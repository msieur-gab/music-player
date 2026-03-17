"""Soniq audio feature tags — read/write feature signatures in m4a and mp3 files.

Stores extracted audio features + classifier outputs directly in the file's
metadata as JSON, making the library fully portable. On startup, features can
be loaded from tags in seconds instead of re-running librosa (hours).

Schema v0.6:
  {
    "src": "soniq",
    "v": "0.6",
    "at": "2026-03-17T...",
    "s": { 25 scalar features },
    "vec": { mfcc_m, chroma, tonnetz },
    "cls": { classifier outputs }
  }

Storage:
  m4a -> custom MP4 atom: ----:com.soniq:features
  mp3 -> ID3 TXXX frame:  com.soniq:features
"""

import json
import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)

CURRENT_VERSION = "0.7"
TAG_DESC = "com.soniq:features"
MP4_ATOM = "----:com.soniq:features"

SCALAR_KEYS = [
    "duration", "tempo", "key", "mode",
    "rms_mean", "rms_variance",
    "centroid_mean", "centroid_std", "bandwidth_std", "flatness_mean",
    "spectral_flux", "flux_std",
    "onset_strength", "beat_strength",
    "treble_ratio", "mfcc_delta_var", "mod_crest",
    "harm_energy", "perc_energy", "harm_fraction",
    "beat_regularity", "rhythm_complexity", "plp_stability", "onset_rate",
    "chroma_major_corr",
]

# Maps DB column names (long) → tag short keys.
# Must match what soniq-lab v0.7 writes.
SCALAR_SHORT = {
    "duration": "duration", "tempo": "tempo", "key": "key", "mode": "mode",
    "rms_mean": "rms_mean", "rms_variance": "rms_var",
    "centroid_mean": "centroid", "centroid_std": "centroid_std",
    "bandwidth_std": "bandwidth_std", "flatness_mean": "flatness",
    "spectral_flux": "flux", "flux_std": "flux_std",
    "onset_strength": "onset", "beat_strength": "beat",
    "treble_ratio": "treble_ratio", "mfcc_delta_var": "mfcc_delta_var",
    "mod_crest": "mod_crest",
    "harm_energy": "harm_energy", "perc_energy": "perc_energy",
    "harm_fraction": "harm_fraction",
    "beat_regularity": "beat_regularity", "rhythm_complexity": "rhythm_complexity",
    "plp_stability": "plp_stability", "onset_rate": "onset_rate",
    "chroma_major_corr": "chroma_major_corr",
}

SCALAR_FULL = {v: k for k, v in SCALAR_SHORT.items()}

# Classifier keys stored in cls section
CLS_KEYS = [
    "arousal", "valence", "happy", "sad", "relaxed", "aggressive",
    "danceable", "party", "energetic", "still", "hypnotic", "varied",
    "instrumental", "vocal", "brilliant", "warm", "radiant", "somber",
    "contemplative", "restless",
]


def _round(val, decimals=4):
    if isinstance(val, (int, float)):
        return round(val, decimals)
    return val


def features_to_tag(features, classifications=None):
    """Convert extractor output dict + classifier outputs to tag JSON string."""
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
    if "chroma_mean" in features:
        tag["vec"]["chroma"] = [_round(v) for v in features["chroma_mean"]]
    if "tonnetz_mean" in features:
        tag["vec"]["tonnetz"] = [_round(v) for v in features["tonnetz_mean"]]

    if classifications:
        cls = {}
        for k in CLS_KEYS:
            if k in classifications:
                cls[k] = _round(classifications[k])
        # Store energy components and hypnotic path as sub-dicts
        if "_energy_components" in classifications:
            cls["nrg"] = {k: _round(v) for k, v in classifications["_energy_components"].items()}
        if "_hypnotic_path" in classifications:
            cls["hypnotic_path"] = classifications["_hypnotic_path"]
        if "genre" in classifications:
            cls["genre"] = classifications["genre"]
        tag["cls"] = cls

    return json.dumps(tag, separators=(",", ":"))


def tag_to_features(tag_json):
    """Parse tag JSON string back to extractor-compatible feature dict.

    Returns (features_dict, classifications_dict, version_str) or
    (None, None, None) on failure.
    """
    try:
        tag = json.loads(tag_json)
    except (json.JSONDecodeError, TypeError):
        return None, None, None

    version = tag.get("v")
    if not version:
        return None, None, None

    features = {}

    s = tag.get("s", {})
    for short_key, val in s.items():
        full_key = SCALAR_FULL.get(short_key, short_key)
        features[full_key] = val

    vec = tag.get("vec", {})
    if "mfcc_m" in vec:
        features["mfcc_mean"] = vec["mfcc_m"]
    if "chroma" in vec:
        features["chroma_mean"] = vec["chroma"]
    if "tonnetz" in vec:
        features["tonnetz_mean"] = vec["tonnetz"]

    # Parse classifier outputs
    classifications = None
    cls = tag.get("cls")
    if cls:
        classifications = {}
        for k in CLS_KEYS:
            if k in cls:
                classifications[k] = cls[k]
        if "nrg" in cls:
            classifications["_energy_components"] = cls["nrg"]
        if "hypnotic_path" in cls:
            classifications["_hypnotic_path"] = cls["hypnotic_path"]
        if "genre" in cls:
            classifications["genre"] = cls["genre"]

    return features, classifications, version


def write_tag(filepath, features, classifications=None):
    """Write Soniq features tag to an audio file (m4a or mp3)."""
    tag_json = features_to_tag(features, classifications)
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

    Returns (features_dict, classifications_dict, version_str) or
    (None, None, None) if no tag found.
    """
    ext = filepath.lower().rsplit(".", 1)[-1] if "." in filepath else ""

    try:
        if ext == "m4a":
            tag_json = _read_m4a(filepath)
        elif ext == "mp3":
            tag_json = _read_mp3(filepath)
        else:
            return None, None, None

        if tag_json:
            return tag_to_features(tag_json)
    except Exception as e:
        log.debug("Failed to read tag from %s: %s", filepath, e)

    return None, None, None


def has_current_tag(filepath):
    """Check if a file has a Soniq tag with the current version."""
    _, _, version = read_tag(filepath)
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
