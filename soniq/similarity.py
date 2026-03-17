"""Similarity search, harmony matching, mood clustering, and transitions.

v0.6: uses classifier outputs (cls_json) for mood clusters and as part of
the similarity vector. Raw features still used for acoustic similarity
and transitions.
"""

import json

from .db import _connect, FEATURE_COLS, get_norm_ranges
from .scoring import cosine


# Circle of fifths: key 0=C, 1=C#, ... 11=B
_KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Classifier keys used for similarity (all 0-1, no normalization needed)
_CLS_SIM_KEYS = [
    "arousal", "valence", "happy", "sad", "relaxed", "aggressive",
    "danceable", "energetic", "hypnotic", "instrumental",
    "brilliant", "radiant", "contemplative", "party",
]


def _compatible_keys(key, mode):
    """Return set of (key, mode) tuples that are harmonically compatible."""
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

    Uses classifier outputs (14D, already 0-1) + vector features for
    acoustic similarity. Scored via inverse Euclidean distance.
    """
    conn = _connect(music_root)
    target_row = conn.execute(
        "SELECT * FROM tracks WHERE track_id = ?", (track_id,)
    ).fetchone()
    if not target_row:
        conn.close()
        return []

    all_rows = conn.execute("SELECT * FROM tracks").fetchall()
    conn.close()

    # Compute z-score stats for vector features
    vec_collectors = {
        "mfcc_mean_json": ([], 13),
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

        # Classifier outputs (already 0-1, no normalization needed)
        cls = json.loads(row["cls_json"]) if row["cls_json"] else {}
        for k in _CLS_SIM_KEYS:
            vec.append(cls.get(k, 0.5))

        # Vector features (z-score normalized)
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
    """Find tracks harmonically compatible with the given track."""
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
    """Cluster all tracks into mood quadrants using pre-computed arousal/valence.

    Returns 4 quadrants (Russell's Circumplex):
      - high_positive: excited, happy, euphoric
      - high_negative: tense, aggressive, anxious
      - low_positive: peaceful, serene, content
      - low_negative: sad, melancholic, dark
    """
    conn = _connect(music_root)
    rows = conn.execute(
        "SELECT track_id, artist, album, title, file, cls_json FROM tracks"
    ).fetchall()
    conn.close()

    if not rows:
        return {"high_positive": [], "high_negative": [],
                "low_positive": [], "low_negative": []}

    clusters = {"high_positive": [], "high_negative": [],
                "low_positive": [], "low_negative": []}

    for row in rows:
        cls = json.loads(row["cls_json"]) if row["cls_json"] else {}
        arousal = cls.get("arousal", 0.5)
        valence = cls.get("valence", 0.5)

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
    """Find tracks that would transition smoothly from the given track."""
    conn = _connect(music_root)
    target = conn.execute(
        "SELECT * FROM tracks WHERE track_id = ?", (track_id,)
    ).fetchone()
    if not target:
        conn.close()
        return []

    all_rows = conn.execute("SELECT * FROM tracks").fetchall()
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
