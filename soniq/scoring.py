"""Track classification — score tracks against zone profiles.

Computed on demand, never stored. Changing a profile in profiles.py
takes effect immediately on the next call.
"""

import json

from .profiles import CONTEXT_PROFILES, _ENERGY_RHYTHM, _TIMBRE_SCALARS
from .db import FEATURE_COLS, PROFILE_FEATURES, get_norm_ranges


# Krumhansl-Schmuckler major key profile (for valence estimation)
_MAJOR_TEMPLATE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                   2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MT_NORM = sum(v ** 2 for v in _MAJOR_TEMPLATE) ** 0.5


def classify_track(features, norm_ranges):
    """Score a track against each context profile. Returns {zone_id: score}.

    Uses weighted inverse Euclidean distance on scalar features, plus two
    derived scalars computed from vector features:

      arousal  -- from tempo, rms, onset, flux (0-1)
      valence  -- from chroma major-key correlation, tonnetz consonance,
                  mode (0-1)

    Each zone has per-group weights so arousal-dominant zones (sleep, energy)
    weight energy scalars heavily while valence-dependent zones (joy,
    melancholy) weight the valence signal from chroma/tonnetz.
    """
    arousal = compute_arousal(features, norm_ranges)
    valence = compute_valence(features)

    ext = dict(features)
    ext["_arousal"] = arousal
    ext["_valence"] = valence

    scores = {}
    for ctx_id, profile in CONTEXT_PROFILES.items():
        target = profile["target"]
        w = profile["weights"]

        weighted_sq_sum = 0.0
        total_weight = 0.0

        feat_w = w.get("features", {})
        for group_key, feat_list in (("energy_rhythm", _ENERGY_RHYTHM),
                                     ("timbre_scalars", _TIMBRE_SCALARS)):
            group_wt = w[group_key]
            for f in feat_list:
                wt = feat_w.get(f, group_wt)
                r = norm_ranges.get(f, [0, 0])
                lo, hi = r[0], r[1]
                val = (ext.get(f, 0) - lo) / (hi - lo) if hi > lo else 0.5
                tgt = target.get(f, 0.5)
                weighted_sq_sum += wt * (val - tgt) ** 2
                total_weight += wt

        for derived, wt_key in (("_arousal", "arousal"), ("_valence", "valence")):
            wt = w.get(wt_key, 1.0)
            val = ext[derived]
            tgt = target.get(derived, 0.5)
            weighted_sq_sum += wt * (val - tgt) ** 2
            total_weight += wt

        dist = (weighted_sq_sum / total_weight) ** 0.5 if total_weight > 0 else 0
        scores[ctx_id] = round(1.0 / (1.0 + dist), 4)

    return scores


def compute_arousal(features, norm_ranges):
    """Derive arousal (0-1) from energy/rhythm features."""
    def _n(f):
        r = norm_ranges.get(f, [0, 0])
        lo, hi = r[0], r[1]
        return (features.get(f, 0) - lo) / (hi - lo) if hi > lo else 0.5

    return (
        _n("tempo") * 0.3
        + _n("rms_mean") * 0.25
        + _n("onset_strength") * 0.25
        + _n("spectral_flux") * 0.2
    )


def compute_valence(features):
    """Derive valence (0-1) from chroma major-key correlation, tonnetz
    consonance, and mode.
    """
    chroma = features.get("chroma_mean", []) or []
    tonnetz = features.get("tonnetz_mean", []) or []

    if chroma and len(chroma) == 12:
        key_idx = int(features.get("key", 0))
        rotated = chroma[key_idx:] + chroma[:key_idx]
        dot = sum(a * b for a, b in zip(rotated, _MAJOR_TEMPLATE))
        c_norm = sum(v ** 2 for v in rotated) ** 0.5
        major_corr = dot / (c_norm * _MT_NORM) if c_norm > 0 else 0.5
    else:
        major_corr = 0.5

    if tonnetz and len(tonnetz) == 6:
        consonance = (abs(tonnetz[0]) + abs(tonnetz[1])
                      + abs(tonnetz[4]) + abs(tonnetz[5])) / 4.0
        consonance = min(1.0, consonance * 5)
    else:
        consonance = 0.5

    mode = features.get("mode", 0.5)
    mode_signal = float(mode) if mode in (0, 1) else 0.5

    return major_corr * 0.35 + consonance * 0.25 + mode_signal * 0.40


def score_all_tracks(conn):
    """Score every track against every profile. Returns [(row, {zone: score}), ...]."""
    ranges = get_norm_ranges(conn)
    rows = conn.execute("SELECT * FROM tracks").fetchall()

    scored = []
    for row in rows:
        feats = {f: row[f] for f in FEATURE_COLS}
        for col in ("chroma_mean", "tonnetz_mean"):
            json_col = col + "_json"
            v = json.loads(row[json_col]) if isinstance(row[json_col], str) else row[json_col]
            feats[col] = v or []
        scores = classify_track(feats, ranges)
        scored.append((row, scores))
    return scored


def normalize_vec(features, ranges):
    """Convert raw features to 0-1 vector using library min-max ranges."""
    vec = []
    for f in PROFILE_FEATURES:
        r = ranges.get(f, [0, 0])
        lo, hi = r[0], r[1]
        val = features.get(f, 0)
        vec.append((val - lo) / (hi - lo) if hi > lo else 0.5)
    return vec


def cosine(a, b):
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0
