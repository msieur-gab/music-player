#!/usr/bin/env python3
"""Soniq audio feature tags — read/write feature signatures in m4a and mp3 files.

Stores extracted audio features directly in the file's metadata as JSON,
making the library fully portable. On startup, features can be loaded from
tags in seconds instead of re-running librosa (hours).

Schema v0.1:
  {
    "src": "soniq",
    "v": "0.1",
    "at": "2026-03-09T11:45:21Z",
    "s": { 15 scalar features },
    "vec": { mfcc_m, mfcc_s, contrast }
  }

Storage:
  m4a → custom MP4 atom: ----:com.soniq:features
  mp3 → ID3 TXXX frame:  com.soniq:features
"""

import json
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

CURRENT_VERSION = "0.1"
TAG_DESC = "com.soniq:features"
MP4_ATOM = "----:com.soniq:features"

# Scalar feature keys (must match extractor output)
SCALAR_KEYS = [
    "duration", "tempo", "key", "mode",
    "rms_mean", "rms_max", "rms_variance", "dynamic_range",
    "centroid_mean", "flatness_mean", "spectral_flux",
    "onset_strength", "beat_strength", "vocal_proxy", "zcr_mean",
]

# Short keys for compact JSON storage
SCALAR_SHORT = {
    "duration": "duration", "tempo": "tempo", "key": "key", "mode": "mode",
    "rms_mean": "rms_mean", "rms_max": "rms_max", "rms_variance": "rms_var",
    "dynamic_range": "dyn_range", "centroid_mean": "centroid",
    "flatness_mean": "flatness", "spectral_flux": "flux",
    "onset_strength": "onset", "beat_strength": "beat",
    "vocal_proxy": "vocal", "zcr_mean": "zcr",
}

# Reverse: short → full
SCALAR_FULL = {v: k for k, v in SCALAR_SHORT.items()}


def _round(val, decimals=4):
    """Round a float for compact storage."""
    if isinstance(val, (int, float)):
        return round(val, decimals)
    return val


def features_to_tag(features):
    """Convert extractor output dict to tag JSON string."""
    tag = {
        "src": "soniq",
        "v": CURRENT_VERSION,
        "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "s": {},
        "vec": {},
    }

    for full_key, short_key in SCALAR_SHORT.items():
        if full_key in features:
            tag["s"][short_key] = _round(features[full_key])

    if "mfcc_mean" in features:
        tag["vec"]["mfcc_m"] = [_round(v) for v in features["mfcc_mean"]]
    if "mfcc_std" in features:
        tag["vec"]["mfcc_s"] = [_round(v) for v in features["mfcc_std"]]
    if "contrast_mean" in features:
        tag["vec"]["contrast"] = [_round(v) for v in features["contrast_mean"]]

    return json.dumps(tag, separators=(",", ":"))


def tag_to_features(tag_json):
    """Parse tag JSON string back to extractor-compatible feature dict.

    Returns (features_dict, version_str) or (None, None) on failure.
    """
    try:
        tag = json.loads(tag_json)
    except (json.JSONDecodeError, TypeError):
        return None, None

    version = tag.get("v")
    if not version:
        return None, None

    features = {}

    # Scalars
    s = tag.get("s", {})
    for short_key, val in s.items():
        full_key = SCALAR_FULL.get(short_key, short_key)
        features[full_key] = val

    # Vectors
    vec = tag.get("vec", {})
    if "mfcc_m" in vec:
        features["mfcc_mean"] = vec["mfcc_m"]
    if "mfcc_s" in vec:
        features["mfcc_std"] = vec["mfcc_s"]
    if "contrast" in vec:
        features["contrast_mean"] = vec["contrast"]

    return features, version


def write_tag(filepath, features):
    """Write Soniq features tag to an audio file (m4a or mp3)."""
    tag_json = features_to_tag(features)
    ext = filepath.lower().rsplit(".", 1)[-1] if "." in filepath else ""

    try:
        if ext == "m4a":
            _write_m4a(filepath, tag_json)
        elif ext == "mp3":
            _write_mp3(filepath, tag_json)
        else:
            log.debug("Unsupported format for tag writing: %s", ext)
            return False
        return True
    except Exception as e:
        log.warning("Failed to write tag to %s: %s", filepath, e)
        return False


def read_tag(filepath):
    """Read Soniq features tag from an audio file.

    Returns (features_dict, version_str) or (None, None) if no tag found.
    """
    ext = filepath.lower().rsplit(".", 1)[-1] if "." in filepath else ""

    try:
        if ext == "m4a":
            tag_json = _read_m4a(filepath)
        elif ext == "mp3":
            tag_json = _read_mp3(filepath)
        else:
            return None, None

        if tag_json:
            return tag_to_features(tag_json)
    except Exception as e:
        log.debug("Failed to read tag from %s: %s", filepath, e)

    return None, None


def has_current_tag(filepath):
    """Check if a file has a Soniq tag with the current version."""
    _, version = read_tag(filepath)
    return version == CURRENT_VERSION


# ---------------------------------------------------------------------------
# M4A (MP4) tag operations
# ---------------------------------------------------------------------------

def _write_m4a(filepath, tag_json):
    from mutagen.mp4 import MP4

    audio = MP4(filepath)
    if audio.tags is None:
        audio.add_tags()
    audio.tags[MP4_ATOM] = [tag_json.encode("utf-8")]
    audio.save()


def _read_m4a(filepath):
    from mutagen.mp4 import MP4

    audio = MP4(filepath)
    if audio.tags and MP4_ATOM in audio.tags:
        val = audio.tags[MP4_ATOM]
        if val:
            raw = val[0]
            return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)
    return None


# ---------------------------------------------------------------------------
# MP3 (ID3) tag operations
# ---------------------------------------------------------------------------

def _write_mp3(filepath, tag_json):
    from mutagen.id3 import ID3, TXXX
    from mutagen.id3 import ID3NoHeaderError

    try:
        audio = ID3(filepath)
    except ID3NoHeaderError:
        audio = ID3()

    # Remove existing tag if present
    for key in list(audio.keys()):
        if key.startswith("TXXX:") and TAG_DESC in key:
            del audio[key]

    audio.add(TXXX(encoding=3, desc=TAG_DESC, text=[tag_json]))
    audio.save(filepath)


def _read_mp3(filepath):
    from mutagen.id3 import ID3

    try:
        audio = ID3(filepath)
    except Exception:
        return None

    key = f"TXXX:{TAG_DESC}"
    if key in audio:
        texts = audio[key].text
        if texts:
            return texts[0]
    return None
