# Soniq Audio Feature Tags

## Problem

Extracting audio features with librosa is slow — a 341-track library takes **hours** to analyze using multi-point spectral sampling. Features were stored in a local SQLite database, meaning:

- Moving the library to another device required re-analysis from scratch
- A corrupted or deleted DB meant hours of lost work
- The DB was a single point of failure with no backup in the files themselves

## Solution

Embed extracted audio features **directly inside each audio file** as metadata tags. The files become self-describing — they carry their own audio intelligence.

- **m4a (MP4)**: custom atom `----:com.soniq:features`
- **mp3 (ID3)**: TXXX frame with description `com.soniq:features`

Tags are written using [mutagen](https://mutagen.readthedocs.io/) and do not alter the audio stream. On m4a files, the JSON payload (~455 bytes) fits inside existing MP4 padding — **zero file size increase**.

## Schema v0.1

```json
{
  "src": "soniq",
  "v": "0.1",
  "at": "2026-03-09T17:02:54Z",
  "s": {
    "duration": 303.4,
    "tempo": 112.3,
    "key": 8,
    "mode": 0,
    "rms_mean": -11.9,
    "rms_max": -5.4,
    "rms_var": 0.25,
    "dyn_range": 19.9,
    "centroid": 1108.5,
    "flatness": 0.0037,
    "flux": 94.4,
    "onset": 1.33,
    "beat": 1.59,
    "vocal": 0.44,
    "zcr": 0.038
  },
  "vec": {
    "mfcc_m": [13 floats],
    "mfcc_s": [13 floats],
    "contrast": [7 floats]
  }
}
```

### Fields

| Field | Description |
|-------|-------------|
| `src` | App identifier — always `"soniq"` |
| `v` | Schema version string — enables re-extraction when schema changes |
| `at` | ISO 8601 UTC timestamp of extraction |
| `s` | 15 scalar features (compact short keys) |
| `vec` | 3 vector features (33 floats total) |

### Scalar key mapping

| Full key | Short key | Description |
|----------|-----------|-------------|
| `duration` | `duration` | Track length in seconds |
| `tempo` | `tempo` | BPM estimate |
| `key` | `key` | Musical key (0-11, C to B) |
| `mode` | `mode` | 0 = minor, 1 = major |
| `rms_mean` | `rms_mean` | Average loudness (dB) |
| `rms_max` | `rms_max` | Peak loudness (dB) |
| `rms_variance` | `rms_var` | Loudness variation |
| `dynamic_range` | `dyn_range` | Loudness spread (dB) |
| `centroid_mean` | `centroid` | Spectral brightness (Hz) |
| `flatness_mean` | `flatness` | Noise vs tone (0-1) |
| `spectral_flux` | `flux` | Rate of spectral change |
| `onset_strength` | `onset` | Attack intensity |
| `beat_strength` | `beat` | Rhythmic prominence |
| `vocal_proxy` | `vocal` | Vocal presence estimate (0-1) |
| `zcr_mean` | `zcr` | Zero-crossing rate |

### Vector features

| Key | Dimensions | Description |
|-----|-----------|-------------|
| `mfcc_m` | 13 | MFCC means — timbral identity |
| `mfcc_s` | 13 | MFCC std deviations — timbral consistency |
| `contrast` | 7 | Spectral contrast bands — harmonic structure |

## Startup Logic

```
For each audio file:
  1. Already in DB?           → skip
  2. Has tag, version matches → load into DB (fast path)
  3. Has tag, version old     → re-extract with librosa, overwrite tag
  4. No tag                   → extract with librosa, write tag + DB
```

**Performance**: 341 tracks rebuild from tags into SQLite in ~3 seconds. The same library takes hours to extract with librosa.

## Versioning

The `v` field enables forward compatibility. When the schema changes (new features, different extraction parameters), bump `CURRENT_VERSION` in `tags.py`. On next startup, tracks with outdated versions are automatically re-extracted and re-tagged.

## File structure

| File | Role |
|------|------|
| `tags.py` | Read/write Soniq tags (mutagen) |
| `extractor.py` | librosa feature extraction |
| `analyzer.py` | Library scanning, tag-first loading, classification |
| `db.py` | SQLite schema and track storage |

## Known issue: librosa deprecation warnings

When extracting features from m4a files, librosa produces deprecation warnings:

```
DeprecationWarning: 'aifc' is deprecated and slated for removal in Python 3.13
DeprecationWarning: 'audioop' is deprecated and slated for removal in Python 3.13
UserWarning: PySoundFile failed. Trying audioread instead.
FutureWarning: librosa.core.audio.__audioread_load Deprecated as of librosa version 0.10.0.
```

**Why**: PySoundFile (libsndfile) cannot decode AAC/m4a. librosa falls back to `audioread`, which works but is deprecated and will be removed in librosa 1.0.

**Impact**: None for now. We're on Python 3.11 + librosa 0.11 — everything works, warnings are cosmetic. Since tags make extraction a one-time cost per track, this only runs once per file.

**Future fix** (when librosa 1.0 drops audioread): pre-decode m4a to WAV via ffmpeg before passing to librosa, or use an ffmpeg-based audio backend.
