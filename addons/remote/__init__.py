"""Remote Control addon — per-listener command channel between phone and browser."""

import json
import threading
from urllib.parse import urlparse, parse_qs

_subscribers_lock = threading.Lock()
_subscribers = []  # list of (condition, queue, listener_id)


def register(ctx):
    """Register command routes for the remote control addon."""
    return {
        "POST": {
            "/api/remote/command": _handle_command,
        },
        "GET": {
            "/api/remote/commands": _stream_commands,
        },
    }


def _handle_command(handler):
    """Receive {action, value} from phone, deliver to matching listener's SSE subscribers only."""
    length = int(handler.headers.get('Content-Length', 0))
    body = json.loads(handler.rfile.read(length)) if length else {}

    # Read listener_id from header
    lid = handler.headers.get('X-Listener-Id', 'guest')

    with _subscribers_lock:
        for cond, queue, sub_lid in _subscribers:
            if sub_lid == lid:
                with cond:
                    queue.append(body)
                    cond.notify()

    handler.send_response(200)
    handler.send_header('Content-Type', 'application/json')
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.send_header('Access-Control-Allow-Headers', '*')
    resp = json.dumps({"ok": True}).encode()
    handler.send_header('Content-Length', len(resp))
    handler.end_headers()
    handler.wfile.write(resp)


def _stream_commands(handler):
    """SSE stream: per-subscriber queue tagged with listener_id, keepalive every 30s."""
    handler.send_response(200)
    handler.send_header('Content-Type', 'text/event-stream')
    handler.send_header('Cache-Control', 'no-cache')
    handler.send_header('Connection', 'keep-alive')
    handler.end_headers()

    # Read listener_id from query param (EventSource can't set headers)
    qs = parse_qs(urlparse(handler.path).query)
    lid = qs.get('listener', ['guest'])[0]

    cond = threading.Condition()
    queue = []
    entry = (cond, queue, lid)
    with _subscribers_lock:
        _subscribers.append(entry)

    try:
        while True:
            with cond:
                cond.wait(timeout=30)
                cmds = queue[:]
                queue.clear()

            if cmds:
                for cmd in cmds:
                    handler.wfile.write(f"data: {json.dumps(cmd)}\n\n".encode())
                    handler.wfile.flush()
            else:
                # Keepalive — flushes dead connections fast
                handler.wfile.write(b": keepalive\n\n")
                handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError):
        pass
    finally:
        with _subscribers_lock:
            try:
                _subscribers.remove(entry)
            except ValueError:
                pass
