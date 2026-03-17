"""Zone profiles — classifier-space targets.

v0.6: targets reference classifier outputs directly (arousal, valence,
relaxed, energetic, etc.) instead of raw audio features. Much simpler
and more intuitive to tune.

Pure data, no logic. Changing a profile here takes effect immediately
on the next classification — no re-analysis needed.
"""

# ---------------------------------------------------------------------------
# Context profiles — targets in classifier output space (all 0-1)
#
# Each target key matches a classifier output name.
# Weights control relative importance (default 1.0 if omitted).
# ---------------------------------------------------------------------------

CONTEXT_PROFILES = {
    # === Activities ===
    "focus": {
        "group": "activity",
        "label": "Deep Focus",
        "desc": "Bright, dynamic, tonal -- sustained cognitive alertness",
        "target": {
            "arousal": 0.55, "valence": 0.55,
            "energetic": 0.45, "contemplative": 0.40,
            "hypnotic": 0.55, "instrumental": 0.70,
            "relaxed": 0.35, "aggressive": 0.15,
        },
        "weights": {
            "arousal": 2.0, "valence": 1.0,
            "energetic": 1.5, "contemplative": 1.5,
            "hypnotic": 2.0, "instrumental": 1.5,
            "relaxed": 1.0, "aggressive": 1.5,
        },
    },
    "creative": {
        "group": "activity",
        "label": "Creative Flow",
        "desc": "Balanced, harmonic, fluid -- relaxed alertness",
        "target": {
            "arousal": 0.45, "valence": 0.55,
            "energetic": 0.40, "contemplative": 0.50,
            "hypnotic": 0.45, "instrumental": 0.60,
            "relaxed": 0.45, "happy": 0.50,
        },
        "weights": {
            "arousal": 1.5, "valence": 1.5,
            "energetic": 1.0, "contemplative": 2.0,
            "hypnotic": 1.5, "instrumental": 1.0,
            "relaxed": 1.5, "happy": 1.0,
        },
    },
    "meditation": {
        "group": "activity",
        "label": "Meditation",
        "desc": "Warm, still, organic -- theta state, inner quiet",
        "target": {
            "arousal": 0.10, "valence": 0.50,
            "energetic": 0.05, "still": 0.90,
            "relaxed": 0.90, "contemplative": 0.80,
            "hypnotic": 0.70, "aggressive": 0.02,
        },
        "weights": {
            "arousal": 3.0, "valence": 0.5,
            "energetic": 3.0, "still": 3.0,
            "relaxed": 2.5, "contemplative": 2.0,
            "hypnotic": 1.5, "aggressive": 2.0,
        },
    },
    "energize": {
        "group": "activity",
        "label": "Energy",
        "desc": "Loud, bright, driving -- get moving",
        "target": {
            "arousal": 0.85, "valence": 0.60,
            "energetic": 0.85, "danceable": 0.65,
            "aggressive": 0.40, "party": 0.55,
            "brilliant": 0.65, "happy": 0.55,
        },
        "weights": {
            "arousal": 3.0, "valence": 1.0,
            "energetic": 3.0, "danceable": 2.0,
            "aggressive": 1.0, "party": 1.5,
            "brilliant": 1.0, "happy": 1.0,
        },
    },
    "sleep": {
        "group": "activity",
        "label": "Sleep",
        "desc": "Dark, filtered, barely there -- drift off",
        "target": {
            "arousal": 0.05, "valence": 0.40,
            "energetic": 0.02, "still": 0.95,
            "relaxed": 0.95, "contemplative": 0.70,
            "aggressive": 0.01, "danceable": 0.02,
        },
        "weights": {
            "arousal": 3.0, "valence": 0.5,
            "energetic": 3.0, "still": 3.0,
            "relaxed": 2.5, "contemplative": 1.0,
            "aggressive": 3.0, "danceable": 2.0,
        },
    },

    # === Moods — Russell's Circumplex ===
    "joy": {
        "group": "mood",
        "label": "Joy",
        "desc": "Bright, rhythmic, tonal -- euphoric and uplifting",
        "target": {
            "arousal": 0.70, "valence": 0.85,
            "happy": 0.85, "energetic": 0.60,
            "radiant": 0.75, "danceable": 0.55,
            "sad": 0.10, "aggressive": 0.10,
        },
        "weights": {
            "arousal": 2.0, "valence": 3.0,
            "happy": 3.0, "energetic": 1.5,
            "radiant": 2.0, "danceable": 1.0,
            "sad": 2.0, "aggressive": 1.5,
        },
    },
    "calm": {
        "group": "mood",
        "label": "Calm",
        "desc": "Warm, steady, clear -- unwind and breathe",
        "target": {
            "arousal": 0.25, "valence": 0.65,
            "relaxed": 0.80, "contemplative": 0.60,
            "warm": 0.60, "happy": 0.50,
            "aggressive": 0.05, "energetic": 0.20,
        },
        "weights": {
            "arousal": 2.0, "valence": 2.5,
            "relaxed": 2.5, "contemplative": 1.5,
            "warm": 1.5, "happy": 1.0,
            "aggressive": 2.0, "energetic": 1.5,
        },
    },
    "melancholy": {
        "group": "mood",
        "label": "Melancholy",
        "desc": "Dark, slow, intimate -- sit with the feeling",
        "target": {
            "arousal": 0.25, "valence": 0.20,
            "sad": 0.80, "contemplative": 0.70,
            "relaxed": 0.55, "somber": 0.65,
            "happy": 0.10, "energetic": 0.15,
        },
        "weights": {
            "arousal": 1.5, "valence": 3.0,
            "sad": 3.0, "contemplative": 2.0,
            "relaxed": 1.0, "somber": 2.0,
            "happy": 2.0, "energetic": 1.5,
        },
    },
    "heroic": {
        "group": "mood",
        "label": "Heroic",
        "desc": "Bold, sweeping, tonal -- brass and conviction",
        "target": {
            "arousal": 0.65, "valence": 0.75,
            "energetic": 0.55, "radiant": 0.70,
            "happy": 0.60, "brilliant": 0.60,
            "sad": 0.10, "relaxed": 0.20,
        },
        "weights": {
            "arousal": 2.0, "valence": 2.5,
            "energetic": 2.0, "radiant": 2.0,
            "happy": 1.5, "brilliant": 1.5,
            "sad": 2.0, "relaxed": 1.0,
        },
    },
    "mysterious": {
        "group": "mood",
        "label": "Mysterious",
        "desc": "Dark, textured, noisy -- shadows and atmosphere",
        "target": {
            "arousal": 0.35, "valence": 0.25,
            "somber": 0.65, "contemplative": 0.55,
            "hypnotic": 0.50, "instrumental": 0.70,
            "happy": 0.10, "radiant": 0.20,
        },
        "weights": {
            "arousal": 1.5, "valence": 2.0,
            "somber": 2.5, "contemplative": 2.0,
            "hypnotic": 1.5, "instrumental": 1.0,
            "happy": 2.0, "radiant": 1.5,
        },
    },

    # === Support ===
    "stress_relief": {
        "group": "support",
        "label": "Stress Relief",
        "desc": "Warm, predictable, spacious -- let the nervous system settle",
        "target": {
            "arousal": 0.20, "valence": 0.60,
            "relaxed": 0.85, "contemplative": 0.55,
            "warm": 0.65, "hypnotic": 0.55,
            "aggressive": 0.02, "energetic": 0.10,
        },
        "weights": {
            "arousal": 2.5, "valence": 1.5,
            "relaxed": 2.5, "contemplative": 1.5,
            "warm": 1.5, "hypnotic": 1.5,
            "aggressive": 2.5, "energetic": 2.0,
        },
    },
    "recovery": {
        "group": "support",
        "label": "Recovery",
        "desc": "Filtered, ambient, gentle -- physiological restoration",
        "target": {
            "arousal": 0.08, "valence": 0.45,
            "energetic": 0.03, "still": 0.92,
            "relaxed": 0.92, "contemplative": 0.65,
            "aggressive": 0.01, "danceable": 0.02,
        },
        "weights": {
            "arousal": 3.0, "valence": 0.5,
            "energetic": 3.0, "still": 3.0,
            "relaxed": 2.5, "contemplative": 1.5,
            "aggressive": 3.0, "danceable": 2.0,
        },
    },
}
