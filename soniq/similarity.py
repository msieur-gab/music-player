"""Similarity search, harmony matching, mood clustering, and transitions.

All queries are computed on the fly from stored features.
"""

import json

from .db import _connect, FEATURE_COLS, PROFILE_FEATURES, get_norm_ranges
from .scoring import cosine, compute_arousal, compute_valence, _MAJOR_TEMPLATE, _MT_NORM


# Circle of fifths: key 0=C, 1=C#, ... 11=B
_KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _compatible_keys(key, mode):
    """Return set of (key, mode) tuples that are harmonically compatible.

    Includes: same key, relative major/minor, circle-of-fifths neighbors,
    and parallel major/minor.
    """
    compat = {(key, mode)}

    if mode == 1:
        compat.add(((key + 9) % 12, 0))
    else:
        compat.add(((key + 3) % 12, 1))

    compat.add((key, 1 - mode))

    for offset in (7, -7):
        neighbor = (key + offset) % 12
        compat.add((neighbor, mode))
        if mode == 1:
            compat.add(((neighbor + 9) % 12, 0))
        else:
            compat.add(((neighbor + 3) % 12, 1))

    return compat


def find_similar(track_id, music_root, limit=10):
    """Find tracks most similar to the given one.

    Builds a 61-dimension normalized vector from all feature groups.
    Scored via inverse Euclidean distance.
    """
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

    vec_collectors = {
        "mfcc_mean_json": ([], 13),
        "mfcc_std_json": ([], 13),
        "contrast_mean_json": ([], 7),
        "chroma_mean_json": ([], 12),
        "tonnetz_mean_json": ([], 6),
    }
    for row in all_rows:
        for col, (collector, _) in vec_collectors.items():
            v = json.loads(row[col]) if isinstance(row[col], str) else row[col]
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
            v = json.loads(row[col]) if isinstance(row[col], str) else row[col]
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


def find_by_harmony(track_id, music_root, limit=20):
    """Find tracks harmonically compatible with the given track.

    Uses key/mode for filtering, then ranks by chroma vector similarity.
    """
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

    t_chroma = json.loads(target["chroma_mean_json"]) if target["chroma_mean_json"] else []

    results = []
    for row in all_rows:
        if row["track_id"] == track_id:
            continue
        r_key, r_mode = int(row["key"]), int(row["mode"])

        if (r_key, r_mode) not in compat:
            continue

        r_chroma = json.loads(row["chroma_mean_json"]) if row["chroma_mean_json"] else []
        chroma_sim = cosine(t_chroma, r_chroma) if t_chroma and r_chroma else 0.5

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


def get_mood_clusters(music_root):
    """Cluster all tracks into mood quadrants using audio features.

    Returns 4 quadrants (Russell's Circumplex):
      - high_positive: excited, happy, euphoric
      - high_negative: tense, aggressive, anxious
      - low_positive: peaceful, serene, content
      - low_negative: sad, melancholic, dark
    """
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

    major_template = _MAJOR_TEMPLATE
    mt_norm = _MT_NORM

    clusters = {"high_positive": [], "high_negative": [],
                "low_positive": [], "low_negative": []}

    for row in rows:
        arousal = (
            _norm(row["tempo"], "tempo") * 0.3
            + _norm(row["rms_mean"], "rms_mean") * 0.25
            + _norm(row["onset_strength"], "onset_strength") * 0.25
            + _norm(row["spectral_flux"], "spectral_flux") * 0.2
        )

        brightness = _norm(row["centroid_mean"], "centroid_mean")

        chroma = json.loads(row["chroma_mean_json"]) if row["chroma_mean_json"] else []
        if chroma and len(chroma) == 12:
            key_idx = int(row["key"])
            rotated = chroma[key_idx:] + chroma[:key_idx]
            dot = sum(a * b for a, b in zip(rotated, major_template))
            c_norm = sum(v**2 for v in rotated) ** 0.5
            major_corr = dot / (c_norm * mt_norm) if c_norm > 0 else 0.5
        else:
            major_corr = 0.5

        tonnetz = json.loads(row["tonnetz_mean_json"]) if row["tonnetz_mean_json"] else []
        if tonnetz and len(tonnetz) == 6:
            consonance = (abs(tonnetz[0]) + abs(tonnetz[1])
                         + abs(tonnetz[4]) + abs(tonnetz[5])) / 4.0
            consonance = min(1.0, consonance * 5)
        else:
            consonance = 0.5

        valence = brightness * 0.3 + major_corr * 0.4 + consonance * 0.3

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

    for q in clusters:
        clusters[q].sort(
            key=lambda t: (t["arousal"] - 0.5)**2 + (t["valence"] - 0.5)**2,
            reverse=True,
        )

    return clusters


def find_transitions(track_id, music_root, limit=10):
    """Find tracks that would transition smoothly from the given track.

    A good transition has similar tempo, compatible key, similar energy,
    and close chroma profile.
    """
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
    t_chroma = json.loads(target["chroma_mean_json"]) if target["chroma_mean_json"] else []
    t_centroid = target["centroid_mean"]

    compat = _compatible_keys(t_key, t_mode)

    results = []
    for row in all_rows:
        if row["track_id"] == track_id:
            continue

        if t_tempo > 0 and row["tempo"] > 0:
            tempo_ratio = row["tempo"] / t_tempo
            ratios = [tempo_ratio, tempo_ratio * 2, tempo_ratio / 2]
            tempo_score = max(max(0, 1.0 - abs(r - 1.0) * 5) for r in ratios)
        else:
            tempo_score = 0.5

        r_key, r_mode = int(row["key"]), int(row["mode"])
        key_score = 1.0 if (r_key, r_mode) in compat else 0.3

        rms_diff = abs(row["rms_mean"] - t_rms)
        energy_score = max(0, 1.0 - rms_diff / 12.0)

        r_chroma = json.loads(row["chroma_mean_json"]) if row["chroma_mean_json"] else []
        chroma_score = cosine(t_chroma, r_chroma) if t_chroma and r_chroma else 0.5

        centroid_diff = abs(row["centroid_mean"] - t_centroid)
        brightness_score = max(0, 1.0 - centroid_diff / 3000.0)

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
