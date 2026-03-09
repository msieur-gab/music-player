"""Zone profiles — target vectors and per-zone feature weights.

Pure data, no logic. Changing a profile here takes effect immediately
on the next classification — no re-analysis needed.

Architecture note: these drive Russell's Circumplex mapping.
  arousal axis  → energy_rhythm weights (tempo, rms, onset, beat)
  valence axis  → valence weight (chroma major-key, tonnetz consonance, mode)
  timbre detail → timbre_scalars weights (centroid, flatness, flux, zcr, etc.)
"""

# ---------------------------------------------------------------------------
# Feature group definitions for weighted scoring
# ---------------------------------------------------------------------------

_ENERGY_RHYTHM = ["tempo", "rms_mean", "onset_strength", "beat_strength"]
_TIMBRE_SCALARS = ["centroid_mean", "flatness_mean", "spectral_flux",
                   "dynamic_range", "rms_variance", "vocal_proxy"]

_MFCC_LO_DIMS = 4   # coefficients 0-3 (broad spectral shape)
_MFCC_HI_DIMS = 9   # coefficients 4-12 (fine timbral detail)


# ---------------------------------------------------------------------------
# Context profiles — target vectors + per-zone feature group weights
#
# Scalar targets are normalized 0-1 (0 = library min, 1 = library max).
# Weights control how much each feature group contributes to the final score.
# Research basis: see docs/RESEARCH_MIR_FEATURES.md
# ---------------------------------------------------------------------------

CONTEXT_PROFILES = {
    # === Activities -- mapped to brainwave states ===
    "focus": {
        "group": "activity",
        "label": "Deep Focus",
        "desc": "Bright, dynamic, tonal -- sustained cognitive alertness",
        "target": {
            "tempo": 0.50, "rms_mean": 0.65, "dynamic_range": 0.15,
            "centroid_mean": 0.50, "flatness_mean": 0.03, "spectral_flux": 0.40,
            "onset_strength": 0.40, "beat_strength": 0.40,
            "rms_variance": 0.10, "vocal_proxy": 0.80, "zcr_mean": 0.10,
            "_arousal": 0.55, "_valence": 0.55,
        },
        "weights": {"energy_rhythm": 2.0, "timbre_scalars": 2.0,
                    "arousal": 1.5, "valence": 0.5},
    },
    "creative": {
        "group": "activity",
        "label": "Creative Flow",
        "desc": "Balanced, harmonic, fluid -- relaxed alertness",
        "target": {
            "tempo": 0.40, "rms_mean": 0.60, "dynamic_range": 0.12,
            "centroid_mean": 0.35, "flatness_mean": 0.03, "spectral_flux": 0.30,
            "onset_strength": 0.35, "beat_strength": 0.30,
            "rms_variance": 0.10, "vocal_proxy": 0.80, "zcr_mean": 0.10,
            "_arousal": 0.45, "_valence": 0.55,
        },
        "weights": {"energy_rhythm": 1.5, "timbre_scalars": 1.5,
                    "arousal": 1.5, "valence": 1.0},
    },
    "meditation": {
        "group": "activity",
        "label": "Meditation",
        "desc": "Warm, still, organic -- theta state, inner quiet",
        "target": {
            "tempo": 0.15, "rms_mean": 0.45, "dynamic_range": 0.10,
            "centroid_mean": 0.15, "flatness_mean": 0.02, "spectral_flux": 0.10,
            "onset_strength": 0.08, "beat_strength": 0.08,
            "rms_variance": 0.08, "vocal_proxy": 0.80,
            "_arousal": 0.15, "_valence": 0.55,
        },
        "weights": {"energy_rhythm": 2.0, "timbre_scalars": 2.0,
                    "arousal": 2.0, "valence": 0.5,
                    "features": {
                        "onset_strength": 4.0, "beat_strength": 4.0,
                        "spectral_flux": 3.0, "dynamic_range": 3.0,
                        "tempo": 1.0,
                    }},
    },
    "energize": {
        "group": "activity",
        "label": "Energy",
        "desc": "Loud, bright, driving -- get moving",
        "target": {
            "tempo": 0.80, "rms_mean": 0.85, "dynamic_range": 0.12,
            "centroid_mean": 0.70, "flatness_mean": 0.04, "spectral_flux": 0.80,
            "onset_strength": 0.80, "beat_strength": 0.80,
            "rms_variance": 0.10, "vocal_proxy": 0.75, "zcr_mean": 0.15,
            "_arousal": 0.85, "_valence": 0.55,
        },
        "weights": {"energy_rhythm": 3.0, "timbre_scalars": 1.5,
                    "arousal": 3.0, "valence": 0.5},
    },
    "sleep": {
        "group": "activity",
        "label": "Sleep",
        "desc": "Dark, filtered, barely there -- drift off",
        "target": {
            "tempo": 0.10, "rms_mean": 0.40, "dynamic_range": 0.08,
            "centroid_mean": 0.10, "flatness_mean": 0.02, "spectral_flux": 0.05,
            "onset_strength": 0.05, "beat_strength": 0.05,
            "rms_variance": 0.08, "vocal_proxy": 0.80,
            "_arousal": 0.10, "_valence": 0.40,
        },
        "weights": {"energy_rhythm": 2.0, "timbre_scalars": 2.0,
                    "arousal": 3.0, "valence": 0.5,
                    "features": {
                        "onset_strength": 5.0, "beat_strength": 5.0,
                        "spectral_flux": 4.0, "dynamic_range": 4.0,
                        "tempo": 1.0,
                    }},
    },

    # === Moods -- Russell's Circumplex (arousal x valence) ===
    "joy": {
        "group": "mood",
        "label": "Joy",
        "desc": "Bright, rhythmic, tonal -- euphoric and uplifting",
        "target": {
            "tempo": 0.70, "rms_mean": 0.70, "dynamic_range": 0.12,
            "centroid_mean": 0.50, "flatness_mean": 0.03, "spectral_flux": 0.50,
            "onset_strength": 0.55, "beat_strength": 0.55,
            "rms_variance": 0.10, "vocal_proxy": 0.80, "zcr_mean": 0.10,
            "_arousal": 0.70, "_valence": 0.85,
        },
        "weights": {"energy_rhythm": 2.0, "timbre_scalars": 1.5,
                    "arousal": 2.0, "valence": 3.0},
    },
    "calm": {
        "group": "mood",
        "label": "Calm",
        "desc": "Warm, steady, clear -- unwind and breathe",
        "target": {
            "tempo": 0.25, "rms_mean": 0.50, "dynamic_range": 0.15,
            "centroid_mean": 0.20, "flatness_mean": 0.02, "spectral_flux": 0.15,
            "onset_strength": 0.20, "beat_strength": 0.15,
            "rms_variance": 0.10, "vocal_proxy": 0.80, "zcr_mean": 0.08,
            "_arousal": 0.25, "_valence": 0.70,
        },
        "weights": {"energy_rhythm": 2.0, "timbre_scalars": 2.0,
                    "arousal": 2.0, "valence": 2.5},
    },
    "melancholy": {
        "group": "mood",
        "label": "Melancholy",
        "desc": "Dark, slow, intimate -- sit with the feeling",
        "target": {
            "tempo": 0.30, "rms_mean": 0.55, "dynamic_range": 0.12,
            "centroid_mean": 0.20, "flatness_mean": 0.02, "spectral_flux": 0.15,
            "onset_strength": 0.25, "beat_strength": 0.20,
            "rms_variance": 0.10, "vocal_proxy": 0.80, "zcr_mean": 0.08,
            "_arousal": 0.30, "_valence": 0.20,
        },
        "weights": {"energy_rhythm": 1.0, "timbre_scalars": 1.5,
                    "arousal": 1.5, "valence": 3.0},
    },
    "heroic": {
        "group": "mood",
        "label": "Heroic",
        "desc": "Bold, sweeping, tonal -- brass and conviction",
        "target": {
            "tempo": 0.55, "rms_mean": 0.75, "dynamic_range": 0.12,
            "centroid_mean": 0.50, "flatness_mean": 0.03, "spectral_flux": 0.50,
            "onset_strength": 0.50, "beat_strength": 0.45,
            "rms_variance": 0.10, "vocal_proxy": 0.80, "zcr_mean": 0.10,
            "_arousal": 0.60, "_valence": 0.75,
        },
        "weights": {"energy_rhythm": 2.0, "timbre_scalars": 1.5,
                    "arousal": 2.0, "valence": 2.5},
    },
    "mysterious": {
        "group": "mood",
        "label": "Mysterious",
        "desc": "Dark, textured, noisy -- shadows and atmosphere",
        "target": {
            "tempo": 0.30, "rms_mean": 0.55, "dynamic_range": 0.15,
            "centroid_mean": 0.20, "flatness_mean": 0.05, "spectral_flux": 0.20,
            "onset_strength": 0.25, "beat_strength": 0.15,
            "rms_variance": 0.12, "vocal_proxy": 0.75, "zcr_mean": 0.12,
            "_arousal": 0.30, "_valence": 0.30,
        },
        "weights": {"energy_rhythm": 1.0, "timbre_scalars": 2.5,
                    "arousal": 1.5, "valence": 2.0},
    },

    # === Support -- therapeutic profiles ===
    "stress_relief": {
        "group": "support",
        "label": "Stress Relief",
        "desc": "Warm, predictable, spacious -- let the nervous system settle",
        "target": {
            "tempo": 0.25, "rms_mean": 0.50, "dynamic_range": 0.15,
            "centroid_mean": 0.25, "flatness_mean": 0.02, "spectral_flux": 0.15,
            "onset_strength": 0.15, "beat_strength": 0.20,
            "rms_variance": 0.08, "vocal_proxy": 0.80, "zcr_mean": 0.10,
            "_arousal": 0.20, "_valence": 0.60,
        },
        "weights": {"energy_rhythm": 2.0, "timbre_scalars": 2.0,
                    "arousal": 2.5, "valence": 1.5},
    },
    "recovery": {
        "group": "support",
        "label": "Recovery",
        "desc": "Filtered, ambient, gentle -- physiological restoration",
        "target": {
            "tempo": 0.15, "rms_mean": 0.40, "dynamic_range": 0.08,
            "centroid_mean": 0.15, "flatness_mean": 0.02, "spectral_flux": 0.08,
            "onset_strength": 0.08, "beat_strength": 0.08,
            "rms_variance": 0.08, "vocal_proxy": 0.80,
            "_arousal": 0.10, "_valence": 0.50,
        },
        "weights": {"energy_rhythm": 2.0, "timbre_scalars": 2.0,
                    "arousal": 3.0, "valence": 0.5,
                    "features": {
                        "onset_strength": 5.0, "beat_strength": 5.0,
                        "spectral_flux": 4.0, "dynamic_range": 4.0,
                        "tempo": 1.0,
                    }},
    },
}
