"""
Chromecast discovery + control via pychromecast.

Media status via event listener (no polling threads).
Queue managed server-side — play one track at a time, auto-advance on finish.
"""

import socket
import threading
import time


class CastManager:
    def __init__(self, port=8000, get_lan_ip=None):
        self._port = port
        self._get_lan_ip = get_lan_ip or (lambda: "127.0.0.1")
        self._devices = {}       # uuid_str → Chromecast
        self._browser = None
        self._lock = threading.Lock()
        self._active = None      # currently casting Chromecast
        self._queue = []
        self._qi = -1
        self._base_url = None

        # Status cache — updated by listener
        self._status_lock = threading.Lock()
        self._player_state = "IDLE"
        self._current_time = 0
        self._duration = 0
        self._last_update_ts = 0
        self._was_playing = False  # for auto-advance detection

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
            return [
                {
                    "id": uid,
                    "name": cc.name,
                    "model": cc.model_name,
                    "is_active": self._active and str(self._active.uuid) == uid,
                }
                for uid, cc in self._devices.items()
            ]

    # -- Cast --

    def cast(self, device_id, track, queue=None, queue_index=0, base_url=None):
        if base_url:
            self._base_url = base_url
        try:
            with self._lock:
                cc = self._devices.get(device_id)
            if not cc:
                return {"error": "Device not found"}
            cc.wait(timeout=10)

            # Quit app on previous device if switching
            if self._active and self._active.uuid != cc.uuid:
                try:
                    self._active.quit_app()
                except Exception:
                    pass

            self._active = cc
            self._queue = queue or [track]
            self._qi = queue_index

            # Register status listener (pychromecast deduplicates)
            cc.media_controller.register_status_listener(self)

            self._play_track(cc, self._qi)
            return {"ok": True, "device": cc.name}
        except Exception as e:
            return {"error": str(e)}

    def _play_track(self, cc, index):
        """Play a single track by queue index."""
        if index < 0 or index >= len(self._queue):
            return
        self._qi = index
        track = self._queue[index]
        url, base = self._resolve_url(track)
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

        print(f"  Casting to {cc.name}: {title} ({index + 1}/{len(self._queue)})")

        mc = cc.media_controller
        mc.play_media(
            url, content_type,
            title=title, thumb=thumb,
            stream_type="BUFFERED",
            metadata=meta,
        )
        with self._status_lock:
            self._was_playing = False
        try:
            mc.block_until_active(timeout=10)
        except Exception:
            print(f"  Cast media did not become active within 10s")

    def _resolve_url(self, track):
        """Build absolute URL for a track."""
        url = track.get("url", "")
        base = self._base_url or f"http://{self._get_lan_ip()}:{self._port}"
        if url.startswith("/"):
            url = base + url
        return url, base

    # -- Media status listener (called by pychromecast on events) --

    def new_media_status(self, status):
        """Called by pychromecast when media status changes."""
        with self._status_lock:
            prev_state = self._player_state
            self._player_state = status.player_state or "IDLE"
            self._current_time = status.current_time or 0
            self._duration = status.duration or 0
            self._last_update_ts = time.time()

            if self._player_state == "PLAYING":
                self._was_playing = True

            # Auto-advance: was playing, now idle → track finished
            should_advance = (
                self._was_playing
                and self._player_state == "IDLE"
                and self._qi < len(self._queue) - 1
            )
            if should_advance:
                self._was_playing = False

        # Advance outside the lock to avoid deadlock
        if should_advance:
            cc = self._active
            if cc:
                self._play_track(cc, self._qi + 1)

    def load_media_failed(self, queue_item_id, error_code):
        """Called by pychromecast when media fails to load."""
        print(f"  Cast media load failed: item {queue_item_id}, error {error_code}")

    # -- Control --

    def control(self, action, value=None):
        cc = self._active
        if not cc:
            return {"error": "No active device"}
        mc = cc.media_controller
        try:
            if action == "play":
                mc.play()
            elif action == "pause":
                mc.pause()
            elif action == "toggle":
                with self._status_lock:
                    state = self._player_state
                if state == "PLAYING":
                    mc.pause()
                else:
                    mc.play()
            elif action == "stop":
                with self._status_lock:
                    self._was_playing = False
                    self._player_state = "IDLE"
                try:
                    mc.stop()
                except Exception:
                    pass
                try:
                    cc.quit_app()
                except Exception:
                    pass
                self._active = None
                self._queue = []
                self._qi = -1
            elif action == "next":
                if self._qi < len(self._queue) - 1:
                    self._play_track(cc, self._qi + 1)
            elif action == "prev":
                with self._status_lock:
                    ct = self._current_time
                if ct and ct > 3:
                    mc.seek(0)
                elif self._qi > 0:
                    self._play_track(cc, self._qi - 1)
            elif action == "seek" and value is not None:
                mc.seek(float(value))
            elif action == "volume" and value is not None:
                cc.set_volume(float(value))
            return {"ok": True}
        except Exception as e:
            return {"error": str(e)}

    def get_status(self):
        cc = self._active
        if not cc:
            return {"state": "idle"}
        try:
            track = self._queue[self._qi] if 0 <= self._qi < len(self._queue) else {}

            with self._status_lock:
                state = self._player_state
                raw_time = self._current_time
                duration = self._duration
                last_ts = self._last_update_ts

            # Interpolate position between listener updates
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
                "queueIndex": self._qi,
                "queueLength": len(self._queue),
                "device": cc.name,
            }
        except Exception:
            return {"state": "idle"}

    def stop(self):
        if self._active:
            try:
                self._active.media_controller.stop()
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
        self._active = None
