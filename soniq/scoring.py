"""Track classification — score tracks against zone profiles using classifier outputs.

v0.6: classifier outputs (arousal, valence, relaxed, etc.) are the primary
scoring currency. No more raw-feature normalization for zone matching.
"""

import json

from .profiles import CONTEXT_PROFILES
from .db import FEATURE_COLS


def classify_track(cls, profile):
    """Score a track against a profile using classifier outputs.

    Uses weighted inverse Euclidean distance in classifier-output space.

    Args:
        cls: dict of classifier outputs (arousal, valence, relaxed, etc.)
        profile: profile dict from CONTEXT_PROFILES

    Returns:
        float score 0-1 (higher = better match)
    """
    target = profile["target"]
    weights = profile.get("weights", {})

    weighted_sq_sum = 0.0
    total_weight = 0.0

    for key, tgt in target.items():
        val = cls.get(key, 0.5)
        wt = weights.get(key, 1.0)
        weighted_sq_sum += wt * (val - tgt) ** 2
        total_weight += wt

    dist = (weighted_sq_sum / total_weight) ** 0.5 if total_weight > 0 else 0
    return round(1.0 / (1.0 + dist), 4)


def score_all_tracks(conn):
    """Score every track against every profile. Returns [(row, {zone: score}), ...]."""
    rows = conn.execute("SELECT * FROM tracks").fetchall()

    scored = []
    for row in rows:
        cls = json.loads(row["cls_json"]) if row["cls_json"] else {}
        scores = {}
        for ctx_id, profile in CONTEXT_PROFILES.items():
            scores[ctx_id] = classify_track(cls, profile)
        scored.append((row, scores))
    return scored


def cosine(a, b):
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0
