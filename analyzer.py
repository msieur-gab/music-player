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

    All components are normalized to comparable scales so no single group
    dominates the distance calculation.

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

    # Compute library-wide mean/std for MFCC, MFCC std, and contrast
    # so we can z-score normalize them to the same scale as profile features
    all_mfcc = []
    all_mfcc_s = []
    all_contrast = []
    for row in all_rows:
        m = _json.loads(row["mfcc_mean_json"]) if isinstance(row["mfcc_mean_json"], str) else row["mfcc_mean_json"]
        s = _json.loads(row["mfcc_std_json"]) if isinstance(row["mfcc_std_json"], str) else row["mfcc_std_json"]
        c = _json.loads(row["contrast_mean_json"]) if isinstance(row["contrast_mean_json"], str) else row["contrast_mean_json"]
        if m: all_mfcc.append(m)
        if s: all_mfcc_s.append(s)
        if c: all_contrast.append(c)

    def _stats(arrays, dims):
        """Compute per-dimension mean and std."""
        if not arrays:
            return [0] * dims, [1] * dims
        means = [sum(a[i] for a in arrays) / len(arrays) for i in range(dims)]
        stds = [max((sum((a[i] - means[i])**2 for a in arrays) / len(arrays))**0.5, 1e-6)
                for i in range(dims)]
        return means, stds

    mfcc_mean, mfcc_std = _stats(all_mfcc, 13)
    mfccs_mean, mfccs_std = _stats(all_mfcc_s, 13)
    cont_mean, cont_std = _stats(all_contrast, 7)

    def _full_vec(row):
        """Build normalized similarity vector — all components on 0-1 scale."""
        vec = []

        # Profile features (already min-max normalized)
        for f in PROFILE_FEATURES:
            r = ranges.get(f, [0, 0])
            lo, hi = r[0], r[1]
            val = row[f] if row[f] is not None else 0
            vec.append((val - lo) / (hi - lo) if hi > lo else 0.5)

        # MFCC mean — z-score normalized
        m = _json.loads(row["mfcc_mean_json"]) if isinstance(row["mfcc_mean_json"], str) else row["mfcc_mean_json"]
        m = m or [0] * 13
        vec.extend((m[i] - mfcc_mean[i]) / mfcc_std[i] for i in range(13))

        # MFCC std — z-score normalized
        s = _json.loads(row["mfcc_std_json"]) if isinstance(row["mfcc_std_json"], str) else row["mfcc_std_json"]
        s = s or [0] * 13
        vec.extend((s[i] - mfccs_mean[i]) / mfccs_std[i] for i in range(13))

        # Spectral contrast — z-score normalized
        c = _json.loads(row["contrast_mean_json"]) if isinstance(row["contrast_mean_json"], str) else row["contrast_mean_json"]
        c = c or [0] * 7
        vec.extend((c[i] - cont_mean[i]) / cont_std[i] for i in range(7))

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
