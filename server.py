#!/usr/bin/env python3
"""
MusiCast server — music file server with addon-based extensibility.
Drop into a Linux environment, run `python3 server.py`, done.

Core: library scanning, audio analysis, playlists, similarity, moods.
Addons: chromecast, downloader, and future frontend views.
"""

import os
import sys
import json
import uuid
import signal
import socket
import mimetypes
import importlib
import importlib.util
import subprocess
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, unquote, parse_qs, quote

# ---------------------------------------------------------------------------
# Venv bootstrap — ensure we run inside the project venv
# ---------------------------------------------------------------------------

_VENV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")
_VENV_PY = os.path.join(_VENV_DIR, "bin", "python3")

if not os.path.isdir(_VENV_DIR):
    print("Creating virtual environment...")
    subprocess.check_call([sys.executable, "-m", "venv", _VENV_DIR])

if os.path.abspath(sys.executable) != os.path.abspath(_VENV_PY):
    os.execv(_VENV_PY, [_VENV_PY] + sys.argv)

# Core dependencies (numpy, librosa for analysis; mutagen for tags)
_REQUIRED = ["numpy", "librosa", "mutagen"]
_missing = [p for p in _REQUIRED if not importlib.util.find_spec(p)]
if _missing:
    print(f"Installing core dependencies: {', '.join(_missing)}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", *_missing],
                          stdout=sys.stdout, stderr=sys.stderr)

from soniq import (
    _connect, analyze_library, find_similar, get_zones, generate_playlist,
    migrate_from_json, find_by_harmony, get_mood_clusters, find_transitions,
    save_playlist, list_playlists, get_playlist, delete_playlist,
    create_listener, list_listeners, delete_listener,
    add_favorite, remove_favorite, get_favorite_ids,
    get_favorites_count, get_favorites_playlist,
)

PORT = 8000
ROOT = os.path.dirname(os.path.abspath(__file__))
ADDONS_DIR = os.path.join(ROOT, "addons")
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


# ---------------------------------------------------------------------------
# Per-listener playback state (pushed by browser, read by remote)
# ---------------------------------------------------------------------------

_listener_states = {}  # listener_id → {"state": {...}, "condition": Condition()}
_listener_states_lock = threading.Lock()  # protects dict creation only


def _get_listener_state(listener_id):
    """Get or create per-listener state entry. Thread-safe lazy init.

    Fast path reads dict without lock — safe under CPython GIL.
    Lock only protects creation to prevent duplicate entries.
    """
    if listener_id in _listener_states:
        return _listener_states[listener_id]
    with _listener_states_lock:
        if listener_id not in _listener_states:
            _listener_states[listener_id] = {
                "state": {"state": "idle"},
                "condition": threading.Condition(),
            }
        return _listener_states[listener_id]

# ---------------------------------------------------------------------------
# Job tracker (shared infrastructure — used by analysis + addons)
# ---------------------------------------------------------------------------

jobs = {}
jobs_lock = threading.Lock()


def _create_job(url):
    # Purge completed jobs before creating a new one
    with jobs_lock:
        stale = [jid for jid, j in jobs.items() if j["done"]]
        for jid in stale:
            del jobs[jid]

    job_id = uuid.uuid4().hex[:8]
    job = {
        "id": job_id, "url": url, "status": "queued",
        "events": [], "done": False,
        "condition": threading.Condition(),
    }
    with jobs_lock:
        jobs[job_id] = job
    return job


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
# Addon system
# ---------------------------------------------------------------------------

_addons = {}          # id → {manifest, module, routes, status}
_addon_routes = {     # method → {path: (handler, match_type)}
    "GET": {}, "POST": {}, "DELETE": {},
}
_addon_shutdowns = [] # shutdown callbacks


def _addon_ctx():
    """Build the context dict passed to addon register()."""
    return {
        "get_music_root": lambda: MUSIC_ROOT,
        "connect_db": lambda: _connect(MUSIC_ROOT),
        "create_job": _create_job,
        "jobs": jobs,
        "jobs_lock": jobs_lock,
        "get_lan_ip": get_lan_ip,
        "port": PORT,
    }


def _activate_addon(addon_id, addon_dir, manifest):
    """Import, register, and activate an addon. Returns True on success."""
    addon_type = manifest.get("type", "unknown")

    # View addons: no Python module to load, just mark as loaded
    if addon_type == "view":
        _addons[addon_id] = {
            "manifest": manifest,
            "module": None,
            "status": "loaded",
            "dir": addon_dir,
        }
        # Update autoload so it stays enabled on restart
        manifest["autoload"] = True
        manifest_path = os.path.join(addon_dir, "manifest.json")
        try:
            with open(manifest_path, "w") as f:
                json.dump(manifest, f, indent=2)
        except Exception:
            pass
        print(f"  Addon {manifest['name']} v{manifest.get('version', '?')}: view enabled")
        return True

    name = os.path.basename(addon_dir)
    try:
        if addon_dir not in sys.path:
            sys.path.insert(0, os.path.dirname(addon_dir))

        module_name = f"addons.{name}"

        # If module was previously loaded (e.g. failed import), remove it
        if module_name in sys.modules:
            del sys.modules[module_name]

        spec = importlib.util.spec_from_file_location(
            module_name, os.path.join(addon_dir, "__init__.py")
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        routes = {}
        if hasattr(module, "register"):
            routes = module.register(_addon_ctx())

        # Register routes
        for method, paths in routes.items():
            method = method.upper()
            if method not in _addon_routes:
                _addon_routes[method] = {}
            for path, handler in paths.items():
                if path.endswith("*"):
                    _addon_routes[method][path[:-1]] = (handler, "prefix")
                else:
                    _addon_routes[method][path] = (handler, "exact")

        if hasattr(module, "shutdown"):
            _addon_shutdowns.append(module.shutdown)

        _addons[addon_id] = {
            "manifest": manifest,
            "module": module,
            "status": "loaded",
            "dir": addon_dir,
        }
        route_count = sum(len(v) for v in routes.values())
        print(f"  Addon {manifest['name']} v{manifest.get('version', '?')}: "
              f"loaded ({route_count} routes)")
        return True

    except Exception as e:
        _addons[addon_id] = {
            "manifest": manifest,
            "module": None,
            "status": "error",
            "error": str(e),
            "dir": addon_dir,
        }
        print(f"  Addon {manifest['name']}: load error — {e}")
        return False


def _load_addons():
    """Discover and load addons from the addons/ directory."""
    if not os.path.isdir(ADDONS_DIR):
        return

    for name in sorted(os.listdir(ADDONS_DIR)):
        addon_dir = os.path.join(ADDONS_DIR, name)
        manifest_path = os.path.join(addon_dir, "manifest.json")
        if not os.path.isfile(manifest_path):
            continue

        try:
            with open(manifest_path) as f:
                manifest = json.load(f)
        except Exception as e:
            print(f"  Addon {name}: bad manifest — {e}")
            continue

        addon_id = manifest.get("id", name)
        addon_type = manifest.get("type", "unknown")

        # Addons with autoload=false are discovered but not activated
        if manifest.get("autoload") is False:
            _addons[addon_id] = {
                "manifest": manifest,
                "module": None,
                "status": "available",
                "dir": addon_dir,
            }
            print(f"  Addon {manifest['name']} v{manifest.get('version', '?')}: "
                  f"available (enable in add-ons manager)")
            continue

        # Check if dependencies are available
        deps = manifest.get("deps", [])
        missing_deps = [d for d in deps if not importlib.util.find_spec(d.replace("-", "_"))]

        if addon_type == "backend" and missing_deps:
            _addons[addon_id] = {
                "manifest": manifest,
                "module": None,
                "status": "missing_deps",
                "missing_deps": missing_deps,
                "dir": addon_dir,
            }
            print(f"  Addon {manifest['name']}: deps missing ({', '.join(missing_deps)})")
            continue

        if addon_type == "backend":
            _activate_addon(addon_id, addon_dir, manifest)

        elif addon_type == "view":
            _addons[addon_id] = {
                "manifest": manifest,
                "module": None,
                "status": "loaded",
                "dir": addon_dir,
            }
            print(f"  Addon {manifest['name']} v{manifest.get('version', '?')}: "
                  f"view registered")


def _dispatch_addon(method, path):
    """Try to match an addon route. Returns handler or None."""
    routes = _addon_routes.get(method, {})

    # Exact match first
    entry = routes.get(path)
    if entry and entry[1] == "exact":
        return entry[0], path

    # Prefix match
    for route_path, (handler, match_type) in routes.items():
        if match_type == "prefix" and path.startswith(route_path):
            return handler, path

    return None, None


def _install_addon_deps(addon_id):
    """Install missing dependencies and hot-reload the addon."""
    addon = _addons.get(addon_id)
    if not addon:
        return {"error": "Unknown addon"}

    if addon["status"] == "loaded":
        return {"ok": True, "status": "already_loaded"}

    missing = addon.get("missing_deps", [])

    # Install missing pip packages
    if missing:
        try:
            print(f"  Installing deps for {addon_id}: {', '.join(missing)}")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", *missing],
                stdout=sys.stdout, stderr=sys.stderr,
            )
        except Exception as e:
            return {"error": f"Install failed: {e}"}

        # Clear importlib cache so new packages are found
        importlib.invalidate_caches()

        # Verify all deps are now importable
        still_missing = [d for d in missing if not importlib.util.find_spec(d.replace("-", "_"))]
        if still_missing:
            return {"error": f"Still missing after install: {', '.join(still_missing)}"}

    # Hot-reload: activate the addon without restart
    manifest = addon["manifest"]
    addon_dir = addon["dir"]

    if _activate_addon(addon_id, addon_dir, manifest):
        return {"ok": True, "installed": missing, "status": "loaded"}
    else:
        return {"error": "Deps installed but addon failed to load", "installed": missing}


# ---------------------------------------------------------------------------
# Library scanner (for /api/library — directory listing, not analysis)
# ---------------------------------------------------------------------------

def _read_album_meta(album_path, first_file):
    meta = {"genre": "", "year": ""}
    filepath = os.path.join(album_path, first_file)
    try:
        if first_file.lower().endswith(".mp3"):
            from mutagen.id3 import ID3
            tags = ID3(filepath)
            genre_tag = tags.get("TCON")
            if genre_tag:
                meta["genre"] = str(genre_tag)
            year_tag = tags.get("TDRC")
            if year_tag:
                meta["year"] = str(year_tag)
        elif first_file.lower().endswith(".m4a"):
            from mutagen.mp4 import MP4
            audio = MP4(filepath)
            if audio.tags:
                genre = audio.tags.get("\xa9gen")
                if genre:
                    meta["genre"] = genre[0]
                year = audio.tags.get("\xa9day")
                if year:
                    meta["year"] = str(year[0])[:4]
    except Exception:
        pass
    return meta


def _load_durations():
    try:
        conn = _connect(MUSIC_ROOT)
        rows = conn.execute("SELECT file, duration FROM tracks WHERE duration > 0").fetchall()
        conn.close()
        return {row["file"]: row["duration"] for row in rows}
    except Exception:
        return {}


def scan_library():
    albums = []
    if not os.path.isdir(MUSIC_ROOT):
        return albums

    durations = _load_durations()

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
                if f.lower().endswith(('.mp3', '.m4a'))
            )
            if not files:
                continue

            has_cover = os.path.isfile(os.path.join(album_path, "cover.jpg"))
            meta = _read_album_meta(album_path, files[0])

            tracks = []
            for f in files:
                rel = f"{artist}/{album}/{f}"
                tracks.append({
                    "file": f,
                    "duration": durations.get(rel, 0),
                })

            albums.append({
                "artist": artist, "album": album,
                "tracks": tracks, "trackCount": len(files),
                "cover": f"/music/{quote(artist)}/{quote(album)}/cover.jpg" if has_cover else None,
                "genre": meta["genre"], "year": meta["year"],
            })
    return albums


# ---------------------------------------------------------------------------
# HTTP Handler
# ---------------------------------------------------------------------------

class Handler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        '.m4a': 'audio/mp4',
    }

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

        # Check addon routes first
        handler, matched_path = _dispatch_addon("GET", path)
        if handler:
            try:
                # Prefix handlers get the path for ID extraction
                import inspect
                sig = inspect.signature(handler)
                if len(sig.parameters) > 1:
                    handler(self, path)
                else:
                    handler(self)
                return
            except Exception as e:
                print(f"  Addon GET {path} error: {e}")
                try:
                    self._json({"error": str(e)}, 500)
                except Exception:
                    pass
                return

        # Core routes
        if path == '/api/config':
            self._json({
                "lanIp": get_lan_ip(),
                "port": PORT,
                "musicDir": MUSIC_ROOT,
            })
        elif path == '/api/playback':
            lid = self.headers.get('X-Listener-Id', 'guest')
            entry = _get_listener_state(lid)
            self._json(dict(entry["state"]))
        elif path == '/api/playback/stream':
            qs = parse_qs(urlparse(self.path).query)
            lid = qs.get('listener', ['guest'])[0]
            self._stream_playback_state(lid)
        elif path == '/api/library':
            self._json(scan_library())
        elif path == '/api/addons':
            self._json(_get_addons_list())
        elif path == '/api/listeners':
            self._json(list_listeners(MUSIC_ROOT))
        elif path == '/api/favorites/ids':
            qs = parse_qs(urlparse(self.path).query)
            lid = qs.get('listener', [''])[0]
            if not lid:
                self._json({"error": "Missing listener param"}, 400)
            else:
                self._json(get_favorite_ids(lid, MUSIC_ROOT))
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
        elif path == '/api/harmony':
            qs = parse_qs(urlparse(self.path).query)
            key = qs.get('key', [''])[0]
            limit = int(qs.get('limit', ['20'])[0])
            if not key:
                self._json({"error": "Missing key param"}, 400)
            else:
                self._json(find_by_harmony(key, MUSIC_ROOT, limit))
        elif path == '/api/moods':
            self._json(get_mood_clusters(MUSIC_ROOT))
        elif path == '/api/transitions':
            qs = parse_qs(urlparse(self.path).query)
            key = qs.get('key', [''])[0]
            limit = int(qs.get('limit', ['10'])[0])
            if not key:
                self._json({"error": "Missing key param"}, 400)
            else:
                self._json(find_transitions(key, MUSIC_ROOT, limit))
        elif path == '/api/tracks':
            qs = parse_qs(urlparse(self.path).query)
            page = int(qs.get('page', ['1'])[0])
            per_page = int(qs.get('per_page', ['50'])[0])
            search = qs.get('q', [''])[0]
            sort = qs.get('sort', ['artist'])[0]
            order = qs.get('order', ['asc'])[0]
            conn = _connect(MUSIC_ROOT)
            allowed_sorts = {c[1] for c in conn.execute("PRAGMA table_info(tracks)").fetchall()}
            if sort not in allowed_sorts:
                sort = 'artist'
            direction = 'DESC' if order == 'desc' else 'ASC'
            if search:
                like = f'%{search}%'
                total = conn.execute(
                    "SELECT COUNT(*) FROM tracks WHERE artist LIKE ? OR album LIKE ? OR title LIKE ?",
                    (like, like, like)
                ).fetchone()[0]
                rows = conn.execute(
                    f"SELECT * FROM tracks WHERE artist LIKE ? OR album LIKE ? OR title LIKE ? ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
                    (like, like, like, per_page, (page - 1) * per_page)
                ).fetchall()
            else:
                total = conn.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
                rows = conn.execute(
                    f"SELECT * FROM tracks ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
                    (per_page, (page - 1) * per_page)
                ).fetchall()
            tracks_list = []
            for r in rows:
                track = {k: r[k] for k in r.keys()}
                for jcol in ('mfcc_mean_json', 'chroma_mean_json',
                             'tonnetz_mean_json', 'cls_json'):
                    if jcol in track and isinstance(track[jcol], str):
                        track[jcol] = json.loads(track[jcol])
                tracks_list.append(track)
            conn.close()
            self._json({"tracks": tracks_list, "total": total, "page": page, "per_page": per_page})
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
            lid = self.headers.get('X-Listener-Id', 'guest')
            playlists = list_playlists(MUSIC_ROOT, listener_id=lid)
            # Inject virtual Favorites playlist at the top
            fav_count = get_favorites_count(lid, MUSIC_ROOT)
            if fav_count > 0:
                playlists.insert(0, {
                    "id": "favorites",
                    "name": "Favorites",
                    "zone": "",
                    "zoneLabel": "",
                    "trackCount": fav_count,
                    "createdAt": "",
                    "virtual": True,
                })
            self._json(playlists)
        elif path == '/api/playlists/favorites':
            lid = self.headers.get('X-Listener-Id', 'guest')
            tracks = get_favorites_playlist(lid, MUSIC_ROOT)
            self._json({
                "id": "favorites",
                "name": "Favorites",
                "zone": "",
                "zoneLabel": "",
                "zoneDesc": "",
                "trackCount": len(tracks),
                "createdAt": "",
                "tracks": tracks,
            })
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
        elif path.startswith('/addons/'):
            self._serve_addon_static(path)
        elif path.startswith('/music/'):
            self._serve_ranged(path)
        else:
            super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path

        # Check addon routes first
        handler, matched_path = _dispatch_addon("POST", path)
        if handler:
            try:
                handler(self)
                return
            except Exception as e:
                print(f"  Addon POST {path} error: {e}")
                try:
                    self._json({"error": str(e)}, 500)
                except Exception:
                    pass
                return

        # Core routes
        try:
            body = self._read_body()
        except Exception as e:
            self._json({"error": f"Bad request: {e}"}, 400)
            return

        try:
            if path == '/api/playback':
                # Browser pushing its state (per-listener)
                lid = self.headers.get('X-Listener-Id', 'guest')
                entry = _get_listener_state(lid)
                with entry["condition"]:
                    entry["state"].update(body)
                    entry["condition"].notify_all()
                self._json({"ok": True})

            elif path == '/api/analyze':
                job = _create_job("analyze")
                threading.Thread(target=_run_analysis, args=(job,), daemon=True).start()
                self._json({"id": job["id"], "status": "queued"})

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
                lid = self.headers.get('X-Listener-Id', 'guest')
                pid = save_playlist(name, zone, tracks, MUSIC_ROOT, listener_id=lid)
                self._json({"id": pid, "ok": True})

            elif path == '/api/listeners':
                name = body.get("name", "").strip()
                if not name:
                    self._json({"error": "Missing name"}, 400)
                    return
                try:
                    listener = create_listener(name, MUSIC_ROOT)
                    self._json(listener)
                except ValueError as e:
                    self._json({"error": str(e)}, 400)

            elif path == '/api/favorites':
                lid = body.get("listener_id", "")
                tid = body.get("track_id", "")
                if not lid or not tid:
                    self._json({"error": "Missing listener_id or track_id"}, 400)
                    return
                add_favorite(lid, tid, MUSIC_ROOT)
                self._json({"ok": True})

            elif path == '/api/addons/install':
                addon_id = body.get("id", "")
                if not addon_id:
                    self._json({"error": "Missing addon id"}, 400)
                    return
                result = _install_addon_deps(addon_id)
                self._json(result)

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

        # Check addon routes first
        handler, matched_path = _dispatch_addon("DELETE", path)
        if handler:
            try:
                handler(self)
                return
            except Exception as e:
                print(f"  Addon DELETE {path} error: {e}")
                try:
                    self._json({"error": str(e)}, 500)
                except Exception:
                    pass
                return

        if path.startswith('/api/listeners/'):
            lid = path.split('/')[-1]
            if not lid:
                self._json({"error": "Missing listener id"}, 400)
                return
            try:
                delete_listener(lid, MUSIC_ROOT)
                self._json({"ok": True})
            except ValueError as e:
                self._json({"error": str(e)}, 400)

        elif path == '/api/favorites':
            try:
                body = self._read_body()
            except Exception:
                body = {}
            lid = body.get("listener_id", "")
            tid = body.get("track_id", "")
            if not lid or not tid:
                self._json({"error": "Missing listener_id or track_id"}, 400)
                return
            remove_favorite(lid, tid, MUSIC_ROOT)
            self._json({"ok": True})

        elif path.startswith('/api/playlists/'):
            try:
                pid = int(path.split('/')[-1])
            except ValueError:
                self._json({"error": "Invalid id"}, 400)
                return
            lid = self.headers.get('X-Listener-Id', 'guest')
            delete_playlist(pid, MUSIC_ROOT, listener_id=lid)
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

    def _stream_playback_state(self, listener_id='guest'):
        """SSE stream: sends per-listener playback state on every change + 30s keepalive."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        entry = _get_listener_state(listener_id)

        # Send current state immediately on connect
        try:
            self.wfile.write(f"data: {json.dumps(dict(entry['state']))}\n\n".encode())
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

        while True:
            with entry["condition"]:
                entry["condition"].wait(timeout=30)

            try:
                self.wfile.write(f"data: {json.dumps(dict(entry['state']))}\n\n".encode())
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

    def _stream_sse(self, job):
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        while True:
            with job["condition"]:
                while not job["events"] and not job["done"]:
                    job["condition"].wait(timeout=5)
                # Drain: take all pending events and clear the list
                batch = job["events"][:]
                job["events"].clear()
                done = job["done"]

            for event in batch:
                try:
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return
            if done:
                return

    def _serve_addon_static(self, path):
        """Serve static files from frontend addons: /addons/:id/file.html"""
        parts = path.strip("/").split("/")
        if len(parts) < 2:
            self.send_error(404)
            return

        # Serve any file under addons/ directly from disk
        rel_path = "/".join(parts[1:])
        filepath = os.path.join(ADDONS_DIR, rel_path)

        if not os.path.isfile(filepath):
            self.send_error(404)
            return

        content_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
        with open(filepath, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(content))
        self.end_headers()
        self.wfile.write(content)

    def _serve_ranged(self, path):
        rel = unquote(path).lstrip('/')
        if rel.startswith('music/'):
            filepath = os.path.join(MUSIC_ROOT, rel[len('music/'):])
        else:
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
        if path.startswith('/api/status'):
            return
        if path.startswith('/api') or path.startswith('/music/') or '404' in str(args):
            super().log_message(fmt, *args)


def _get_addons_list():
    """Build addon list for /api/addons endpoint."""
    result = []
    for addon_id, addon in _addons.items():
        m = addon["manifest"]
        entry = {
            "id": addon_id,
            "name": m.get("name", addon_id),
            "version": m.get("version", "0.0.0"),
            "type": m.get("type", "unknown"),
            "description": m.get("description", ""),
            "icon": m.get("icon", ""),
            "status": addon["status"],
        }
        if addon["status"] == "missing_deps":
            entry["missingDeps"] = addon.get("missing_deps", [])
        if addon["status"] == "error":
            entry["error"] = addon.get("error", "")
        if m.get("type") == "view" and addon["status"] == "loaded":
            entry["entry"] = f"/addons/{addon_id}/{m.get('entry', 'index.html')}"
        # Include UI metadata for frontend hydration
        ui = m.get("ui")
        if ui and addon["status"] == "loaded":
            entry["ui"] = {
                "component": ui.get("component", ""),
                "entry": f"/addons/{addon_id}/{ui.get('entry', '')}",
                "trigger": ui.get("trigger"),
                "events": ui.get("events", {}),
            }
        result.append(entry)
    return result


class ThreadedServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    os.makedirs(MUSIC_ROOT, exist_ok=True)

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

    # Load addons
    print("Loading addons...")
    _load_addons()

    server = ThreadedServer(('0.0.0.0', PORT), Handler)

    _state = {"shutting_down": False}

    def _shutdown(signum=None, frame=None):
        if _state["shutting_down"]:
            print("\nForce exit.")
            os._exit(1)
        _state["shutting_down"] = True
        print("\nShutting down...")
        for shutdown_fn in _addon_shutdowns:
            try:
                shutdown_fn()
            except Exception:
                pass
        # Run in thread — server.shutdown() blocks until request threads finish
        threading.Thread(target=server.shutdown, daemon=True).start()
        # Give threads 2s to finish, then force exit
        threading.Timer(2.0, lambda: os._exit(0)).start()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        _shutdown()
