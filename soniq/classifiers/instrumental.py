"""Classifier: instrumental — perceived absence of vocals/singing.

Formula-based, feature-only. Uses three signal families:
1. Spectral stability: voice modulates spectrum dynamically
2. Modulation regularity: instrumental has peaked modulation pattern
3. Spectral shape: MFCCs capture vocal tract vs instrument timbre

0 = vocal (singing, speech, voice-heavy)
1 = instrumental (no voice, instruments only)
"""

import math
from ._corpus_stats import STATS


def _norm(val, key):
    """Z-score through sigmoid — corpus-relative 0-1."""
    mean, std = STATS[key]
    z = (val - mean) / (std + 1e-8)
    return 1 / (1 + math.exp(-z))


def predict(prepared):
    """Predict instrumental quality from prepared features dict.

    Returns dict with instrumental (0-1) and component scores.
    """
    # --- Stability signals ---
    spectral_stability = 1 - _norm(prepared.get("centroid_std", 0), "centroid_std")
    timbral_stability = 1 - _norm(prepared.get("mfcc_delta_var", 0), "mfcc_delta_var")
    flux_stability = 1 - _norm(prepared.get("flux_std", 0), "flux_std")
    bw_stability = 1 - _norm(prepared.get("bandwidth_std", 0), "bandwidth_std")

    stability = (
        spectral_stability * 0.35
        + timbral_stability * 0.25
        + flux_stability * 0.20
        + bw_stability * 0.20
    )

    # --- Modulation regularity ---
    mod_regularity = _norm(prepared.get("mod_crest", 0), "mod_crest")

    # --- Spectral shape (MFCC values) ---
    mfcc1 = prepared.get("mfcc1", 130)
    slope_signal = 1 / (1 + math.exp(-(mfcc1 - 130) / 40))

    mfcc3 = prepared.get("mfcc3", 20)
    formant_absence = 1 / (1 + math.exp((mfcc3 - 20) / 15))

    spectral_shape = slope_signal * 0.6 + formant_absence * 0.4

    # --- Combine ---
    raw = (
        stability * 0.45
        + mod_regularity * 0.25
        + spectral_shape * 0.30
    )

    # Sigmoid stretch
    instrumental = 1 / (1 + math.exp(-6 * (raw - 0.5)))
    instrumental = round(max(0.0, min(1.0, instrumental)), 4)

    return {
        "instrumental": instrumental,
        "stability": round(stability, 4),
        "mod_regularity": round(mod_regularity, 4),
        "spectral_shape": round(spectral_shape, 4),
    }
