"""Listener management — CRUD for household members.

Each listener gets personalized favorites, play history, and playlists
from a shared music library. Face recognition is optional (addon).
"""

import uuid
from datetime import datetime, timezone

from .db import _connect


def create_listener(name, music_root):
    """Create a new listener. Returns {id, name, created_at}."""
    name = (name or "").strip()
    if not name:
        raise ValueError("Listener name cannot be empty")
    if len(name) > 50:
        raise ValueError("Listener name too long (max 50 characters)")

    listener_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = _connect(music_root)
    conn.execute(
        "INSERT INTO listeners (id, name, created_at) VALUES (?, ?, ?)",
        (listener_id, name, now),
    )
    conn.commit()
    conn.close()
    return {"id": listener_id, "name": name, "created_at": now}


def list_listeners(music_root):
    """Return all listeners."""
    conn = _connect(music_root)
    rows = conn.execute(
        "SELECT id, name, created_at FROM listeners ORDER BY name"
    ).fetchall()
    conn.close()
    return [{"id": r["id"], "name": r["name"], "created_at": r["created_at"]} for r in rows]


def delete_listener(listener_id, music_root):
    """Delete a listener. CASCADE handles favorites, playlists cleaned up manually."""
    if listener_id == "guest":
        raise ValueError("Cannot delete the Guest listener")
    conn = _connect(music_root)
    # Delete playlists owned by this listener (playlist_tracks cleaned by CASCADE)
    conn.execute("DELETE FROM playlists WHERE listener_id = ?", (listener_id,))
    conn.execute("DELETE FROM listeners WHERE id = ?", (listener_id,))
    conn.commit()
    conn.close()
    return True
