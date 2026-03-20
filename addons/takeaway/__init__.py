"""Takeaway addon — build a music basket and serve it to phones via QR code."""

import json
import os
import secrets
import threading
import time
from urllib.parse import urlparse, parse_qs, unquote

_baskets = {}          # id → {tracks, created, expires}
_baskets_lock = threading.Lock()
_EXPIRY = 3 * 3600    # baskets live 3 hours

_ctx = None


def register(ctx):
    global _ctx
    _ctx = ctx
    return {
        "POST": {
            "/api/takeaway/basket": _create_basket,
        },
        "GET": {
            "/api/takeaway/basket/*": _get_basket,
            "/api/takeaway/track/*": _serve_track,
        },
        "DELETE": {
            "/api/takeaway/basket/*": _delete_basket,
        },
    }


def _purge_expired():
    now = time.time()
    with _baskets_lock:
        expired = [k for k, v in _baskets.items() if now > v['expires']]
        for k in expired:
            del _baskets[k]


def _create_basket(handler):
    """Create a new basket from a list of tracks."""
    _purge_expired()
    length = int(handler.headers.get('Content-Length', 0))
    body = json.loads(handler.rfile.read(length)) if length else {}

    tracks = body.get('tracks', [])
    if not tracks:
        handler.send_response(400)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": "no tracks"}).encode())
        return

    basket_id = secrets.token_urlsafe(8)
    now = time.time()

    with _baskets_lock:
        _baskets[basket_id] = {
            'tracks': tracks,
            'created': now,
            'expires': now + _EXPIRY,
        }

    handler.send_response(201)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    resp = json.dumps({"id": basket_id}).encode()
    handler.send_header('Content-Length', len(resp))
    handler.end_headers()
    handler.wfile.write(resp)


def _get_basket(handler, path):
    """Return basket manifest (track list with metadata)."""
    basket_id = path.split('/')[-1]

    with _baskets_lock:
        basket = _baskets.get(basket_id)

    if not basket or time.time() > basket['expires']:
        handler.send_response(404)
        handler.send_header('Content-Type', 'application/json')
        handler.end_headers()
        handler.wfile.write(json.dumps({"error": "basket not found or expired"}).encode())
        return

    handler.send_response(200)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    resp = json.dumps({"tracks": basket['tracks']}).encode()
    handler.send_header('Content-Length', len(resp))
    handler.end_headers()
    handler.wfile.write(resp)


def _delete_basket(handler, path):
    """Delete a basket."""
    basket_id = path.split('/')[-1]

    with _baskets_lock:
        removed = _baskets.pop(basket_id, None)

    handler.send_response(200 if removed else 404)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    resp = json.dumps({"ok": bool(removed)}).encode()
    handler.send_header('Content-Length', len(resp))
    handler.end_headers()
    handler.wfile.write(resp)


def _serve_track(handler, path):
    """Serve an m4a file for download. Path: /api/takeaway/track/{basket_id}/{artist}/{album}/{file}"""
    # path = /api/takeaway/track/{basket_id}/artist/album/file.m4a
    parts = path.split('/', 5)  # ['', 'api', 'takeaway', 'track', basket_id, 'artist/album/file']
    if len(parts) < 6:
        handler.send_response(400)
        handler.end_headers()
        return

    basket_id = parts[4]
    rel_path = unquote(parts[5])  # URL-decode: artist/album/file.m4a

    # Verify basket exists and track is in it
    with _baskets_lock:
        basket = _baskets.get(basket_id)

    if not basket or time.time() > basket['expires']:
        handler.send_response(404)
        handler.end_headers()
        return

    # Check the requested file belongs to this basket
    allowed = any(t.get('file') == rel_path for t in basket['tracks'])
    if not allowed:
        handler.send_response(403)
        handler.end_headers()
        return

    music_root = _ctx['get_music_root']()
    file_path = os.path.join(music_root, rel_path)
    file_path = os.path.realpath(file_path)

    # Prevent path traversal
    if not file_path.startswith(os.path.realpath(music_root)):
        handler.send_response(403)
        handler.end_headers()
        return

    if not os.path.isfile(file_path):
        handler.send_response(404)
        handler.end_headers()
        return

    size = os.path.getsize(file_path)
    range_header = handler.headers.get('Range')

    if range_header:
        # Support range requests for seeking
        byte_range = range_header.replace('bytes=', '').split('-')
        start = int(byte_range[0])
        end = int(byte_range[1]) if byte_range[1] else size - 1
        length = end - start + 1

        handler.send_response(206)
        handler.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        handler.send_header('Content-Length', length)
    else:
        start = 0
        length = size
        handler.send_response(200)
        handler.send_header('Content-Length', size)

    handler.send_header('Content-Type', 'audio/mp4')
    handler.send_header('Accept-Ranges', 'bytes')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Cache-Control', 'public, max-age=3600')
    handler.end_headers()

    with open(file_path, 'rb') as f:
        f.seek(start)
        remaining = length
        while remaining > 0:
            chunk = f.read(min(65536, remaining))
            if not chunk:
                break
            handler.wfile.write(chunk)
            remaining -= len(chunk)
