"""
Saved playlists — CRUD operations for user-saved zone playlists.
Uses the same SQLite database as the analyzer.
"""

import os
from analyzer import _connect, ZONES


def save_playlist(name, zone_id, track_keys, music_root):
    """Save a playlist. track_keys is a list of 'artist::album::title' keys."""
    conn = _connect(music_root)
    cur = conn.execute(
        "INSERT INTO playlists (name, zone_id) VALUES (?, ?)",
        (name, zone_id),
    )
    playlist_id = cur.lastrowid

    for i, key in enumerate(track_keys):
        conn.execute(
            "INSERT INTO playlist_tracks (playlist_id, position, track_key) VALUES (?, ?, ?)",
            (playlist_id, i, key),
        )

    conn.commit()
    conn.close()
    return playlist_id


def list_playlists(music_root):
    """Return all saved playlists with track counts."""
    conn = _connect(music_root)
    rows = conn.execute("""
        SELECT p.id, p.name, p.zone_id, p.created_at, COUNT(pt.track_key) as track_count
        FROM playlists p
        LEFT JOIN playlist_tracks pt ON pt.playlist_id = p.id
        GROUP BY p.id
        ORDER BY p.created_at DESC
    """).fetchall()
    conn.close()

    return [{
        "id": r["id"],
        "name": r["name"],
        "zone": r["zone_id"],
        "zoneLabel": ZONES.get(r["zone_id"], {}).get("label", ""),
        "trackCount": r["track_count"],
        "createdAt": r["created_at"],
    } for r in rows]


def get_playlist(playlist_id, music_root):
    """Return a saved playlist with full track info."""
    conn = _connect(music_root)

    playlist = conn.execute(
        "SELECT * FROM playlists WHERE id = ?", (playlist_id,)
    ).fetchone()
    if not playlist:
        conn.close()
        return None

    # Join with tracks table to get full info — LEFT JOIN to handle deleted tracks
    rows = conn.execute("""
        SELECT pt.position, t.key, t.artist, t.album, t.title, t.file
        FROM playlist_tracks pt
        LEFT JOIN tracks t ON t.key = pt.track_key
        WHERE pt.playlist_id = ?
        ORDER BY pt.position
    """, (playlist_id,)).fetchall()
    conn.close()

    # Build track list, resolve covers, skip deleted tracks
    cover_cache = {}
    tracks = []
    for r in rows:
        if not r["key"]:
            continue
        artist, album = r["artist"], r["album"]
        if (artist, album) not in cover_cache:
            cover_path = os.path.join(music_root, artist, album, "cover.jpg")
            cover_cache[(artist, album)] = (
                f"/music/{artist}/{album}/cover.jpg"
                if os.path.isfile(cover_path) else None
            )
        tracks.append({
            "key": r["key"],
            "artist": artist,
            "album": album,
            "title": r["title"],
            "file": r["file"],
            "cover": cover_cache[(artist, album)],
            "url": f"/music/{r['file']}",
        })

    zone = ZONES.get(playlist["zone_id"], {})
    return {
        "id": playlist["id"],
        "name": playlist["name"],
        "zone": playlist["zone_id"],
        "zoneLabel": zone.get("label", ""),
        "zoneDesc": zone.get("desc", ""),
        "trackCount": len(tracks),
        "createdAt": playlist["created_at"],
        "tracks": tracks,
    }


def delete_playlist(playlist_id, music_root):
    """Delete a saved playlist. CASCADE handles track rows."""
    conn = _connect(music_root)
    conn.execute("DELETE FROM playlists WHERE id = ?", (playlist_id,))
    conn.commit()
    conn.close()
    return True
