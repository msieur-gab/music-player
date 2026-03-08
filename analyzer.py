#!/usr/bin/env python3
"""
Audio feature extraction using ffmpeg — zero additional dependencies.
Extracts spectral and energy features for music similarity matching.
"""

import subprocess
import json
import os
import re
import math

FEATURES_FILE = ".audio_features.json"
FEATURE_VERSION = 1

# Regex patterns for astats overall summary (stderr)
ASTATS_KEYS = {
    "rms_level_db":       r"RMS level dB:\s*([-\d.]+(?:inf)?)",
    "peak_level_db":      r"Peak level dB:\s*([-\d.]+(?:inf)?)",
    "rms_peak_db":        r"RMS peak dB:\s*([-\d.]+(?:inf)?)",
    "rms_trough_db":      r"RMS trough dB:\s*([-\d.]+(?:inf)?)",
    "flat_factor":        r"Flat factor:\s*([\d.]+)",
    "noise_floor_db":     r"Noise floor dB:\s*([-\d.]+(?:inf)?)",
    "entropy":            r"Entropy:\s*([\d.]+)",
    "mean_difference":    r"Mean difference:\s*([\d.]+)",
}

# Spectral measures from aspectralstats (we compute mean + std per track)
SPECTRAL_MEASURES = ["centroid", "spread", "rolloff", "flatness", "flux"]

# Full ordered feature vector for similarity computation
FEATURE_ORDER = (
    list(ASTATS_KEYS.keys()) + ["dynamic_range"]
    + [f"spectral_{m}_mean" for m in SPECTRAL_MEASURES]
    + [f"spectral_{m}_std" for m in SPECTRAL_MEASURES]
)


# ---------------------------------------------------------------------------
# Single-track analysis
# ---------------------------------------------------------------------------

def analyze_track(filepath):
    """Extract audio features from one MP3 file. Returns dict or None."""
    if not os.path.isfile(filepath):
        return None

    features = {}

    # Pass 1 — energy / dynamics
    astats = _run_astats(filepath)
    if not astats:
        return None
    features.update(astats)

    # Pass 2 — spectral character
    spectral = _run_spectral(filepath)
    if spectral:
        features.update(spectral)
    else:
        # Spectral extraction failed (old ffmpeg?) — fill zeros
        for m in SPECTRAL_MEASURES:
            features[f"spectral_{m}_mean"] = 0.0
            features[f"spectral_{m}_std"] = 0.0

    return features


def _run_astats(filepath):
    """Run ffmpeg astats filter, parse overall summary from stderr."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", filepath,
             "-af", "astats=measure_perchannel=none",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=60,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    out = {}
    for key, pattern in ASTATS_KEYS.items():
        m = re.search(pattern, r.stderr)
        if m:
            raw = m.group(1)
            if "inf" in raw:
                out[key] = -100.0 if "-" in raw else 100.0
            else:
                try:
                    out[key] = float(raw)
                except ValueError:
                    out[key] = 0.0
        else:
            out[key] = 0.0

    # Dynamic range: peak-to-trough, or peak-to-RMS if trough is silence
    if out["rms_trough_db"] > -99:
        out["dynamic_range"] = out["rms_peak_db"] - out["rms_trough_db"]
    else:
        out["dynamic_range"] = out["rms_peak_db"] - out["rms_level_db"]

    return out


def _run_spectral(filepath):
    """Run ffmpeg aspectralstats, collect per-frame values, return mean+std."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", filepath, "-t", "90",
             "-af", "aspectralstats,ametadata=print:file=-",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None

    # Collect per-frame values, channel 1 only
    buckets = {m: [] for m in SPECTRAL_MEASURES}
    for line in r.stdout.splitlines():
        # Only use channel 1 (`.1.`)
        if ".2." in line:
            continue
        for m in SPECTRAL_MEASURES:
            if f".{m}=" in line:
                try:
                    val = float(line.split("=", 1)[1])
                    # Skip silence frames (centroid=1, spread=1 etc. = no signal)
                    if math.isfinite(val) and not (m in ("centroid", "spread") and val <= 1):
                        buckets[m].append(val)
                except (ValueError, IndexError):
                    pass

    out = {}
    for m in SPECTRAL_MEASURES:
        vals = buckets[m]
        if vals:
            mean = sum(vals) / len(vals)
            std = (sum((v - mean) ** 2 for v in vals) / len(vals)) ** 0.5
            out[f"spectral_{m}_mean"] = round(mean, 4)
            out[f"spectral_{m}_std"] = round(std, 4)
        else:
            out[f"spectral_{m}_mean"] = 0.0
            out[f"spectral_{m}_std"] = 0.0

    return out


# ---------------------------------------------------------------------------
# Library scanning
# ---------------------------------------------------------------------------

def analyze_library(music_root, on_progress=None):
    """Analyze all MP3s in the library. Incremental — skips already-analyzed."""
    db = load_features(music_root)
    mp3s = _find_mp3s(music_root)
    total = len(mp3s)
    analyzed = 0
    skipped = 0

    for i, path in enumerate(mp3s, 1):
        artist, album, title = _info_from_path(path, music_root)
        key = f"{artist}::{album}::{title}"

        if key in db["tracks"]:
            skipped += 1
            if on_progress:
                on_progress({"message": f"Skipping {i}/{total}: {title}",
                             "track": i, "total": total, "status": "skipped"})
            continue

        if on_progress:
            on_progress({"message": f"Analyzing {i}/{total}: {title}",
                         "track": i, "total": total, "status": "analyzing"})

        feats = analyze_track(path)
        if feats:
            db["tracks"][key] = {
                "artist": artist, "album": album, "title": title,
                "file": os.path.relpath(path, music_root),
                "features": feats,
            }
            analyzed += 1

        # Save periodically
        if analyzed % 5 == 0:
            save_features(music_root, db)

    save_features(music_root, db)

    if on_progress:
        on_progress({
            "message": f"Done — {analyzed} new tracks analyzed ({skipped} already known)",
            "analyzed": analyzed, "skipped": skipped, "total": total,
            "status": "complete",
        })

    return db


def _find_mp3s(music_root):
    mp3s = []
    for root, _, files in os.walk(music_root):
        for f in sorted(files):
            if f.lower().endswith(".mp3") and not f.startswith("_temp_"):
                mp3s.append(os.path.join(root, f))
    return mp3s


def _info_from_path(filepath, music_root):
    """Derive artist/album/title from path: root/Artist/Album/01 - Title.mp3"""
    rel = os.path.relpath(filepath, music_root)
    parts = rel.replace("\\", "/").split("/")
    artist = parts[0] if len(parts) >= 3 else "Unknown"
    album = parts[1] if len(parts) >= 3 else (parts[0] if len(parts) >= 2 else "Unknown")
    fname = os.path.splitext(parts[-1])[0]
    m = re.match(r"^\d+\s*[-\u2013]\s*(.+)$", fname)
    title = m.group(1).strip() if m else fname
    return artist, album, title


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

def find_similar(track_key, music_root, limit=10):
    """Return tracks most similar to the given one, ranked by cosine similarity."""
    db = load_features(music_root)

    if track_key not in db["tracks"]:
        return []

    target = db["tracks"][track_key]["features"]
    others = {k: v for k, v in db["tracks"].items() if k != track_key}
    if not others:
        return []

    # Compute min/max across entire library for normalization
    all_feats = [v["features"] for v in db["tracks"].values()]
    ranges = {}
    for feat in FEATURE_ORDER:
        vals = [f.get(feat, 0) for f in all_feats]
        lo, hi = min(vals), max(vals)
        ranges[feat] = (lo, hi)

    def to_vec(features):
        return [
            (features.get(f, 0) - lo) / (hi - lo) if (hi := ranges[f][1]) > (lo := ranges[f][0]) else 0
            for f in FEATURE_ORDER
        ]

    target_vec = to_vec(target)

    results = []
    for key, data in others.items():
        vec = to_vec(data["features"])
        score = _cosine(target_vec, vec)
        results.append({
            "key": key,
            "artist": data["artist"],
            "album": data["album"],
            "title": data["title"],
            "file": data.get("file", ""),
            "score": round(score, 4),
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:limit]


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def load_features(music_root):
    path = os.path.join(music_root, FEATURES_FILE)
    if os.path.isfile(path):
        try:
            with open(path) as f:
                db = json.load(f)
            if db.get("version") == FEATURE_VERSION:
                return db
        except (json.JSONDecodeError, IOError):
            pass
    return {"version": FEATURE_VERSION, "tracks": {}}


def save_features(music_root, db):
    path = os.path.join(music_root, FEATURES_FILE)
    with open(path, "w") as f:
        json.dump(db, f)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <music_root>")
        print(f"       {sys.argv[0]} --similar <music_root> 'Artist::Album::Title'")
        sys.exit(1)

    if sys.argv[1] == "--similar" and len(sys.argv) >= 4:
        root = sys.argv[2]
        key = sys.argv[3]
        results = find_similar(key, root)
        for r in results:
            print(f"  {r['score']:.3f}  {r['artist']} — {r['title']}")
    else:
        root = sys.argv[1]
        print(f"Analyzing library: {root}")
        analyze_library(root, on_progress=lambda d: print(f"  {d['message']}"))
        print("Done.")
