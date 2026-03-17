"""
Chromecast discovery + control via pychromecast.
Extracted from server.py to keep concerns separated.
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
        self._qi = -1            # queue index
        self._base_url = None    # set by frontend on first cast
        self._last_time = 0      # last known currentTime
        self._last_state = None  # last player state
        self._last_ts = 0        # timestamp of last status read
        self._watch_gen = 0      # generation counter to kill old watchers
        self._watch_stop = threading.Event()  # signal current watcher to exit

    # -- Discovery --

    def start_discovery(self):
        if self._browser:
            return  # already running
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
        # Step 1: find active subnets by probing gateways
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

        # Step 2: scan those subnets for port 8009
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
            self._active = cc
            self._queue = queue or [track]
            self._qi = queue_index
            # Kill old watcher before starting new one
            self._watch_gen += 1
            self._play_current(cc)
            self._watch(cc)
            return {"ok": True, "device": cc.name}
        except Exception as e:
            return {"error": str(e)}

    def _play_current(self, cc):
        if self._qi < 0 or self._qi >= len(self._queue):
            return
        track = self._queue[self._qi]
        url = track.get("url", "")
        base = self._base_url or f"http://{self._get_lan_ip()}:{self._port}"
        if url.startswith("/"):
            url = base + url

        # Warn if media URL uses a container IP — Chromecasts can't reach it
        if "100.115." in url or "localhost" in url or "127.0.0.1" in url:
            print(f"  WARNING: Media URL may be unreachable by Chromecast: {url}")
            print(f"  Set base_url via the frontend WiFi IP prompt or use a LAN IP.")

        print(f"  Casting to {cc.name}: {url}")
        print(f"  Base URL: {base}")

        mc = cc.media_controller
        meta = {
            "metadataType": 3,
            "title": track.get("title", ""),
            "artist": track.get("artist", ""),
            "albumName": track.get("album", ""),
        }
        cover = track.get("cover")
        if cover:
            meta["images"] = [{"url": base + cover if cover.startswith("/") else cover}]

        mc.play_media(url, "audio/mpeg", metadata=meta)
        try:
            mc.block_until_active(timeout=10)
        except Exception:
            print(f"  Cast media did not become active within 10s")

    def _watch(self, cc):
        """Auto-advance queue when track finishes."""
        # Signal any previous watcher to exit immediately
        self._watch_stop.set()
        self._watch_stop = threading.Event()
        stop = self._watch_stop  # capture for this watcher
        gen = self._watch_gen

        def _loop():
            mc = cc.media_controller
            was_playing = False
            while not stop.is_set() and gen == self._watch_gen and self._active and self._active.uuid == cc.uuid:
                stop.wait(1)  # sleeps up to 1s but wakes instantly on stop
                if stop.is_set() or gen != self._watch_gen:
                    return
                try:
                    ps = mc.status.player_state
                    if ps == "PLAYING":
                        was_playing = True
                    elif was_playing and ps in ("IDLE", "UNKNOWN"):
                        was_playing = False
                        if self._qi < len(self._queue) - 1:
                            self._qi += 1
                            self._play_current(cc)
                except Exception:
                    break
        threading.Thread(target=_loop, daemon=True).start()

    # -- Control --

    def control(self, action, value=None):
        cc = self._active
        if not cc:
            return {"error": "No active device"}
        mc = cc.media_controller
        try:
            if action == "play":      mc.play()
            elif action == "pause":   mc.pause()
            elif action == "toggle":
                s = mc.status
                if s and s.player_state == "PLAYING":
                    mc.pause()
                else:
                    mc.play()
            elif action == "stop":
                mc.stop()
                self._active = None
            elif action == "next":
                if self._qi < len(self._queue) - 1:
                    self._watch_gen += 1
                    self._qi += 1
                    self._play_current(cc)
                    self._watch(cc)
            elif action == "prev":
                s = mc.status
                if s and s.current_time and s.current_time > 3:
                    mc.seek(0)
                elif self._qi > 0:
                    self._watch_gen += 1
                    self._qi -= 1
                    self._play_current(cc)
                    self._watch(cc)
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
            mc = cc.media_controller
            s = mc.status
            track = self._queue[self._qi] if 0 <= self._qi < len(self._queue) else {}

            # Interpolate: pychromecast only updates time on events
            raw_time = s.current_time or 0
            now = time.time()
            if raw_time != self._last_time or s.player_state != self._last_state:
                self._last_time = raw_time
                self._last_state = s.player_state
                self._last_ts = now
            ct = raw_time
            if s.player_state == "PLAYING" and self._last_ts:
                ct = raw_time + (now - self._last_ts)

            return {
                "state": (s.player_state or "UNKNOWN").lower(),
                "currentTime": ct,
                "duration": s.duration or 0,
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
        self._watch_stop.set()
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
