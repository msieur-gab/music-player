"""Playlist generation and saved playlists CRUD.

Zone playlists are generated on the fly from scoring. Saved playlists
are persisted in SQLite for user bookmarking.
"""

import json
import os

from .db import _connect
from .profiles import CONTEXT_PROFILES
from .scoring import score_all_tracks, cosine


# Classifier keys used for diversity vector in MMR
_CLS_VEC_KEYS = [
    "arousal", "valence", "happy", "sad", "relaxed", "aggressive",
    "danceable", "energetic", "hypnotic", "instrumental",
    "brilliant", "radiant", "contemplative",
]


# ---------------------------------------------------------------------------
# Zone queries -- computed on the fly
# ---------------------------------------------------------------------------

def get_zones(music_root):
    """Return context/zone summaries with track counts (computed live)."""
    conn = _connect(music_root)
    scored = score_all_tracks(conn)
    conn.close()

    counts = {ctx_id: 0 for ctx_id in CONTEXT_PROFILES}
    best = {ctx_id: 0.0 for ctx_id in CONTEXT_PROFILES}
    for _, scores in scored:
        for ctx_id, score in scores.items():
            if score > best[ctx_id]:
                best[ctx_id] = score

    for _, scores in scored:
        for ctx_id, score in scores.items():
            threshold = best[ctx_id] * 0.90
            if score >= threshold:
                counts[ctx_id] += 1

    return [{
        "id": ctx_id,
        "group": profile["group"],
        "label": profile["label"],
        "desc": profile["desc"],
        "trackCount": counts[ctx_id],
    } for ctx_id, profile in CONTEXT_PROFILES.items()]


def generate_playlist(zone_id, music_root, limit=25, artist=None, album=None):
    """Generate a playlist for a context zone.

    Scores all tracks against the profile on the fly, then orders
    using MMR (Maximal Marginal Relevance) for diversity.
    """
    if zone_id not in CONTEXT_PROFILES:
        return []

    conn = _connect(music_root)
    scored = score_all_tracks(conn)
    conn.close()

    raw_candidates = []
    for row, scores in scored:
        if artist and row["artist"] != artist:
            continue
        if album and row["album"] != album:
            continue
        zone_score = scores.get(zone_id, 0)
        cls = json.loads(row["cls_json"]) if row["cls_json"] else {}
        raw_candidates.append((zone_score, row, cls))

    if not raw_candidates:
        return []

    best_score = max(s for s, _, _ in raw_candidates)
    threshold = best_score * 0.90

    candidates = []
    for zone_score, row, cls in raw_candidates:
        if zone_score < threshold:
            continue
        # Build diversity vector from classifier outputs
        vec = [cls.get(k, 0.5) for k in _CLS_VEC_KEYS]
        candidates.append({
            "score": zone_score,
            "key": row["track_id"],
            "artist": row["artist"],
            "album": row["album"],
            "title": row["title"],
            "file": row["file"],
            "vec": vec,
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    ordered = candidates[:limit]

    cover_cache = {}
    result = []
    for c in ordered:
        a, alb = c["artist"], c["album"]
        if (a, alb) not in cover_cache:
            cover_path = os.path.join(music_root, a, alb, "cover.jpg")
            cover_cache[(a, alb)] = (
                f"/music/{a}/{alb}/cover.jpg"
                if os.path.isfile(cover_path) else None
            )
        result.append({
            "key": c["key"],
            "artist": a,
            "album": alb,
            "title": c["title"],
            "file": c["file"],
            "cover": cover_cache[(a, alb)],
            "score": c["score"],
            "url": f"/music/{c['file']}",
        })

    return result


def _mmr_order(candidates, target_vec, limit, diversity=0.3):
    """Maximal Marginal Relevance: balance relevance with diversity."""
    if not candidates:
        return []

    ordered = [candidates[0]]
    remaining = list(candidates[1:])

    while remaining and len(ordered) < limit:
        best_idx = 0
        best_mmr = -1

        recent_artists = {c["artist"] for c in ordered[-3:]}
        recent_albums = {c["album"] for c in ordered[-3:]}

        for i, cand in enumerate(remaining):
            relevance = cosine(cand["vec"], target_vec)
            max_sim = max(cosine(cand["vec"], sel["vec"]) for sel in ordered)
            mmr = (1 - diversity) * relevance - diversity * max_sim

            if cand["artist"] in recent_artists:
                mmr *= 0.4
            elif cand["album"] in recent_albums:
                mmr *= 0.6

            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i

        ordered.append(remaining.pop(best_idx))

    return ordered


# ---------------------------------------------------------------------------
# Saved playlists -- CRUD
# ---------------------------------------------------------------------------

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
        "zoneLabel": CONTEXT_PROFILES.get(r["zone_id"], {}).get("label", ""),
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

    rows = conn.execute("""
        SELECT pt.position, t.track_id, t.artist, t.album, t.title, t.file
        FROM playlist_tracks pt
        LEFT JOIN tracks t ON t.track_id = pt.track_key
        WHERE pt.playlist_id = ?
        ORDER BY pt.position
    """, (playlist_id,)).fetchall()
    conn.close()

    cover_cache = {}
    tracks = []
    for r in rows:
        if not r["track_id"]:
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

    zone = CONTEXT_PROFILES.get(playlist["zone_id"], {})
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
