"""
Chromecast discovery + control via pychromecast.

Per-listener sessions — each listener owns their own device, queue, and state.
Device-to-listener reverse map prevents conflicts.
"""

import socket
import threading
import time


class _DeviceStatusListener:
    """Per-device pychromecast status listener that routes to CastManager with device UUID."""

    def __init__(self, manager, device_uuid):
        self._manager = manager
        self._device_uuid = device_uuid

    def new_media_status(self, status):
        self._manager._on_media_status(self._device_uuid, status)

    def load_media_failed(self, queue_item_id, error_code):
        print(f"  Cast media load failed on {self._device_uuid}: item {queue_item_id}, error {error_code}")


class CastManager:
    def __init__(self, port=8000, get_lan_ip=None, push_state=None):
        self._port = port
        self._get_lan_ip = get_lan_ip or (lambda: "127.0.0.1")
        self._push_state = push_state  # callback(listener_id, state_dict) → push to SSE
        self._devices = {}       # uuid_str → Chromecast
        self._browser = None
        self._lock = threading.Lock()

        # Per-listener sessions
        self._sessions = {}           # listener_id → session dict
        self._device_to_listener = {} # device_uuid → listener_id
        self._device_listeners = {}   # device_uuid → _DeviceStatusListener
        self._session_lock = threading.Lock()

    def _get_session(self, listener_id):
        """Get or create a session for a listener."""
        if listener_id not in self._sessions:
            self._sessions[listener_id] = {
                "device": None,       # Chromecast object
                "queue": [],
                "qi": -1,
                "base_url": None,
                "player_state": "IDLE",
                "current_time": 0,
                "duration": 0,
                "last_update_ts": 0,
                "was_playing": False,
            }
        return self._sessions[listener_id]

    # -- Discovery --

    def start_discovery(self):
        if self._browser:
            return
        threading.Thread(target=self._discover, daemon=True).start()

    def _discover(self):
        import pychromecast
        hosts = self._scan_for_chromecasts()
        try:
            kw = {"timeout": 10}
            if hosts:
                kw["known_hosts"] = hosts
            casts, browser = pychromecast.get_chromecasts(**kw)
            self._browser = browser
            with self._lock:
                for cc in casts:
                    self._devices[str(cc.uuid)] = cc
            print(f"  Found {len(casts)} Chromecast(s)")
            for cc in casts:
                print(f"    {cc.name} ({cc.model_name})")
        except Exception as e:
            print(f"  Discovery error: {e}")

    def _scan_for_chromecasts(self):
        """Find devices with port 8009 open on reachable subnets."""
        gateways = []
        gw_lock = threading.Lock()

        def probe_gw(ip):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect((ip, 80))
                s.close()
                with gw_lock:
                    gateways.append(ip)
            except Exception:
                pass

        threads = []
        for sub in range(256):
            t = threading.Thread(target=probe_gw, args=(f"192.168.{sub}.1",))
            t.start()
            threads.append(t)
        for t in threads:
            t.join()

        if not gateways:
            print("  No reachable subnets found")
            return []

        print(f"  Subnets: {', '.join(gw.rsplit('.', 1)[0] + '.x' for gw in sorted(gateways))}")

        found = []
        found_lock = threading.Lock()

        def probe_8009(ip):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                s.connect((ip, 8009))
                s.close()
                with found_lock:
                    found.append(ip)
            except Exception:
                pass

        threads = []
        for gw in gateways:
            prefix = gw.rsplit(".", 1)[0]
            for i in range(1, 255):
                t = threading.Thread(target=probe_8009, args=(f"{prefix}.{i}",))
                t.start()
                threads.append(t)
        for t in threads:
            t.join()

        if found:
            print(f"  Port 8009 on: {', '.join(sorted(found))}")
        else:
            print("  No port 8009 found")
        return found

    # -- Device list --

    def list_devices(self):
        with self._lock:
            devices = []
            for uid, cc in self._devices.items():
                owner = self._device_to_listener.get(uid)
                devices.append({
                    "id": uid,
                    "name": cc.name,
                    "model": cc.model_name,
                    "owned_by": owner,
                })
            return devices

    # -- Cast (per-listener) --

    def cast(self, device_id, track, queue=None, queue_index=0, base_url=None, listener_id="guest"):
        with self._session_lock:
            # Check if another listener owns this device
            current_owner = self._device_to_listener.get(device_id)
            if current_owner and current_owner != listener_id:
                return {"error": f"Device in use by another listener"}

            with self._lock:
                cc = self._devices.get(device_id)
            if not cc:
                return {"error": "Device not found"}

            session = self._get_session(listener_id)

            # If this listener had a different device, release it
            old_device = session["device"]
            if old_device and str(old_device.uuid) != device_id:
                old_uuid = str(old_device.uuid)
                try:
                    old_device.quit_app()
                except Exception:
                    pass
                self._device_to_listener.pop(old_uuid, None)

            session["device"] = cc
            session["queue"] = queue or [track]
            session["qi"] = queue_index
            session["was_playing"] = False  # prevent stale auto-advance after reassignment
            if base_url:
                session["base_url"] = base_url

            self._device_to_listener[device_id] = listener_id

        try:
            cc.wait(timeout=10)
            # Register per-device status listener (captures device_id for reverse lookup)
            if device_id not in self._device_listeners:
                dl = _DeviceStatusListener(self, device_id)
                self._device_listeners[device_id] = dl
                cc.media_controller.register_status_listener(dl)

            self._play_track(listener_id, queue_index)
            return {"ok": True, "device": cc.name}
        except Exception as e:
            return {"error": str(e)}

    def _play_track(self, listener_id, index):
        """Play a single track by queue index for a specific listener."""
        session = self._sessions.get(listener_id)
        if not session or not session["device"]:
            return
        cc = session["device"]
        queue = session["queue"]
        if index < 0 or index >= len(queue):
            return
        session["qi"] = index
        track = queue[index]
        url, base = self._resolve_url(track, session)
        title = track.get("title", "")
        artist = track.get("artist", "")
        album = track.get("album", "")
        cover = track.get("cover")
        thumb = (base + cover if cover and cover.startswith("/") else cover) or None
        content_type = "audio/mp4" if url.lower().endswith(".m4a") else "audio/mpeg"

        meta = {
            "metadataType": 3,
            "title": title,
            "artist": artist,
            "albumName": album,
        }
        if thumb:
            meta["images"] = [{"url": thumb}]

        if "100.115." in url or "localhost" in url or "127.0.0.1" in url:
            print(f"  WARNING: Media URL may be unreachable by Chromecast: {url}")

        print(f"  Casting to {cc.name} [{listener_id}]: {title} ({index + 1}/{len(queue)})")

        mc = cc.media_controller
        mc.play_media(
            url, content_type,
            title=title, thumb=thumb,
            stream_type="BUFFERED",
            metadata=meta,
        )
        session["was_playing"] = False
        try:
            mc.block_until_active(timeout=10)
        except Exception:
            print(f"  Cast media did not become active within 10s")

    def _resolve_url(self, track, session):
        """Build absolute URL for a track."""
        url = track.get("url", "")
        base = session.get("base_url") or f"http://{self._get_lan_ip()}:{self._port}"
        if url.startswith("/"):
            url = base + url
        return url, base

    # -- Media status (routed from per-device listeners) --

    def _on_media_status(self, device_uuid, status):
        """Handle media status update for a specific device."""
        with self._session_lock:
            listener_id = self._device_to_listener.get(device_uuid)
            if not listener_id:
                return

            session = self._sessions.get(listener_id)
            if not session:
                return

            session["player_state"] = status.player_state or "IDLE"
            session["current_time"] = status.current_time or 0
            session["duration"] = status.duration or 0
            session["last_update_ts"] = time.time()

            if session["player_state"] == "PLAYING":
                session["was_playing"] = True

            # Auto-advance: was playing, now idle → track finished
            should_advance = (
                session["was_playing"]
                and session["player_state"] == "IDLE"
                and session["qi"] < len(session["queue"]) - 1
            )
            if should_advance:
                session["was_playing"] = False

            # Push state directly to SSE — no poll delay
            if self._push_state and not should_advance:
                self._push_state(listener_id, self._build_status(session))

        # Advance outside the lock to avoid deadlock with pychromecast
        if should_advance:
            self._play_track(listener_id, session["qi"] + 1)

    # -- Control (per-listener) --

    def control(self, action, value=None, listener_id="guest"):
        session = self._sessions.get(listener_id)
        if not session or not session["device"]:
            return {"error": "No active device for this listener"}
        cc = session["device"]
        mc = cc.media_controller
        try:
            if action == "play":
                mc.play()
            elif action == "pause":
                mc.pause()
            elif action == "toggle":
                state = session["player_state"]
                if state == "PLAYING":
                    mc.pause()
                else:
                    mc.play()
            elif action == "stop":
                session["was_playing"] = False
                session["player_state"] = "IDLE"
                try:
                    mc.stop()
                except Exception:
                    pass
                try:
                    cc.quit_app()
                except Exception:
                    pass
                # Release device
                with self._session_lock:
                    device_uuid = str(cc.uuid)
                    self._device_to_listener.pop(device_uuid, None)
                session["device"] = None
                session["queue"] = []
                session["qi"] = -1
            elif action == "next":
                if session["qi"] < len(session["queue"]) - 1:
                    self._play_track(listener_id, session["qi"] + 1)
            elif action == "prev":
                ct = session["current_time"]
                if ct and ct > 3:
                    mc.seek(0)
                elif session["qi"] > 0:
                    self._play_track(listener_id, session["qi"] - 1)
            elif action == "seek" and value is not None:
                mc.seek(float(value))
            elif action == "volume" and value is not None:
                cc.set_volume(float(value))
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}

    def _build_status(self, session):
        """Build a status dict from a session. Must be called under _session_lock."""
        cc = session["device"]
        if not cc:
            return {"state": "idle"}
        try:
            track = session["queue"][session["qi"]] if 0 <= session["qi"] < len(session["queue"]) else {}
            state = session["player_state"]
            raw_time = session["current_time"]
            duration = session["duration"]
            last_ts = session["last_update_ts"]

            ct = raw_time
            if state == "PLAYING" and last_ts:
                ct = raw_time + (time.time() - last_ts)

            return {
                "state": state.lower(),
                "currentTime": ct,
                "duration": duration,
                "volume": cc.status.volume_level if cc.status else 1,
                "title": track.get("title", ""),
                "artist": track.get("artist", ""),
                "album": track.get("album", ""),
                "cover": track.get("cover", ""),
                "queueIndex": session["qi"],
                "queueLength": len(session["queue"]),
                "device": cc.name,
            }
        except Exception:
            return {"state": "idle"}

    def get_status(self, listener_id="guest"):
        with self._session_lock:
            session = self._sessions.get(listener_id)
            if not session or not session["device"]:
                return {"state": "idle"}
            return self._build_status(session)

    def stop(self):
        # Stop all active sessions
        for lid, session in self._sessions.items():
            if session["device"]:
                try:
                    session["device"].media_controller.stop()
                except Exception:
                    pass
        if self._browser:
            self._browser.stop_discovery()
        with self._lock:
            for cc in self._devices.values():
                try:
                    cc.disconnect()
                except Exception:
                    pass
            self._devices.clear()
        self._sessions.clear()
        self._device_to_listener.clear()
