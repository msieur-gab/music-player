#!/usr/bin/env python3
"""Music analysis — context-based classification and playlist generation.

Classification is computed on demand from stored features — never persisted.
Changing a context profile takes effect immediately, no re-analysis needed.

Architecture:
  db.py        → SQLite schema, connection, track storage (features only)
  extractor.py → librosa feature extraction (multi-point sampling)
  analyzer.py  → classification, playlists, library scanning (this file)
"""

import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

from db import (
    _connect, FEATURE_COLS, PROFILE_FEATURES,
    insert_track, update_norm_ranges, get_norm_ranges,
)
from extractor import extract_track_features


# ---------------------------------------------------------------------------
# Context profiles — target vectors for cosine similarity
# Values are normalized 0-1 (0 = library min, 1 = library max)
# ---------------------------------------------------------------------------

CONTEXT_PROFILES = {
    # ═══ Activities — mapped to brainwave states ═══
    "focus": {
        "group": "activity",
        "label": "Deep Focus",
        "desc": "Bright, dynamic, tonal — sustained cognitive alertness",
        "target": {
            "tempo": 0.50, "rms_mean": 0.60, "dynamic_range": 0.35,
            "centroid_mean": 0.70, "flatness_mean": 0.25, "spectral_flux": 0.60,
            "onset_strength": 0.50, "beat_strength": 0.50,
            "rms_variance": 0.25, "vocal_proxy": 0.30,
        },
    },
    "creative": {
        "group": "activity",
        "label": "Creative Flow",
        "desc": "Balanced, harmonic, fluid — relaxed alertness",
        "target": {
            "tempo": 0.40, "rms_mean": 0.45, "dynamic_range": 0.50,
            "centroid_mean": 0.50, "flatness_mean": 0.25, "spectral_flux": 0.40,
            "onset_strength": 0.40, "beat_strength": 0.40,
            "rms_variance": 0.40, "vocal_proxy": 0.40,
        },
    },
    "meditation": {
        "group": "activity",
        "label": "Meditation",
        "desc": "Warm, still, organic — theta state, inner quiet",
        "target": {
            "tempo": 0.15, "rms_mean": 0.20, "dynamic_range": 0.60,
            "centroid_mean": 0.20, "flatness_mean": 0.40, "spectral_flux": 0.10,
            "onset_strength": 0.10, "beat_strength": 0.10,
            "rms_variance": 0.20, "vocal_proxy": 0.15,
        },
    },
    "energize": {
        "group": "activity",
        "label": "Energy",
        "desc": "Loud, bright, driving — get moving",
        "target": {
            "tempo": 0.80, "rms_mean": 0.80, "dynamic_range": 0.25,
            "centroid_mean": 0.80, "flatness_mean": 0.50, "spectral_flux": 0.80,
            "onset_strength": 0.80, "beat_strength": 0.80,
            "rms_variance": 0.25, "vocal_proxy": 0.60,
        },
    },
    "sleep": {
        "group": "activity",
        "label": "Sleep",
        "desc": "Dark, filtered, barely there — drift off",
        "target": {
            "tempo": 0.10, "rms_mean": 0.10, "dynamic_range": 0.50,
            "centroid_mean": 0.10, "flatness_mean": 0.50, "spectral_flux": 0.05,
            "onset_strength": 0.05, "beat_strength": 0.05,
            "rms_variance": 0.10, "vocal_proxy": 0.10,
        },
    },

    # ═══ Moods — Russell's Circumplex (arousal x valence) ═══
    "joy": {
        "group": "mood",
        "label": "Joy",
        "desc": "Bright, rhythmic, tonal — euphoric and uplifting",
        "target": {
            "tempo": 0.70, "rms_mean": 0.60, "dynamic_range": 0.35,
            "centroid_mean": 0.70, "flatness_mean": 0.20, "spectral_flux": 0.60,
            "onset_strength": 0.60, "beat_strength": 0.70,
            "rms_variance": 0.30, "vocal_proxy": 0.50,
        },
    },
    "calm": {
        "group": "mood",
        "label": "Calm",
        "desc": "Warm, steady, clear — unwind and breathe",
        "target": {
            "tempo": 0.30, "rms_mean": 0.30, "dynamic_range": 0.55,
            "centroid_mean": 0.30, "flatness_mean": 0.25, "spectral_flux": 0.20,
            "onset_strength": 0.20, "beat_strength": 0.25,
            "rms_variance": 0.25, "vocal_proxy": 0.30,
        },
    },
    "melancholy": {
        "group": "mood",
        "label": "Melancholy",
        "desc": "Dark, slow, intimate — sit with the feeling",
        "target": {
            "tempo": 0.30, "rms_mean": 0.35, "dynamic_range": 0.50,
            "centroid_mean": 0.30, "flatness_mean": 0.20, "spectral_flux": 0.25,
            "onset_strength": 0.20, "beat_strength": 0.20,
            "rms_variance": 0.40, "vocal_proxy": 0.50,
        },
    },
    "heroic": {
        "group": "mood",
        "label": "Heroic",
        "desc": "Bold, sweeping, tonal — brass and conviction",
        "target": {
            "tempo": 0.55, "rms_mean": 0.70, "dynamic_range": 0.45,
            "centroid_mean": 0.60, "flatness_mean": 0.20, "spectral_flux": 0.55,
            "onset_strength": 0.50, "beat_strength": 0.55,
            "rms_variance": 0.45, "vocal_proxy": 0.40,
        },
    },
    "mysterious": {
        "group": "mood",
        "label": "Mysterious",
        "desc": "Dark, textured, noisy — shadows and atmosphere",
        "target": {
            "tempo": 0.30, "rms_mean": 0.30, "dynamic_range": 0.55,
            "centroid_mean": 0.25, "flatness_mean": 0.70, "spectral_flux": 0.30,
            "onset_strength": 0.20, "beat_strength": 0.15,
            "rms_variance": 0.50, "vocal_proxy": 0.30,
        },
    },

    # ═══ Support — therapeutic profiles ═══
    "stress_relief": {
        "group": "support",
        "label": "Stress Relief",
        "desc": "Warm, predictable, spacious — let the nervous system settle",
        "target": {
            "tempo": 0.25, "rms_mean": 0.30, "dynamic_range": 0.55,
            "centroid_mean": 0.30, "flatness_mean": 0.35, "spectral_flux": 0.15,
            "onset_strength": 0.15, "beat_strength": 0.20,
            "rms_variance": 0.20, "vocal_proxy": 0.20,
        },
    },
    "recovery": {
        "group": "support",
        "label": "Recovery",
        "desc": "Filtered, ambient, gentle — physiological restoration",
        "target": {
            "tempo": 0.15, "rms_mean": 0.15, "dynamic_range": 0.55,
            "centroid_mean": 0.20, "flatness_mean": 0.45, "spectral_flux": 0.10,
            "onset_strength": 0.10, "beat_strength": 0.10,
            "rms_variance": 0.15, "vocal_proxy": 0.10,
        },
    },
}


# ---------------------------------------------------------------------------
# Classification — computed on demand, never stored
# ---------------------------------------------------------------------------

def classify_track(features, norm_ranges):
    """Score a track against each context profile. Returns {zone_id: score}."""
    track_vec = _normalize_vec(features, norm_ranges)
    scores = {}
    for ctx_id, profile in CONTEXT_PROFILES.items():
        target_vec = [profile["target"].get(f, 0.5) for f in PROFILE_FEATURES]
        scores[ctx_id] = round(_cosine(track_vec, target_vec), 4)
    return scores


def _score_all_tracks(conn):
    """Score every track against every profile. Returns [(row, {zone: score}), ...]."""
    ranges = get_norm_ranges(conn)
    rows = conn.execute(
        "SELECT track_id, artist, album, title, file, "
        + ", ".join(FEATURE_COLS)
        + " FROM tracks"
    ).fetchall()

    scored = []
    for row in rows:
        feats = {f: row[f] for f in FEATURE_COLS}
        scores = classify_track(feats, ranges)
        scored.append((row, scores))
    return scored


# ---------------------------------------------------------------------------
# Library analysis — extraction only, no classification stored
# ---------------------------------------------------------------------------

def analyze_library(music_root, on_progress=None, workers=4):
    """Analyze all MP3s: extract features with librosa (parallel)."""
    conn = _connect(music_root)
    existing = {row[0] for row in conn.execute("SELECT track_id FROM tracks").fetchall()}

    mp3s = _find_mp3s(music_root)
    total = len(mp3s)
    skipped = 0

    work = []
    for path in mp3s:
        artist, album, title = _info_from_path(path, music_root)
        track_id = f"{artist}::{album}::{title}"
        if track_id in existing:
            skipped += 1
        else:
            work.append((path, artist, album, title, track_id))

    if on_progress:
        on_progress({
            "message": f"Extracting features: {len(work)} tracks "
                       f"({skipped} cached, {workers} workers)",
            "track": 0, "total": total, "status": "analyzing",
        })

    done = 0
    analyzed = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_track_features, item[0]): item for item in work}
        for future in as_completed(futures):
            done += 1
            path, artist, album, title, track_id = futures[future]
            try:
                feats = future.result()
                if feats:
                    insert_track(
                        conn, track_id, artist, album, title,
                        os.path.relpath(path, music_root), feats,
                    )
                    analyzed += 1
            except Exception as e:
                print(f"  Error extracting {title}: {e}")

            if on_progress:
                on_progress({
                    "message": f"Extracted {done}/{len(work)}: {title}",
                    "track": skipped + done, "total": total, "status": "analyzing",
                })

    # Update normalization ranges after new tracks added
    update_norm_ranges(conn)
    conn.close()

    if on_progress:
        on_progress({
            "message": f"Done — {analyzed} new tracks ({skipped} cached)",
            "analyzed": analyzed, "skipped": skipped, "total": total,
            "status": "complete",
        })


# ---------------------------------------------------------------------------
# Zone queries — computed on the fly
# ---------------------------------------------------------------------------

def get_zones(music_root):
    """Return context/zone summaries with track counts (computed live)."""
    conn = _connect(music_root)
    scored = _score_all_tracks(conn)
    conn.close()

    counts = {ctx_id: 0 for ctx_id in CONTEXT_PROFILES}
    for _, scores in scored:
        for ctx_id, score in scores.items():
            if score >= 0.5:
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
    Optional artist/album filters narrow the pool before scoring.
    """
    if zone_id not in CONTEXT_PROFILES:
        return []

    conn = _connect(music_root)
    scored = _score_all_tracks(conn)
    ranges = get_norm_ranges(conn)
    conn.close()

    # Filter and sort by zone score
    candidates = []
    for row, scores in scored:
        if artist and row["artist"] != artist:
            continue
        if album and row["album"] != album:
            continue
        zone_score = scores.get(zone_id, 0)
        if zone_score < 0.4:
            continue
        feats = {f: row[f] for f in FEATURE_COLS}
        candidates.append({
            "score": zone_score,
            "key": row["track_id"],
            "artist": row["artist"],
            "album": row["album"],
            "title": row["title"],
            "file": row["file"],
            "vec": _normalize_vec(feats, ranges),
        })

    candidates.sort(key=lambda c: c["score"], reverse=True)
    candidates = candidates[:limit * 3]  # cap for MMR performance

    # MMR ordering for diversity
    target_vec = [
        CONTEXT_PROFILES[zone_id]["target"].get(f, 0.5) for f in PROFILE_FEATURES
    ]
    ordered = _mmr_order(candidates, target_vec, limit)

    # Build result with covers
    cover_cache = {}
    result = []
    for c in ordered:
        artist, album = c["artist"], c["album"]
        if (artist, album) not in cover_cache:
            cover_path = os.path.join(music_root, artist, album, "cover.jpg")
            cover_cache[(artist, album)] = (
                f"/music/{artist}/{album}/cover.jpg"
                if os.path.isfile(cover_path) else None
            )
        result.append({
            "key": c["key"],
            "artist": artist,
            "album": album,
            "title": c["title"],
            "file": c["file"],
            "cover": cover_cache[(artist, album)],
            "score": c["score"],
            "url": f"/music/{c['file']}",
        })

    return result


def _mmr_order(candidates, target_vec, limit, diversity=0.3):
    """Maximal Marginal Relevance: balance relevance with diversity.

    Also penalizes consecutive same-artist/album runs.
    """
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
            relevance = _cosine(cand["vec"], target_vec)
            max_sim = max(_cosine(cand["vec"], sel["vec"]) for sel in ordered)
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
# Similarity
# ---------------------------------------------------------------------------

def find_similar(track_id, music_root, limit=10):
    """Find tracks most similar to the given one.

    Builds a full feature vector from:
      - 10 normalized profile features (tempo, energy, dynamics, etc.)
      - 13 MFCC means (timbral identity — what it "sounds like")
      - 13 MFCC stds (timbral consistency)
      - 7 spectral contrast bands (harmonic structure)

    Total: 43 dimensions scored via cosine similarity.
    """
    import json as _json

    conn = _connect(music_root)
    target_row = conn.execute(
        "SELECT * FROM tracks WHERE track_id = ?", (track_id,)
    ).fetchone()
    if not target_row:
        conn.close()
        return []

    ranges = get_norm_ranges(conn)
    rows = conn.execute(
        "SELECT * FROM tracks WHERE track_id != ?", (track_id,)
    ).fetchall()
    conn.close()

    def _full_vec(row):
        """Build full similarity vector: profile features + MFCC + contrast."""
        # Normalized scalar features
        vec = []
        for f in PROFILE_FEATURES:
            r = ranges.get(f, [0, 0])
            lo, hi = r[0], r[1]
            val = row[f] if row[f] is not None else 0
            vec.append((val - lo) / (hi - lo) if hi > lo else 0.5)

        # MFCC mean (13 dims) — the timbral fingerprint
        mfcc_mean = row["mfcc_mean_json"]
        if isinstance(mfcc_mean, str):
            mfcc_mean = _json.loads(mfcc_mean)
        vec.extend(mfcc_mean or [0] * 13)

        # MFCC std (13 dims) — timbral consistency
        mfcc_std = row["mfcc_std_json"]
        if isinstance(mfcc_std, str):
            mfcc_std = _json.loads(mfcc_std)
        vec.extend(mfcc_std or [0] * 13)

        # Spectral contrast (7 dims) — harmonic structure
        contrast = row["contrast_mean_json"]
        if isinstance(contrast, str):
            contrast = _json.loads(contrast)
        vec.extend(contrast or [0] * 7)

        return vec

    target_vec = _full_vec(target_row)

    results = []
    for row in rows:
        vec = _full_vec(row)
        score = _cosine(target_vec, vec)
        results.append({
            "key": row["track_id"],
            "artist": row["artist"],
            "album": row["album"],
            "title": row["title"],
            "file": row["file"],
            "score": round(score, 4),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_vec(features, ranges):
    """Convert raw features to 0-1 vector using library min-max ranges."""
    vec = []
    for f in PROFILE_FEATURES:
        r = ranges.get(f, [0, 0])
        lo, hi = r[0], r[1]
        val = features.get(f, 0)
        vec.append((val - lo) / (hi - lo) if hi > lo else 0.5)
    return vec


def _cosine(a, b):
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0


def _find_mp3s(music_root):
    """Walk the music directory and return sorted list of MP3 paths."""
    mp3s = []
    for root, _, files in os.walk(music_root):
        for f in sorted(files):
            if f.lower().endswith(".mp3") and not f.startswith("_temp_"):
                mp3s.append(os.path.join(root, f))
    return mp3s


def _info_from_path(filepath, music_root):
    """Derive artist/album/title from path: root/Artist/Album/01 - Title.mp3"""
    rel = os.path.relpath(filepath, music_root)
    parts = rel.replace("\\", "/").split("/")
    artist = parts[0] if len(parts) >= 3 else "Unknown"
    album = parts[1] if len(parts) >= 3 else (parts[0] if len(parts) >= 2 else "Unknown")
    fname = os.path.splitext(parts[-1])[0]
    m = re.match(r"^\d+\s*[-\u2013]\s*(.+)$", fname)
    title = m.group(1).strip() if m else fname
    return artist, album, title


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def migrate_from_json(music_root):
    """Legacy cleanup — remove old JSON feature files."""
    for suffix in ("", ".bak"):
        path = os.path.join(music_root, f".audio_features.json{suffix}")
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <music_root>")
        print(f"       {sys.argv[0]} --similar <music_root> 'Artist::Album::Title'")
        sys.exit(1)

    if sys.argv[1] == "--similar" and len(sys.argv) >= 4:
        root = sys.argv[2]
        key = sys.argv[3]
        results = find_similar(key, root)
        for r in results:
            print(f"  {r['score']:.3f}  {r['artist']} — {r['title']}")
    else:
        root = sys.argv[1]
        print(f"Analyzing library: {root}")
        analyze_library(root, on_progress=lambda d: print(f"  {d['message']}"))
        print("Done.")
