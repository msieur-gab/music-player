#!/usr/bin/env python3
"""
Audio feature extraction using ffmpeg — zero additional dependencies.
Extracts spectral and energy features for music similarity matching.
Storage: SQLite (stdlib) — scales to 100k+ tracks without full-file rewrites.
"""

import subprocess
import sqlite3
import json
import os
import re
import math

DB_FILE = ".audio_features.db"
SCHEMA_VERSION = 5

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

# Column names for feature storage (matches FEATURE_ORDER)
_FEAT_COLS = FEATURE_ORDER

# Zone score column names — derived from ZONES dict below
ZONE_IDS = [
    # Activities
    "focus", "creative", "meditation", "energize", "sleep",
    # Moods
    "joy", "calm", "melancholy", "heroic", "mysterious",
    # Support
    "stress_relief", "recovery",
]
_ZONE_COLS = [f"zone_{z}" for z in ZONE_IDS]


# ---------------------------------------------------------------------------
# SQLite database
# ---------------------------------------------------------------------------

def _db_path(music_root):
    return os.path.join(music_root, DB_FILE)


def _connect(music_root):
    """Open (and create/migrate if needed) the features database."""
    path = _db_path(music_root)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn):
    """Create tables if they don't exist, migrate if schema changed."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return

    feat_cols = ", ".join(f"{c} REAL DEFAULT 0" for c in _FEAT_COLS)
    zone_cols = ", ".join(f"{c} REAL DEFAULT 0" for c in _ZONE_COLS)

    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS tracks (
            key TEXT PRIMARY KEY,
            artist TEXT NOT NULL,
            album TEXT NOT NULL,
            title TEXT NOT NULL,
            file TEXT NOT NULL,
            {feat_cols},
            {zone_cols}
        );

        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS playlists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            zone_id TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS playlist_tracks (
            playlist_id INTEGER NOT NULL,
            position INTEGER NOT NULL,
            track_key TEXT NOT NULL,
            FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE,
            PRIMARY KEY (playlist_id, position)
        );
    """)

    # Add any missing columns (handles v2 → v3 migration with new zones)
    existing_cols = {row[1] for row in conn.execute("PRAGMA table_info(tracks)").fetchall()}
    for col in _FEAT_COLS + _ZONE_COLS:
        if col not in existing_cols:
            conn.execute(f"ALTER TABLE tracks ADD COLUMN {col} REAL DEFAULT 0")

    # Create indexes
    conn.execute("CREATE INDEX IF NOT EXISTS idx_artist ON tracks(artist)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_album ON tracks(artist, album)")
    for zone_id in ZONE_IDS:
        conn.execute(f"CREATE INDEX IF NOT EXISTS idx_zone_{zone_id} ON tracks(zone_{zone_id})")

    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()

    if version > 0 and version < SCHEMA_VERSION:
        if version < 4:
            # v4 changed dynamic_range calculation — features must be recomputed
            conn.execute("DELETE FROM tracks")
            conn.execute("DELETE FROM meta WHERE key = 'norm_ranges'")
            conn.commit()
            print("  Schema v4: cleared tracks for re-analysis (dynamic_range fix)")
        elif version < 5:
            # v5 only adds playlist tables (already created above) — rescore zones
            _rescore_all(conn)


def _rescore_all(conn):
    """Re-classify all tracks against updated zones. No re-analysis needed."""
    rows = conn.execute("SELECT key, " + ", ".join(_FEAT_COLS) + " FROM tracks").fetchall()
    zone_set_clause = ", ".join(f"zone_{z} = ?" for z in ZONE_IDS)
    for row in rows:
        feats = {f: row[f] for f in _FEAT_COLS}
        scores = classify_track(feats)
        vals = [scores.get(z, 0.0) for z in ZONE_IDS] + [row["key"]]
        conn.execute(f"UPDATE tracks SET {zone_set_clause} WHERE key = ?", vals)
    conn.commit()


# ---------------------------------------------------------------------------
# Single-track analysis (unchanged — pure ffmpeg)
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

    # Dynamic range: crest factor (peak RMS vs average RMS)
    # NOT peak-to-trough — trough catches silence/fades giving 80+ dB nonsense
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
        if ".2." in line:
            continue
        for m in SPECTRAL_MEASURES:
            if f".{m}=" in line:
                try:
                    val = float(line.split("=", 1)[1])
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
    conn = _connect(music_root)
    existing = {row[0] for row in conn.execute("SELECT key FROM tracks").fetchall()}

    mp3s = _find_mp3s(music_root)
    total = len(mp3s)
    analyzed = 0
    skipped = 0

    for i, path in enumerate(mp3s, 1):
        artist, album, title = _info_from_path(path, music_root)
        key = f"{artist}::{album}::{title}"

        if key in existing:
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
            zone_scores = classify_track(feats)
            _insert_track(conn, key, artist, album, title,
                          os.path.relpath(path, music_root), feats, zone_scores)
            analyzed += 1

    # Update normalization ranges after batch
    _update_norm_ranges(conn)
    conn.close()

    if on_progress:
        on_progress({
            "message": f"Done — {analyzed} new tracks analyzed ({skipped} already known)",
            "analyzed": analyzed, "skipped": skipped, "total": total,
            "status": "complete",
        })


def _insert_track(conn, key, artist, album, title, file, features, zone_scores):
    """Insert a single track with features and zone scores."""
    cols = ["key", "artist", "album", "title", "file"] + _FEAT_COLS + _ZONE_COLS
    vals = [key, artist, album, title, file]
    vals += [features.get(f, 0.0) for f in _FEAT_COLS]
    vals += [zone_scores.get(z, 0.0) for z in ZONE_IDS]

    placeholders = ", ".join("?" * len(cols))
    col_names = ", ".join(cols)

    conn.execute(f"INSERT OR REPLACE INTO tracks ({col_names}) VALUES ({placeholders})", vals)
    conn.commit()


def _update_norm_ranges(conn):
    """Cache min/max per feature for fast similarity normalization."""
    ranges = {}
    for feat in _FEAT_COLS:
        row = conn.execute(f"SELECT MIN({feat}), MAX({feat}) FROM tracks").fetchone()
        if row and row[0] is not None:
            ranges[feat] = [row[0], row[1]]
        else:
            ranges[feat] = [0.0, 0.0]
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        ("norm_ranges", json.dumps(ranges))
    )
    conn.commit()


def _get_norm_ranges(conn):
    """Load cached normalization ranges."""
    row = conn.execute("SELECT value FROM meta WHERE key = ?", ("norm_ranges",)).fetchone()
    if row:
        return json.loads(row[0])
    # Compute on the fly if not cached
    _update_norm_ranges(conn)
    row = conn.execute("SELECT value FROM meta WHERE key = ?", ("norm_ranges",)).fetchone()
    return json.loads(row[0]) if row else {}


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
# Activity zones — thresholds from neuro-acoustic research
# ---------------------------------------------------------------------------

ZONES = {
    # ═══════════════════════════════════════════════════════════════════
    # Activities — mapped to brainwave states from neuro-acoustic research
    # ═══════════════════════════════════════════════════════════════════

    "focus": {
        # Beta state (14-30 Hz) — bright, dynamic, tonal, moderate DR
        # Research: centroid 3-5 kHz, rolloff 6-8 kHz, high flux, PLR 10-12
        # Library p75+ centroid, p75+ rolloff, above-median flux, loud
        "group": "activity",
        "label": "Deep Focus",
        "desc": "Bright, dynamic, tonal — sustained cognitive alertness",
        "ideal": {
            "spectral_centroid_mean": (2500, 4500),
            "spectral_rolloff_mean":  (5000, 8000),
            "spectral_flatness_mean": (0.02, 0.07),   # tonal for music (below median)
            "spectral_flux_mean":     (0.04, 0.07),    # above median — dynamic
            "rms_level_db":           (-14, -10),       # moderate to loud
            "dynamic_range":          (5, 10),          # compressed enough for consistency
        },
    },
    "creative": {
        # Alpha state (8-12 Hz) — balanced, harmonic, fluid, relaxed alertness
        # Research: centroid 1.5-3 kHz, rolloff 4-6 kHz, moderate flux
        # Library IQR centroid, below-median flatness, moderate flux
        "group": "activity",
        "label": "Creative Flow",
        "desc": "Balanced, harmonic, fluid — relaxed alertness",
        "ideal": {
            "spectral_centroid_mean": (1500, 2500),
            "spectral_rolloff_mean":  (3000, 5200),
            "spectral_flatness_mean": (0.02, 0.06),   # harmonic / tonal
            "spectral_flux_mean":     (0.02, 0.04),    # fluid, not driving
            "rms_level_db":           (-18, -13),       # softer than focus
            "dynamic_range":          (6, 12),
        },
    },
    "meditation": {
        # Theta state (4-8 Hz) — warm, static, organic, very quiet
        # Research: centroid < 1.5 kHz, rolloff < 4 kHz, very low flux
        # Library below-p25 centroid and rolloff, below-p10 flux
        "group": "activity",
        "label": "Meditation",
        "desc": "Warm, still, organic — theta state, inner quiet",
        "ideal": {
            "spectral_centroid_mean": (400, 1400),
            "spectral_rolloff_mean":  (800, 2800),
            "spectral_flatness_mean": (0.04, 0.10),   # organic / slightly breathy
            "spectral_flux_mean":     (0.005, 0.02),   # very static
            "rms_level_db":           (-25, -16),       # quiet
            "dynamic_range":          (6, 15),
        },
    },
    "energize": {
        # High arousal — bright, loud, driving, compressed
        # Research: high centroid, high flux, sympathetic activation
        # Library p75+ centroid, p90+ flux, p75+ RMS, low DR
        "group": "activity",
        "label": "Energy",
        "desc": "Loud, bright, driving — get moving",
        "ideal": {
            "spectral_centroid_mean": (2500, 5500),
            "spectral_rolloff_mean":  (5000, 9000),
            "spectral_flatness_mean": (0.04, 0.12),   # doesn't matter much
            "spectral_flux_mean":     (0.05, 0.08),    # p75+ — very dynamic
            "rms_level_db":           (-12, -8),        # loud
            "dynamic_range":          (3, 8),           # compressed, punchy
        },
    },
    "sleep": {
        # Delta state (1-4 Hz) — very warm, filtered, near-silent
        # Research: centroid < 1 kHz, rolloff < 1 kHz, very low everything
        # Library bottom-10% across all energy/brightness features
        "group": "activity",
        "label": "Sleep",
        "desc": "Dark, filtered, barely there — drift off",
        "ideal": {
            "spectral_centroid_mean": (300, 1000),
            "spectral_rolloff_mean":  (500, 1800),
            "spectral_flatness_mean": (0.06, 0.15),   # breathy / ambient
            "spectral_flux_mean":     (0.002, 0.015),  # near-static
            "rms_level_db":           (-40, -20),       # very quiet
            "dynamic_range":          (5, 15),
        },
    },

    # ═══════════════════════════════════════════════════════════════════
    # Moods — mapped via Circumplex Model (arousal × valence)
    # ═══════════════════════════════════════════════════════════════════

    "joy": {
        # High arousal, positive valence — bright, tonal, rhythmic
        # Research: high centroid, low flatness, high flux, PLR 10-12
        "group": "mood",
        "label": "Joy",
        "desc": "Bright, rhythmic, tonal — euphoric and uplifting",
        "ideal": {
            "spectral_centroid_mean": (2500, 4500),
            "spectral_rolloff_mean":  (4500, 7500),
            "spectral_flatness_mean": (0.02, 0.06),   # tonal / clear
            "spectral_flux_mean":     (0.04, 0.07),    # rhythmic energy
            "rms_level_db":           (-15, -10),
            "dynamic_range":          (5, 10),
        },
    },
    "calm": {
        # Low arousal, positive valence — warm, tonal, static, quiet
        # Research: low centroid, low flatness, very low flux, PLR > 14
        "group": "mood",
        "label": "Calm",
        "desc": "Warm, steady, clear — unwind and breathe",
        "ideal": {
            "spectral_centroid_mean": (800, 1800),
            "spectral_rolloff_mean":  (1500, 3800),
            "spectral_flatness_mean": (0.02, 0.06),   # tonal / stable
            "spectral_flux_mean":     (0.008, 0.025),  # gentle movement
            "rms_level_db":           (-22, -14),
            "dynamic_range":          (7, 15),
        },
    },
    "melancholy": {
        # Low arousal, negative valence — dark, tonal, intimate
        # Research: low centroid, low flatness, low flux
        "group": "mood",
        "label": "Melancholy",
        "desc": "Dark, slow, intimate — sit with the feeling",
        "ideal": {
            "spectral_centroid_mean": (600, 1600),
            "spectral_rolloff_mean":  (1200, 3500),
            "spectral_flatness_mean": (0.02, 0.05),   # very tonal
            "spectral_flux_mean":     (0.01, 0.03),    # slow, sparse
            "rms_level_db":           (-20, -13),       # intimate, not silent
            "dynamic_range":          (6, 14),
        },
    },
    "heroic": {
        # High arousal, positive valence — bold, mid-bright, wide, driving
        # Research: mid centroid, low flatness, mid flux, PLR 12-14
        "group": "mood",
        "label": "Heroic",
        "desc": "Bold, sweeping, tonal — brass and conviction",
        "ideal": {
            "spectral_centroid_mean": (2000, 3500),
            "spectral_rolloff_mean":  (4000, 6500),
            "spectral_flatness_mean": (0.02, 0.06),   # tonal / clean
            "spectral_flux_mean":     (0.03, 0.055),   # controlled momentum
            "rms_level_db":           (-14, -10),       # present, loud
            "dynamic_range":          (6, 12),
        },
    },
    "mysterious": {
        # Low arousal, ambiguous valence — dark, noisy, sparse
        # Research: low centroid, high flatness, low flux, PLR > 14
        "group": "mood",
        "label": "Mysterious",
        "desc": "Dark, textured, noisy — shadows and atmosphere",
        "ideal": {
            "spectral_centroid_mean": (600, 1800),
            "spectral_rolloff_mean":  (1000, 3800),
            "spectral_flatness_mean": (0.09, 0.20),   # p75+ — noisy / textured
            "spectral_flux_mean":     (0.01, 0.035),   # sparse movement
            "rms_level_db":           (-22, -14),       # quiet but present
            "dynamic_range":          (6, 15),
        },
    },

    # ═══════════════════════════════════════════════════════════════════
    # Support — therapeutic profiles from the research
    # ═══════════════════════════════════════════════════════════════════

    "stress_relief": {
        # SNS suppression — warm, predictable, breathing dynamics
        # Research: rolloff < 5 kHz, low flux, high PLR (> 13)
        "group": "support",
        "label": "Stress Relief",
        "desc": "Warm, predictable, spacious — let the nervous system settle",
        "ideal": {
            "spectral_centroid_mean": (1000, 2000),
            "spectral_rolloff_mean":  (1800, 4200),
            "spectral_flatness_mean": (0.03, 0.08),   # stable
            "spectral_flux_mean":     (0.008, 0.025),  # calm, predictable
            "rms_level_db":           (-20, -14),       # quiet
            "dynamic_range":          (7, 15),
        },
    },
    "recovery": {
        # Deep parasympathetic — filtered, ambient, near-silence
        # Research: low everything, PLR > 15, -24 to -18 LUFS
        "group": "support",
        "label": "Recovery",
        "desc": "Filtered, ambient, gentle — physiological restoration",
        "ideal": {
            "spectral_centroid_mean": (400, 1400),
            "spectral_rolloff_mean":  (700, 2500),
            "spectral_flatness_mean": (0.05, 0.12),   # organic / ambient
            "spectral_flux_mean":     (0.005, 0.02),   # near-static
            "rms_level_db":           (-30, -18),       # very quiet
            "dynamic_range":          (6, 15),
        },
    },
}


def _zone_fit(value, lo, hi):
    """How well a value fits an ideal range. 1.0 = inside, decays with Gaussian outside.

    Steepness: exp(-3 * dist²) — at 1 range-width outside, score = 0.050.
    A track must genuinely match the profile to score well.
    """
    if lo <= value <= hi:
        return 1.0
    width = max(hi - lo, 0.001)
    dist = (lo - value) / width if value < lo else (value - hi) / width
    return math.exp(-3.0 * dist * dist)


def classify_track(features):
    """Score a track against each activity zone. Returns {zone: score}.

    Uses geometric mean — a track must fit ALL parameters to score well.
    One bad miss tanks the overall score, unlike arithmetic mean which hides it.
    """
    scores = {}
    for zone_id, zone in ZONES.items():
        fit = []
        for feat, (lo, hi) in zone["ideal"].items():
            val = features.get(feat, 0)
            fit.append(_zone_fit(val, lo, hi))
        if fit:
            # Geometric mean: (f1 * f2 * ... * fn) ^ (1/n)
            product = 1.0
            for f in fit:
                product *= max(f, 1e-10)  # floor to avoid zero killing everything
            scores[zone_id] = round(product ** (1.0 / len(fit)), 4)
        else:
            scores[zone_id] = 0
    return scores


def get_zones(music_root):
    """Return zone summaries with track counts per zone. Uses precomputed scores."""
    conn = _connect(music_root)
    result = []
    for zone_id, zone in ZONES.items():
        col = f"zone_{zone_id}"
        row = conn.execute(f"SELECT COUNT(*) FROM tracks WHERE {col} >= 0.5").fetchone()
        count = row[0] if row else 0
        result.append({
            "id": zone_id,
            "group": zone["group"],
            "label": zone["label"],
            "desc": zone["desc"],
            "trackCount": count,
        })
    conn.close()
    return result


def generate_playlist(zone_id, music_root, limit=25):
    """Generate a smooth playlist for an activity zone.

    Selects tracks that fit the zone (precomputed scores), then orders them
    using nearest-neighbor traversal for smooth sonic transitions.
    """
    if zone_id not in ZONES:
        return []

    conn = _connect(music_root)
    col = f"zone_{zone_id}"

    # Fetch candidates sorted by zone score, over-select for ordering flexibility
    fetch_limit = limit * 2
    rows = conn.execute(
        f"SELECT * FROM tracks WHERE {col} >= 0.5 ORDER BY {col} DESC LIMIT ?",
        (fetch_limit,)
    ).fetchall()

    if not rows:
        conn.close()
        return []

    # Build candidate list
    candidates = []
    for row in rows:
        feats = {f: row[f] for f in _FEAT_COLS}
        candidates.append({
            "score": row[col],
            "key": row["key"],
            "artist": row["artist"],
            "album": row["album"],
            "title": row["title"],
            "file": row["file"],
            "features": feats,
        })

    conn.close()

    # Normalize features for distance computation (within this pool)
    ranges = {}
    for feat in FEATURE_ORDER:
        vals = [c["features"].get(feat, 0) for c in candidates]
        lo, hi = min(vals), max(vals)
        ranges[feat] = (lo, hi)

    def to_vec(features):
        return [
            (features.get(f, 0) - lo) / (hi - lo)
            if (hi := ranges[f][1]) > (lo := ranges[f][0]) else 0
            for f in FEATURE_ORDER
        ]

    vecs = [(to_vec(c["features"]), c) for c in candidates]

    # Diversity-aware nearest-neighbor chain
    ordered = [vecs[0]]
    remaining = list(vecs[1:])

    def _recent_context(n=3):
        artists, albums = set(), set()
        for _, data in ordered[-n:]:
            artists.add(data["artist"])
            albums.add(data["album"])
        return artists, albums

    while remaining and len(ordered) < limit:
        last_vec = ordered[-1][0]
        recent_artists, recent_albums = _recent_context()

        best_idx = 0
        best_score = -1
        for i, (vec, data) in enumerate(remaining):
            sim = _cosine(last_vec, vec)
            if data["artist"] in recent_artists:
                sim *= 0.3
            elif data["album"] in recent_albums:
                sim *= 0.5
            if sim > best_score:
                best_score = sim
                best_idx = i
        ordered.append(remaining.pop(best_idx))

    # Build result
    cover_cache = {}
    result = []
    for _, data in ordered:
        artist, album = data["artist"], data["album"]
        if (artist, album) not in cover_cache:
            cover_path = os.path.join(music_root, artist, album, "cover.jpg")
            cover_cache[(artist, album)] = (
                f"/music/{artist}/{album}/cover.jpg"
                if os.path.isfile(cover_path) else None
            )

        result.append({
            "key": data["key"],
            "artist": artist,
            "album": album,
            "title": data["title"],
            "file": data["file"],
            "cover": cover_cache[(artist, album)],
            "score": data["score"],
            "url": f"/music/{data['file']}",
        })

    return result


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

def find_similar(track_key, music_root, limit=10):
    """Return tracks most similar to the given one, ranked by cosine similarity."""
    conn = _connect(music_root)

    target_row = conn.execute("SELECT * FROM tracks WHERE key = ?", (track_key,)).fetchone()
    if not target_row:
        conn.close()
        return []

    target_feats = {f: target_row[f] for f in _FEAT_COLS}

    # Use cached normalization ranges
    ranges = _get_norm_ranges(conn)

    def to_vec(features):
        vec = []
        for f in FEATURE_ORDER:
            r = ranges.get(f, [0, 0])
            lo, hi = r[0], r[1]
            val = features.get(f, 0)
            vec.append((val - lo) / (hi - lo) if hi > lo else 0)
        return vec

    target_vec = to_vec(target_feats)

    # Fetch all other tracks — only the columns we need
    cols = ", ".join(["key", "artist", "album", "title", "file"] + list(_FEAT_COLS))
    rows = conn.execute(f"SELECT {cols} FROM tracks WHERE key != ?", (track_key,)).fetchall()
    conn.close()

    results = []
    for row in rows:
        feats = {f: row[f] for f in _FEAT_COLS}
        vec = to_vec(feats)
        score = _cosine(target_vec, vec)
        results.append({
            "key": row["key"],
            "artist": row["artist"],
            "album": row["album"],
            "title": row["title"],
            "file": row["file"],
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
# Migration: import existing JSON data
# ---------------------------------------------------------------------------

def migrate_from_json(music_root):
    """Legacy migration — no longer imports old JSON data.

    Old JSON features contain peak-to-trough dynamic_range values that are
    incompatible with the v4+ crest factor calculation. Re-analysis via
    'Analyze library' is the correct path.
    """
    # Just clean up old files if they exist
    for suffix in ("", ".bak"):
        path = os.path.join(music_root, f".audio_features.json{suffix}")
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <music_root>")
        print(f"       {sys.argv[0]} --similar <music_root> 'Artist::Album::Title'")
        print(f"       {sys.argv[0]} --migrate <music_root>")
        sys.exit(1)

    if sys.argv[1] == "--similar" and len(sys.argv) >= 4:
        root = sys.argv[2]
        key = sys.argv[3]
        results = find_similar(key, root)
        for r in results:
            print(f"  {r['score']:.3f}  {r['artist']} — {r['title']}")
    elif sys.argv[1] == "--migrate" and len(sys.argv) >= 3:
        root = sys.argv[2]
        count = migrate_from_json(root)
        print(f"Migrated {count} tracks from JSON to SQLite.")
    else:
        root = sys.argv[1]
        print(f"Analyzing library: {root}")
        analyze_library(root, on_progress=lambda d: print(f"  {d['message']}"))
        print("Done.")
