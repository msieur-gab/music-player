#!/usr/bin/env python3
"""
Music Player server.
- Serves static files (HTML, CSS, JS, music) with Range request support
- POST /api/download        → starts a background download, returns { id }
- GET  /api/download/:id    → SSE stream of progress for that job
- GET  /api/downloads       → list all jobs and their status
- GET  /api/library         → JSON tree of artist/album/tracks
"""

import os
import sys
import json
import uuid
import mimetypes
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs, unquote

from downloader import bootstrap, download_playlist

PORT = 8000
ROOT = os.path.dirname(os.path.abspath(__file__))
MUSIC_ROOT = os.path.join(ROOT, "music")

# ---------------------------------------------------------------------------
# Job tracker
# ---------------------------------------------------------------------------
jobs = {}  # id → { url, status, events[], done: bool }
jobs_lock = threading.Lock()


def _create_job(url):
    job_id = uuid.uuid4().hex[:8]
    job = {
        "id": job_id,
        "url": url,
        "status": "queued",
        "events": [],
        "done": False,
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


# ---------------------------------------------------------------------------
# Library scanner
# ---------------------------------------------------------------------------

def _read_album_meta(album_path, first_mp3):
    """Read genre and year from first track's ID3 tags."""
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
    """Return a list of album objects with full metadata."""
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
                "artist": artist,
                "album": album,
                "tracks": files,
                "trackCount": len(files),
                "cover": f"/music/{artist}/{album}/cover.jpg" if has_cover else None,
                "genre": meta["genre"],
                "year": meta["year"],
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
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == '/api/library':
            self._json_response(scan_library())

        elif parsed.path == '/api/downloads':
            summary = []
            with jobs_lock:
                for j in jobs.values():
                    summary.append({
                        "id": j["id"],
                        "url": j["url"],
                        "status": j["status"],
                        "done": j["done"],
                    })
            self._json_response(summary)

        elif parsed.path.startswith('/api/download/'):
            job_id = parsed.path.split('/')[-1]
            with jobs_lock:
                job = jobs.get(job_id)
            if not job:
                self._json_response({"error": "Unknown job"}, status=404)
                return
            self._stream_job(job)

        elif parsed.path.startswith('/music/'):
            self._serve_with_ranges(parsed.path)

        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == '/api/download':
            length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            url = body.get('url', '').strip()
            if not url:
                self._json_response({"error": "Missing url"}, status=400)
                return

            job = _create_job(url)
            t = threading.Thread(target=_run_job, args=(job,), daemon=True)
            t.start()
            self._json_response({"id": job["id"], "status": "queued"})

        else:
            self.send_error(404)

    def _json_response(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def _stream_job(self, job):
        """SSE stream: sends all past events then waits for new ones."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Connection', 'keep-alive')
        self.end_headers()

        cursor = 0
        while True:
            with job["condition"]:
                # Wait for new events
                while cursor >= len(job["events"]) and not job["done"]:
                    job["condition"].wait(timeout=5)

                # Send any new events
                new_events = job["events"][cursor:]
                cursor = len(job["events"])
                done = job["done"]

            for event in new_events:
                try:
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    return

            if done:
                return

    def _serve_with_ranges(self, path):
        """Serve a file with HTTP Range support (required by Chromecast)."""
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
                range_spec = range_header.replace('bytes=', '')
                start_str, end_str = range_spec.split('-')
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
        if path.startswith('/api') or '404' in str(args):
            super().log_message(fmt, *args)


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


if __name__ == '__main__':
    os.makedirs(MUSIC_ROOT, exist_ok=True)

    print("Bootstrapping dependencies...")
    bootstrap()

    server = ThreadedHTTPServer(('0.0.0.0', PORT), Handler)
    print(f"Serving on http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
