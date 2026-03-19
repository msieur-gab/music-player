"""Chromecast addon — cast music to Chromecast devices (per-listener sessions)."""

from .cast_manager import CastManager

_cast_mgr = None


def register(ctx):
    """Initialize Chromecast discovery and return route table."""
    global _cast_mgr
    _cast_mgr = CastManager(port=ctx["port"], get_lan_ip=ctx["get_lan_ip"])

    print("Discovering Chromecast devices...")
    _cast_mgr.start_discovery()

    return {
        "GET": {
            "/api/devices": _handle_devices,
            "/api/status": _handle_status,
        },
        "POST": {
            "/api/cast": _handle_cast,
            "/api/control": _handle_control,
        },
    }


def shutdown():
    """Stop Chromecast discovery."""
    if _cast_mgr:
        _cast_mgr.stop()


def _get_listener_id(handler):
    """Extract listener ID from request header."""
    return handler.headers.get('X-Listener-Id', 'guest')


# -- Route handlers --

def _handle_devices(handler):
    handler._json(_cast_mgr.list_devices())


def _handle_status(handler):
    lid = _get_listener_id(handler)
    handler._json(_cast_mgr.get_status(listener_id=lid))


def _handle_cast(handler):
    body = handler._read_body()
    device_id = body.get("deviceId")
    if not device_id:
        handler._json({"error": "Missing deviceId"}, 400)
        return
    lid = _get_listener_id(handler)
    result = _cast_mgr.cast(
        device_id, body.get("track", {}),
        body.get("queue"), body.get("queueIndex", 0),
        body.get("baseUrl"),
        listener_id=lid,
    )
    handler._json(result)


def _handle_control(handler):
    body = handler._read_body()
    action = body.get("action")
    if not action:
        handler._json({"error": "Missing action"}, 400)
        return
    lid = _get_listener_id(handler)
    handler._json(_cast_mgr.control(action, body.get("value"), listener_id=lid))
