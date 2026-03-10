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
from concurrent.futures import ProcessPoolExecutor, as_completed

from db import (
    _connect, FEATURE_COLS, PROFILE_FEATURES,
    insert_track, update_norm_ranges, get_norm_ranges,
)
from extractor import extract_track_features
from tags import read_tag, write_tag, has_current_tag, CURRENT_VERSION


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
    """Score a track against each context profile. Returns {zone_id: score}.

    Uses inverse Euclidean distance on normalized 0-1 vectors.
    Score = 1 / (1 + dist), so 1.0 = perfect match, ~0 = far away.
    This gives much better separation than cosine on short positive vectors.
    """
    track_vec = _normalize_vec(features, norm_ranges)
    scores = {}
    for ctx_id, profile in CONTEXT_PROFILES.items():
        target_vec = [profile["target"].get(f, 0.5) for f in PROFILE_FEATURES]
        dist = sum((a - b) ** 2 for a, b in zip(track_vec, target_vec)) ** 0.5
        scores[ctx_id] = round(1.0 / (1.0 + dist), 4)
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
    """Analyze audio files: read from tags when available, extract with librosa otherwise."""
    conn = _connect(music_root)
    existing = {row[0] for row in conn.execute("SELECT track_id FROM tracks").fetchall()}

    audio_files = _find_audio_files(music_root)
    total = len(audio_files)
    skipped = 0
    from_tags = 0

    work = []
    for path in audio_files:
        artist, album, title = _info_from_path(path, music_root)
        track_id = f"{artist}::{album}::{title}"
        if track_id in existing:
            skipped += 1
            continue

        # Try reading features from the file's embedded tag
        feats, version = read_tag(path)
        if feats and version == CURRENT_VERSION:
            insert_track(
                conn, track_id, artist, album, title,
                os.path.relpath(path, music_root), feats,
            )
            from_tags += 1
        else:
            work.append((path, artist, album, title, track_id))

    if on_progress:
        on_progress({
            "message": f"Loaded {from_tags} from tags, extracting {len(work)} tracks "
                       f"({skipped} in DB, {workers} workers)",
            "track": 0, "total": total, "status": "analyzing",
        })

    done = 0
    analyzed = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
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
                    # Write features back to the file's tag for next time
                    write_tag(path, feats)
                    analyzed += 1
            except Exception as e:
                print(f"  Error extracting {title}: {e}")

            if on_progress:
                on_progress({
                    "message": f"Extracted {done}/{len(work)}: {title}",
                    "track": skipped + from_tags + done, "total": total,
                    "status": "analyzing",
                })

    # Update normalization ranges after new tracks added
    update_norm_ranges(conn)
    conn.close()

    if on_progress:
        on_progress({
            "message": f"Done — {from_tags} from tags, {analyzed} extracted ({skipped} cached)",
            "analyzed": analyzed, "from_tags": from_tags,
            "skipped": skipped, "total": total,
            "status": "complete",
        })


# ---------------------------------------------------------------------------
# Zone queries — computed on the fly
# ---------------------------------------------------------------------------

def get_zones(music_root):
    """Return context/zone summaries with track counts (computed live).

    """
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

    # Collect all scores, then set threshold relative to top score.
    # Only include tracks within 75% of the best score for this zone,
    # so weak zones get shorter playlists instead of padding with poor fits.
    raw_candidates = []
    for row, scores in scored:
        if artist and row["artist"] != artist:
            continue
        if album and row["album"] != album:
            continue
        zone_score = scores.get(zone_id, 0)
        feats = {f: row[f] for f in FEATURE_COLS}
        raw_candidates.append((zone_score, row, feats))

    if not raw_candidates:
        return []

    best_score = max(s for s, _, _ in raw_candidates)
    # Tracks must score at least 0.50 (absolute) AND be within top 85% of best.
    # This means weak zones (where best < 0.59) naturally get fewer tracks.
    threshold = max(0.50, best_score * 0.85)

    candidates = []
    for zone_score, row, feats in raw_candidates:
        if zone_score < threshold:
            continue
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

    Builds a normalized feature vector from:
      - 10 profile features (tempo, energy, dynamics, etc.) — min-max normalized
      - 13 MFCC means (timbral identity) — z-score normalized across library
      - 13 MFCC stds (timbral consistency) — z-score normalized
      - 7 spectral contrast bands (harmonic structure) — z-score normalized
      - 12 chroma (pitch class energy — harmonic fingerprint) — z-score normalized
      - 6 tonnetz (tonal centroids — harmonic relationships) — z-score normalized

    Total: 61 dimensions. All components normalized to comparable scales.
    Scored via inverse Euclidean distance for better separation than cosine.
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
    all_rows = conn.execute("SELECT * FROM tracks").fetchall()
    conn.close()

    # Compute library-wide mean/std for vector features
    # so we can z-score normalize them to the same scale as profile features
    vec_collectors = {
        "mfcc_mean_json": ([], 13),
        "mfcc_std_json": ([], 13),
        "contrast_mean_json": ([], 7),
        "chroma_mean_json": ([], 12),
        "tonnetz_mean_json": ([], 6),
    }
    for row in all_rows:
        for col, (collector, _) in vec_collectors.items():
            v = _json.loads(row[col]) if isinstance(row[col], str) else row[col]
            if v: collector.append(v)

    def _stats(arrays, dims):
        """Compute per-dimension mean and std."""
        if not arrays:
            return [0] * dims, [1] * dims
        means = [sum(a[i] for a in arrays) / len(arrays) for i in range(dims)]
        stds = [max((sum((a[i] - means[i])**2 for a in arrays) / len(arrays))**0.5, 1e-6)
                for i in range(dims)]
        return means, stds

    vec_stats = {}
    for col, (collector, dims) in vec_collectors.items():
        vec_stats[col] = _stats(collector, dims)

    def _full_vec(row):
        """Build normalized similarity vector — all components on comparable scale."""
        vec = []

        # Profile features (min-max normalized)
        for f in PROFILE_FEATURES:
            r = ranges.get(f, [0, 0])
            lo, hi = r[0], r[1]
            val = row[f] if row[f] is not None else 0
            vec.append((val - lo) / (hi - lo) if hi > lo else 0.5)

        # Vector features — all z-score normalized
        for col, (_, dims) in vec_collectors.items():
            v = _json.loads(row[col]) if isinstance(row[col], str) else row[col]
            v = v or [0] * dims
            means, stds = vec_stats[col]
            vec.extend((v[i] - means[i]) / stds[i] for i in range(dims))

        return vec

    target_vec = _full_vec(target_row)

    results = []
    for row in all_rows:
        vec = _full_vec(row)
        dist = sum((a - b) ** 2 for a, b in zip(target_vec, vec)) ** 0.5
        score = 1.0 / (1.0 + dist)
        results.append({
            "key": row["track_id"],
            "artist": row["artist"],
            "album": row["album"],
            "title": row["title"],
            "file": row["file"],
            "url": f"/music/{row['file']}",
            "score": round(score, 4),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# Artist similarity
# ---------------------------------------------------------------------------

def _compute_top_features(profile_vec, ranges):
    """Compute composite features from a normalized profile vector.

    Expects profile_vec indexed by PROFILE_FEATURES order:
      0:tempo, 1:rms_mean, 2:dynamic_range, 3:centroid_mean,
      4:flatness_mean, 5:spectral_flux, 6:onset_strength,
      7:beat_strength, 8:rms_variance, 9:vocal_proxy
    """
    tempo_n = profile_vec[0]
    rms_n = profile_vec[1]
    dyn_range_n = profile_vec[2]
    centroid_n = profile_vec[3]
    flatness_n = profile_vec[4]
    flux_n = profile_vec[5]
    onset_n = profile_vec[6]
    beat_n = profile_vec[7]
    rms_var_n = profile_vec[8]
    vocal_n = profile_vec[9]

    # Stillness: inverse of rhythmic activity, higher = more drone-like
    stillness_raw = ((1 - onset_n) * 1.0 + (1 - beat_n) * 1.0
                     + (1 - flux_n) * 0.8) / 2.8

    return {
        "energy": round(rms_n, 4),
        "acousticness": round(max(0, 1 - flatness_n - centroid_n), 4),
        "danceability": round(beat_n * 0.5 + tempo_n * 0.3 + onset_n * 0.2, 4),
        "valence": round(centroid_n * 0.3, 4),  # partial — tonnetz added when available
        "instrumentalness": round(max(0, 1 - vocal_n), 4),
        "texture": round((flatness_n * 1.0 + flux_n * 0.6) / 1.6, 4),
        "dynamics": round((dyn_range_n * 1.2 + rms_var_n * 0.8) / 2.0, 4),
        "stillness": round(min(1.0, stillness_raw), 4),
    }


def _build_artist_data(music_root):
    """Load all tracks, build 61-dim vectors, aggregate per artist.

    Returns (artist_data, vec_stats, ranges) where artist_data is:
      {artist: {"vecs": [vec, ...], "albums": set, "rows": [row, ...]}}
    """
    import json as _json

    conn = _connect(music_root)
    ranges = get_norm_ranges(conn)
    all_rows = conn.execute("SELECT * FROM tracks").fetchall()
    conn.close()

    if not all_rows:
        return {}, None, ranges

    # Compute library-wide mean/std for vector features (same as find_similar)
    vec_collectors = {
        "mfcc_mean_json": ([], 13),
        "mfcc_std_json": ([], 13),
        "contrast_mean_json": ([], 7),
        "chroma_mean_json": ([], 12),
        "tonnetz_mean_json": ([], 6),
    }
    for row in all_rows:
        for col, (collector, _) in vec_collectors.items():
            v = _json.loads(row[col]) if isinstance(row[col], str) else row[col]
            if v:
                collector.append(v)

    def _stats(arrays, dims):
        if not arrays:
            return [0] * dims, [1] * dims
        means = [sum(a[i] for a in arrays) / len(arrays) for i in range(dims)]
        stds = [max((sum((a[i] - means[i])**2 for a in arrays) / len(arrays))**0.5, 1e-6)
                for i in range(dims)]
        return means, stds

    vec_stats = {}
    for col, (collector, dims) in vec_collectors.items():
        vec_stats[col] = _stats(collector, dims)

    def _full_vec(row):
        vec = []
        for f in PROFILE_FEATURES:
            r = ranges.get(f, [0, 0])
            lo, hi = r[0], r[1]
            val = row[f] if row[f] is not None else 0
            vec.append((val - lo) / (hi - lo) if hi > lo else 0.5)
        for col, (_, dims) in vec_collectors.items():
            v = _json.loads(row[col]) if isinstance(row[col], str) else row[col]
            v = v or [0] * dims
            means, stds = vec_stats[col]
            vec.extend((v[i] - means[i]) / stds[i] for i in range(dims))
        return vec

    # Group by artist
    artist_data = {}
    for row in all_rows:
        a = row["artist"]
        if a not in artist_data:
            artist_data[a] = {"vecs": [], "albums": set(), "rows": []}
        artist_data[a]["vecs"].append(_full_vec(row))
        artist_data[a]["albums"].add(row["album"])
        artist_data[a]["rows"].append(row)

    return artist_data, vec_stats, ranges


def _avg_vec(vecs):
    """Element-wise average of a list of vectors."""
    n = len(vecs)
    dims = len(vecs[0])
    return [sum(v[i] for v in vecs) / n for i in range(dims)]


def _artist_top_features(avg_profile_vec, avg_tonnetz, ranges):
    """Compute Spotify-style features for an artist, including tonnetz for valence."""
    feats = _compute_top_features(avg_profile_vec, ranges)

    # Enhance valence with tonnetz brightness if available
    if avg_tonnetz and len(avg_tonnetz) == 6:
        tonnetz_brightness = min(1.0, (abs(avg_tonnetz[0]) + abs(avg_tonnetz[1])
                                       + abs(avg_tonnetz[4]) + abs(avg_tonnetz[5])) / 4.0 * 5)
    else:
        tonnetz_brightness = 0.5

    # mode_norm not available at artist level — use 0.5 as neutral
    mode_norm = 0.5
    centroid_n = avg_profile_vec[3]
    feats["valence"] = round(mode_norm * 0.4 + tonnetz_brightness * 0.3 + centroid_n * 0.3, 4)
    return feats


def _avg_tonnetz(rows):
    """Average tonnetz vectors across rows."""
    import json as _json
    tonnetz_vals = []
    for row in rows:
        t = _json.loads(row["tonnetz_mean_json"]) if row["tonnetz_mean_json"] else None
        if t and len(t) == 6:
            tonnetz_vals.append(t)
    if not tonnetz_vals:
        return None
    n = len(tonnetz_vals)
    return [sum(v[i] for v in tonnetz_vals) / n for i in range(6)]


def find_similar_artists(artist, music_root, limit=10):
    """Find artists most similar to the given one.

    Builds 61-dim normalized vectors (same as find_similar), averages per artist,
    then ranks by cosine similarity — better suited for averaged vectors than
    Euclidean distance.

    Returns list of dicts sorted by similarity desc.
    """
    artist_data, vec_stats, ranges = _build_artist_data(music_root)

    if not artist_data or artist not in artist_data:
        return []

    # Compute average vector per artist
    artist_vecs = {}
    for a, data in artist_data.items():
        artist_vecs[a] = _avg_vec(data["vecs"])

    target_vec = artist_vecs[artist]

    results = []
    for a, avg in artist_vecs.items():
        if a == artist:
            continue
        sim = _cosine(target_vec, avg)
        # Cosine can be negative for z-scored features; clamp to 0-1
        sim = max(0.0, min(1.0, sim))

        data = artist_data[a]
        avg_profile = avg[:len(PROFILE_FEATURES)]
        tonnetz = _avg_tonnetz(data["rows"])

        results.append({
            "artist": a,
            "similarity": round(sim, 4),
            "track_count": len(data["vecs"]),
            "albums": sorted(data["albums"]),
            "top_features": _artist_top_features(avg_profile, tonnetz, ranges),
        })

    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:limit]


def get_artists_overview(music_root):
    """Return all artists with track counts, albums, and Spotify-style features.

    Reuses the same 61-dim vector building and feature computation as
    find_similar_artists, but returns data for every artist.
    """
    artist_data, vec_stats, ranges = _build_artist_data(music_root)

    if not artist_data:
        return []

    results = []
    for a, data in artist_data.items():
        avg = _avg_vec(data["vecs"])
        avg_profile = avg[:len(PROFILE_FEATURES)]
        tonnetz = _avg_tonnetz(data["rows"])

        results.append({
            "artist": a,
            "track_count": len(data["vecs"]),
            "albums": sorted(data["albums"]),
            "top_features": _artist_top_features(avg_profile, tonnetz, ranges),
        })

    results.sort(key=lambda x: x["artist"].lower())
    return results


# ---------------------------------------------------------------------------
# Key / Harmony search
# ---------------------------------------------------------------------------

# Circle of fifths: each key's harmonically compatible neighbors
# key 0=C, 1=C#, ... 11=B
_KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

def _compatible_keys(key, mode):
    """Return set of (key, mode) tuples that are harmonically compatible.

    Includes: same key, relative major/minor, circle-of-fifths neighbors (±1),
    and parallel major/minor.
    """
    compat = {(key, mode)}

    # Relative major/minor (3 semitones apart)
    if mode == 1:  # major → relative minor is 9 semitones up (or 3 down)
        compat.add(((key + 9) % 12, 0))
    else:  # minor → relative major is 3 semitones up
        compat.add(((key + 3) % 12, 1))

    # Parallel major/minor (same root, different mode)
    compat.add((key, 1 - mode))

    # Circle of fifths neighbors (±7 semitones = ±1 on circle)
    for offset in (7, -7):
        neighbor = (key + offset) % 12
        compat.add((neighbor, mode))
        # And their relative
        if mode == 1:
            compat.add(((neighbor + 9) % 12, 0))
        else:
            compat.add(((neighbor + 3) % 12, 1))

    return compat


def find_by_harmony(track_id, music_root, limit=20):
    """Find tracks harmonically compatible with the given track.

    Uses key/mode for filtering, then ranks by chroma vector similarity
    (how close the actual pitch-class distributions are).
    """
    import json as _json

    conn = _connect(music_root)
    target = conn.execute(
        "SELECT * FROM tracks WHERE track_id = ?", (track_id,)
    ).fetchone()
    if not target:
        conn.close()
        return []

    t_key, t_mode = int(target["key"]), int(target["mode"])
    compat = _compatible_keys(t_key, t_mode)

    all_rows = conn.execute("SELECT * FROM tracks").fetchall()
    conn.close()

    t_chroma = _json.loads(target["chroma_mean_json"]) if target["chroma_mean_json"] else []

    results = []
    for row in all_rows:
        if row["track_id"] == track_id:
            continue
        r_key, r_mode = int(row["key"]), int(row["mode"])

        # Filter: must be in a compatible key
        if (r_key, r_mode) not in compat:
            continue

        # Rank by chroma similarity (cosine on pitch-class vectors)
        r_chroma = _json.loads(row["chroma_mean_json"]) if row["chroma_mean_json"] else []
        chroma_sim = _cosine(t_chroma, r_chroma) if t_chroma and r_chroma else 0.5

        # Bonus for exact same key+mode
        key_bonus = 0.1 if (r_key, r_mode) == (t_key, t_mode) else 0.0

        results.append({
            "key": row["track_id"],
            "artist": row["artist"],
            "album": row["album"],
            "title": row["title"],
            "file": row["file"],
            "url": f"/music/{row['file']}",
            "musicalKey": f"{_KEY_NAMES[r_key]} {'major' if r_mode else 'minor'}",
            "score": round(chroma_sim + key_bonus, 4),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


# ---------------------------------------------------------------------------
# Mood clustering (Russell's circumplex: arousal × valence)
# ---------------------------------------------------------------------------

def get_mood_clusters(music_root):
    """Cluster all tracks into mood quadrants using audio features.

    Arousal: tempo, onset_strength, rms_mean, spectral_flux
    Valence: estimated from tonnetz consonance, chroma major-key correlation,
             spectral centroid (brightness ≈ positivity)

    Returns 4 quadrants:
      - high_positive: excited, happy, euphoric
      - high_negative: tense, aggressive, anxious
      - low_positive: peaceful, serene, content
      - low_negative: sad, melancholic, dark
    """
    import json as _json

    conn = _connect(music_root)
    ranges = get_norm_ranges(conn)
    rows = conn.execute(
        "SELECT track_id, artist, album, title, file, "
        + ", ".join(FEATURE_COLS)
        + ", chroma_mean_json, tonnetz_mean_json FROM tracks"
    ).fetchall()
    conn.close()

    if not rows:
        return {"high_positive": [], "high_negative": [],
                "low_positive": [], "low_negative": []}

    def _norm(val, feat):
        r = ranges.get(feat, [0, 0])
        lo, hi = r[0], r[1]
        return (val - lo) / (hi - lo) if hi > lo else 0.5

    # Major key chroma template (normalized Krumhansl weights)
    major_template = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                      2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
    mt_norm = sum(v**2 for v in major_template) ** 0.5

    clusters = {"high_positive": [], "high_negative": [],
                "low_positive": [], "low_negative": []}

    for row in rows:
        # Arousal: high tempo + loud + rhythmic + busy
        arousal = (
            _norm(row["tempo"], "tempo") * 0.3
            + _norm(row["rms_mean"], "rms_mean") * 0.25
            + _norm(row["onset_strength"], "onset_strength") * 0.25
            + _norm(row["spectral_flux"], "spectral_flux") * 0.2
        )

        # Valence estimation from multiple cues:
        # 1. Brightness (centroid) — brighter ≈ more positive
        brightness = _norm(row["centroid_mean"], "centroid_mean")

        # 2. Major-key correlation from chroma
        chroma = _json.loads(row["chroma_mean_json"]) if row["chroma_mean_json"] else []
        if chroma and len(chroma) == 12:
            # Correlate with major template at detected key
            key_idx = int(row["key"])
            rotated = chroma[key_idx:] + chroma[:key_idx]
            dot = sum(a * b for a, b in zip(rotated, major_template))
            c_norm = sum(v**2 for v in rotated) ** 0.5
            major_corr = dot / (c_norm * mt_norm) if c_norm > 0 else 0.5
        else:
            major_corr = 0.5

        # 3. Tonnetz consonance — higher fifths/thirds energy = more consonant = positive
        tonnetz = _json.loads(row["tonnetz_mean_json"]) if row["tonnetz_mean_json"] else []
        if tonnetz and len(tonnetz) == 6:
            # dims 0-1: fifths, 2-3: minor thirds, 4-5: major thirds
            # More energy in fifths+major thirds = consonant
            consonance = (abs(tonnetz[0]) + abs(tonnetz[1])
                         + abs(tonnetz[4]) + abs(tonnetz[5])) / 4.0
            # Normalize roughly to 0-1 (tonnetz values typically -0.1 to 0.1)
            consonance = min(1.0, consonance * 5)
        else:
            consonance = 0.5

        valence = brightness * 0.3 + major_corr * 0.4 + consonance * 0.3

        # Classify into quadrant
        if arousal >= 0.5:
            quadrant = "high_positive" if valence >= 0.5 else "high_negative"
        else:
            quadrant = "low_positive" if valence >= 0.5 else "low_negative"

        track = {
            "key": row["track_id"],
            "artist": row["artist"],
            "album": row["album"],
            "title": row["title"],
            "file": row["file"],
            "url": f"/music/{row['file']}",
            "arousal": round(arousal, 4),
            "valence": round(valence, 4),
        }
        clusters[quadrant].append(track)

    # Sort each quadrant by distance from center (most extreme first)
    for q in clusters:
        clusters[q].sort(
            key=lambda t: (t["arousal"] - 0.5)**2 + (t["valence"] - 0.5)**2,
            reverse=True,
        )

    return clusters


# ---------------------------------------------------------------------------
# Transition suggestions (DJ-style smooth transitions)
# ---------------------------------------------------------------------------

def find_transitions(track_id, music_root, limit=10):
    """Find tracks that would transition smoothly from the given track.

    A good transition has:
      - Similar tempo (±10% is ideal for beatmatching)
      - Compatible key (circle of fifths)
      - Similar energy level (no jarring volume jumps)
      - Close chroma profile (harmonic compatibility)

    Returns tracks ranked by transition score.
    """
    import json as _json

    conn = _connect(music_root)
    target = conn.execute(
        "SELECT * FROM tracks WHERE track_id = ?", (track_id,)
    ).fetchone()
    if not target:
        conn.close()
        return []

    all_rows = conn.execute("SELECT * FROM tracks").fetchall()
    ranges = get_norm_ranges(conn)
    conn.close()

    t_key, t_mode = int(target["key"]), int(target["mode"])
    t_tempo = target["tempo"]
    t_rms = target["rms_mean"]
    t_chroma = _json.loads(target["chroma_mean_json"]) if target["chroma_mean_json"] else []
    t_centroid = target["centroid_mean"]

    compat = _compatible_keys(t_key, t_mode)

    results = []
    for row in all_rows:
        if row["track_id"] == track_id:
            continue

        # Tempo compatibility: 1.0 when identical, drops off outside ±10%
        if t_tempo > 0 and row["tempo"] > 0:
            tempo_ratio = row["tempo"] / t_tempo
            # Also consider half/double time
            ratios = [tempo_ratio, tempo_ratio * 2, tempo_ratio / 2]
            tempo_score = max(max(0, 1.0 - abs(r - 1.0) * 5) for r in ratios)
        else:
            tempo_score = 0.5

        # Key compatibility: 1.0 if compatible, 0.3 if not
        r_key, r_mode = int(row["key"]), int(row["mode"])
        key_score = 1.0 if (r_key, r_mode) in compat else 0.3

        # Energy continuity: penalize large RMS jumps
        rms_diff = abs(row["rms_mean"] - t_rms)
        # Typical RMS range is ~40dB; a 6dB jump is noticeable
        energy_score = max(0, 1.0 - rms_diff / 12.0)

        # Chroma similarity
        r_chroma = _json.loads(row["chroma_mean_json"]) if row["chroma_mean_json"] else []
        chroma_score = _cosine(t_chroma, r_chroma) if t_chroma and r_chroma else 0.5

        # Brightness continuity
        centroid_diff = abs(row["centroid_mean"] - t_centroid)
        brightness_score = max(0, 1.0 - centroid_diff / 3000.0)

        # Weighted combination
        score = (
            tempo_score * 0.30
            + key_score * 0.25
            + chroma_score * 0.20
            + energy_score * 0.15
            + brightness_score * 0.10
        )

        results.append({
            "key": row["track_id"],
            "artist": row["artist"],
            "album": row["album"],
            "title": row["title"],
            "file": row["file"],
            "url": f"/music/{row['file']}",
            "musicalKey": f"{_KEY_NAMES[r_key]} {'major' if r_mode else 'minor'}",
            "tempo": round(row["tempo"], 1),
            "score": round(score, 4),
            "details": {
                "tempo": round(tempo_score, 3),
                "key": round(key_score, 3),
                "chroma": round(chroma_score, 3),
                "energy": round(energy_score, 3),
                "brightness": round(brightness_score, 3),
            },
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


def _find_audio_files(music_root):
    """Walk the music directory and return sorted list of audio file paths."""
    audio = []
    for root, _, files in os.walk(music_root):
        for f in sorted(files):
            if f.lower().endswith((".m4a", ".mp3")) and not f.startswith("_temp_"):
                audio.append(os.path.join(root, f))
    return audio


def _info_from_path(filepath, music_root):
    """Derive artist/album/title from path: root/Artist/Album/01 - Title.{m4a,mp3}"""
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
