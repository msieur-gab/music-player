"""Favorites — per-listener track bookmarking.

Favorites are intentional (explicit heart tap). Separate from listens
which are behavioral (passive play logging).
"""

from datetime import datetime, timezone

from .db import _connect


def add_favorite(listener_id, track_id, music_root):
    """Add a track to a listener's favorites. Idempotent."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = _connect(music_root)
    conn.execute(
        "INSERT OR IGNORE INTO favorites (listener_id, track_id, added_at) VALUES (?, ?, ?)",
        (listener_id, track_id, now),
    )
    conn.commit()
    conn.close()
    return True


def remove_favorite(listener_id, track_id, music_root):
    """Remove a track from a listener's favorites."""
    conn = _connect(music_root)
    conn.execute(
        "DELETE FROM favorites WHERE listener_id = ? AND track_id = ?",
        (listener_id, track_id),
    )
    conn.commit()
    conn.close()
    return True


def get_favorite_ids(listener_id, music_root):
    """Return list of track_ids that are favorited by this listener."""
    conn = _connect(music_root)
    rows = conn.execute(
        "SELECT track_id FROM favorites WHERE listener_id = ?", (listener_id,)
    ).fetchall()
    conn.close()
    return [r["track_id"] for r in rows]


def get_favorites_count(listener_id, music_root):
    """Return count of favorites for a listener."""
    conn = _connect(music_root)
    row = conn.execute(
        "SELECT COUNT(*) FROM favorites WHERE listener_id = ?", (listener_id,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def get_favorites_playlist(listener_id, music_root):
    """Return full track info for a listener's favorites, as a playlist."""
    import os
    conn = _connect(music_root)
    rows = conn.execute("""
        SELECT f.track_id, f.added_at, t.artist, t.album, t.title, t.file
        FROM favorites f
        LEFT JOIN tracks t ON t.track_id = f.track_id
        WHERE f.listener_id = ?
        ORDER BY f.added_at DESC
    """, (listener_id,)).fetchall()
    conn.close()

    cover_cache = {}
    tracks = []
    for r in rows:
        if not r["artist"]:
            continue
        a, alb = r["artist"], r["album"]
        if (a, alb) not in cover_cache:
            cover_path = os.path.join(music_root, a, alb, "cover.jpg")
            cover_cache[(a, alb)] = (
                f"/music/{a}/{alb}/cover.jpg"
                if os.path.isfile(cover_path) else None
            )
        tracks.append({
            "key": r["track_id"],
            "artist": a,
            "album": alb,
            "title": r["title"],
            "file": r["file"],
            "cover": cover_cache[(a, alb)],
            "url": f"/music/{r['file']}",
        })
    return tracks
