#!/usr/bin/env python3
"""
MusiCast server — music file server, Chromecast caster, YouTube Music downloader.
Drop into a Linux environment, run `python3 server.py`, done.
"""

import os
import json
import uuid
import socket
import mimetypes
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, unquote, parse_qs

from downloader import bootstrap, download_playlist
from cast_manager import CastManager
from analyzer import analyze_library, find_similar, get_zones, generate_playlist, migrate_from_json
from playlist_manager import save_playlist, list_playlists, get_playlist, delete_playlist

PORT = 8000
ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(ROOT, "config.json")


def load_config():
    defaults = {"musicDir": os.path.join(ROOT, "music")}
    if os.path.isfile(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
            defaults.update(saved)
        except Exception:
            pass
    return defaults


def save_config(data):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"  Config save error: {e}")


_config = load_config()
MUSIC_ROOT = _config["musicDir"]


def get_lan_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


cast_mgr = CastManager(port=PORT, get_lan_ip=get_lan_ip)


# ---------------------------------------------------------------------------
# Job tracker (download jobs)
# ---------------------------------------------------------------------------

jobs = {}
jobs_lock = threading.Lock()


def _create_job(url):
    job_id = uuid.uuid4().hex[:8]
    job = {
        "id": job_id, "url": url, "status": "queued",
        "events": [], "done": False,
        "condition": threading.Condition(),
    }
    with jobs_lock:
        jobs[job_id] = job
    return job


def _run_job(job):
    job["status"] = "downloading"

    def on_progress(data):
        with job["condition"]:
            job["events"].append(data)
            job["condition"].notify_all()

    try:
        result = download_playlist(job["url"], MUSIC_ROOT, on_progress=on_progress)
        result["status"] = "complete"
        with job["condition"]:
            job["events"].append(result)
            job["status"] = "complete"
            job["done"] = True
            job["condition"].notify_all()
    except Exception as e:
        err = {"message": f"Error: {e}", "status": "error"}
        with job["condition"]:
            job["events"].append(err)
            job["status"] = "error"
            job["done"] = True
            job["condition"].notify_all()


def _run_analysis(job):
    job["status"] = "analyzing"

    def on_progress(data):
        with job["condition"]:
            job["events"].append(data)
            job["condition"].notify_all()

    try:
        analyze_library(MUSIC_ROOT, on_progress=on_progress)
        with job["condition"]:
            job["status"] = "complete"
            job["done"] = True
            job["condition"].notify_all()
    except Exception as e:
        err = {"message": f"Error: {e}", "status": "error"}
        with job["condition"]:
            job["events"].append(err)
            job["status"] = "error"
            job["done"] = True
            job["condition"].notify_all()


# ---------------------------------------------------------------------------
# Library scanner
# ---------------------------------------------------------------------------

def _read_album_meta(album_path, first_mp3):
    meta = {"genre": "", "year": ""}
    try:
        from mutagen.id3 import ID3
        tags = ID3(os.path.join(album_path, first_mp3))
        genre_tag = tags.get("TCON")
        if genre_tag:
            meta["genre"] = str(genre_tag)
        year_tag = tags.get("TDRC")
        if year_tag:
            meta["year"] = str(year_tag)
    except Exception:
        pass
    return meta


def scan_library():
    albums = []
    if not os.path.isdir(MUSIC_ROOT):
        return albums

    for artist in sorted(os.listdir(MUSIC_ROOT)):
        artist_path = os.path.join(MUSIC_ROOT, artist)
        if not os.path.isdir(artist_path):
            continue
        for album in sorted(os.listdir(artist_path)):
            album_path = os.path.join(artist_path, album)
            if not os.path.isdir(album_path):
                continue
            files = sorted(
                f for f in os.listdir(album_path)
                if f.lower().endswith('.mp3')
            )
            if not files:
                continue

            has_cover = os.path.isfile(os.path.join(album_path, "cover.jpg"))
            meta = _read_album_meta(album_path, files[0])

            albums.append({
                "artist": artist, "album": album,
                "tracks": files, "trackCount": len(files),
                "cover": f"/music/{artist}/{album}/cover.jpg" if has_cover else None,
                "genre": meta["genre"], "year": meta["year"],
            })
    return albums


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == '/api/config':
            self._json({
                "lanIp": get_lan_ip(),
                "port": PORT,
                "musicDir": MUSIC_ROOT,
            })
        elif path == '/api/library':
            self._json(scan_library())
        elif path == '/api/devices':
            self._json(cast_mgr.list_devices())
        elif path == '/api/status':
            self._json(cast_mgr.get_status())
        elif path == '/api/downloads':
            with jobs_lock:
                self._json([{
                    "id": j["id"], "url": j["url"],
                    "status": j["status"], "done": j["done"],
                } for j in jobs.values()])
        elif path.startswith('/api/download/'):
            job_id = path.split('/')[-1]
            with jobs_lock:
                job = jobs.get(job_id)
            if not job:
                self._json({"error": "Unknown job"}, 404)
            else:
                self._stream_sse(job)
        elif path.startswith('/api/analyze/'):
            job_id = path.split('/')[-1]
            with jobs_lock:
                job = jobs.get(job_id)
            if not job:
                self._json({"error": "Unknown job"}, 404)
            else:
                self._stream_sse(job)
        elif path == '/api/similar':
            qs = parse_qs(urlparse(self.path).query)
            key = qs.get('key', [''])[0]
            limit = int(qs.get('limit', ['10'])[0])
            if not key:
                self._json({"error": "Missing key param"}, 400)
            else:
                self._json(find_similar(key, MUSIC_ROOT, limit))
        elif path == '/api/zones':
            self._json(get_zones(MUSIC_ROOT))
        elif path == '/api/playlist':
            qs = parse_qs(urlparse(self.path).query)
            zone = qs.get('zone', [''])[0]
            limit = int(qs.get('limit', ['25'])[0])
            if not zone:
                self._json({"error": "Missing zone param"}, 400)
            else:
                self._json(generate_playlist(zone, MUSIC_ROOT, limit))
        elif path == '/api/browse':
            qs = parse_qs(urlparse(self.path).query)
            browse_path = qs.get('path', [os.path.expanduser('~')])[0]
            try:
                entries = []
                if browse_path != '/':
                    entries.append({"name": "..", "path": os.path.dirname(browse_path)})
                for name in sorted(os.listdir(browse_path)):
                    full = os.path.join(browse_path, name)
                    if os.path.isdir(full) and not name.startswith('.'):
                        entries.append({"name": name, "path": full})
                self._json({"current": browse_path, "dirs": entries})
            except PermissionError:
                self._json({"current": browse_path, "dirs": [], "error": "Permission denied"})
            except FileNotFoundError:
                self._json({"current": os.path.expanduser('~'), "dirs": [], "error": "Not found"})
        elif path == '/api/playlists':
            self._json(list_playlists(MUSIC_ROOT))
        elif path.startswith('/api/playlists/'):
            try:
                pid = int(path.split('/')[-1])
            except ValueError:
                self._json({"error": "Invalid id"}, 400)
                return
            data = get_playlist(pid, MUSIC_ROOT)
            if data:
                self._json(data)
            else:
                self._json({"error": "Not found"}, 404)
        elif path.startswith('/music/'):
            self._serve_ranged(path)
        else:
            super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._read_body()
        except Exception as e:
            self._json({"error": f"Bad request: {e}"}, 400)
            return

        try:
            if path == '/api/download':
                url = body.get('url', '').strip()
                if not url:
                    self._json({"error": "Missing url"}, 400)
                    return
                job = _create_job(url)
                threading.Thread(target=_run_job, args=(job,), daemon=True).start()
                self._json({"id": job["id"], "status": "queued"})

            elif path == '/api/analyze':
                job = _create_job("analyze")
                threading.Thread(target=_run_analysis, args=(job,), daemon=True).start()
                self._json({"id": job["id"], "status": "queued"})

            elif path == '/api/cast':
                device_id = body.get('deviceId')
                if not device_id:
                    self._json({"error": "Missing deviceId"}, 400)
                    return
                result = cast_mgr.cast(
                    device_id, body.get('track', {}),
                    body.get('queue'), body.get('queueIndex', 0),
                    body.get('baseUrl'),
                )
                self._json(result)

            elif path == '/api/config':
                global MUSIC_ROOT, _config
                changed = False
                if 'musicDir' in body:
                    new_dir = body['musicDir'].strip()
                    if new_dir and os.path.isabs(new_dir):
                        os.makedirs(new_dir, exist_ok=True)
                        MUSIC_ROOT = new_dir
                        _config['musicDir'] = new_dir
                        changed = True
                    else:
                        self._json({"error": "musicDir must be an absolute path"}, 400)
                        return
                if changed:
                    save_config(_config)
                self._json({"ok": True, "musicDir": MUSIC_ROOT})

            elif path == '/api/playlists':
                name = body.get('name', '').strip()
                zone = body.get('zone', '')
                tracks = body.get('tracks', [])
                if not name or not tracks:
                    self._json({"error": "Missing name or tracks"}, 400)
                    return
                pid = save_playlist(name, zone, tracks, MUSIC_ROOT)
                self._json({"id": pid, "ok": True})

            elif path == '/api/control':
                action = body.get('action')
                if not action:
                    self._json({"error": "Missing action"}, 400)
                    return
                self._json(cast_mgr.control(action, body.get('value')))

            else:
                self.send_error(404)

        except Exception as e:
            print(f"  POST {path} error: {e}")
            try:
                self._json({"error": str(e)}, 500)
            except Exception:
                pass

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path.startswith('/api/playlists/'):
            try:
                pid = int(path.split('/')[-1])
            except ValueError:
                self._json({"error": "Invalid id"}, 400)
                return
            delete_playlist(pid, MUSIC_ROOT)
            self._json({"ok": True})
        else:
            self.send_error(404)

    def _read_body(self):
        length = int(self.headers.get('Content-Length', 0))
        if length:
            return json.loads(self.rfile.read(length))
        return {}

    def _json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _stream_sse(self, job):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        cursor = 0
        while True:
            with job["condition"]:
                while cursor >= len(job["events"]) and not job["done"]:
                    job["condition"].wait(timeout=5)
                new = job["events"][cursor:]
                cursor = len(job["events"])
                done = job["done"]

            for event in new:
                try:
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
            if done:
                return

    def _serve_ranged(self, path):
        rel = unquote(path).lstrip('/')
        filepath = os.path.join(ROOT, rel)

        if not os.path.isfile(filepath):
            self.send_error(404)
            return

        file_size = os.path.getsize(filepath)
        content_type = mimetypes.guess_type(filepath)[0] or 'application/octet-stream'
        range_header = self.headers.get('Range')

        if range_header:
            try:
                start_str, end_str = range_header.replace('bytes=', '').split('-')
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1

                self.send_response(206)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', length)
                self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                self.send_header('Accept-Ranges', 'bytes')
                self.end_headers()

                with open(filepath, 'rb') as f:
                    f.seek(start)
                    remaining = length
                    while remaining > 0:
                        chunk = f.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return
            except (ValueError, IOError):
                try:
                    self.send_error(416)
                except (BrokenPipeError, ConnectionResetError):
                    return
        else:
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', file_size)
            self.send_header('Accept-Ranges', 'bytes')
            self.end_headers()
            try:
                with open(filepath, 'rb') as f:
                    while True:
                        chunk = f.read(65536)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                return

    def log_message(self, fmt, *args):
        try:
            path = args[0].split()[1] if args and isinstance(args[0], str) else ''
        except (IndexError, AttributeError):
            path = ''
        # Show API, music file requests (from Chromecasts), and errors
        if path.startswith('/api/status'):
            return  # too noisy
        if path.startswith('/api') or path.startswith('/music/') or '404' in str(args):
            super().log_message(fmt, *args)


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    os.makedirs(MUSIC_ROOT, exist_ok=True)

    print("Bootstrapping dependencies...")
    bootstrap()

    lan_ip = get_lan_ip()

    print(f"\n  MusiCast")
    print(f"  {'=' * 40}")
    print(f"  Local:   http://localhost:{PORT}")
    print(f"  LAN:     http://{lan_ip}:{PORT}")
    print(f"  Music:   {MUSIC_ROOT}")
    print(f"  {'=' * 40}\n")

    # Auto-migrate from JSON if old data exists
    migrated = migrate_from_json(MUSIC_ROOT)
    if migrated:
        print(f"  Migrated {migrated} tracks from JSON to SQLite.")

    print("Discovering Chromecast devices...")
    cast_mgr.start_discovery()

    server = ThreadedServer(('0.0.0.0', PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        cast_mgr.stop()
        server.shutdown()
