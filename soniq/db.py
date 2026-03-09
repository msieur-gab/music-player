"""Database management — SQLite schema, connection, track storage.

Tracks table stores objective audio features only. Classification scores
are computed on demand by the scoring module -- never stored.
"""

import sqlite3
import json
import os

DB_FILE = ".audio_features.db"
SCHEMA_VERSION = 10

# Numeric feature columns in tracks table
FEATURE_COLS = [
    "duration", "tempo", "key", "mode",
    "rms_mean", "rms_max", "rms_variance", "dynamic_range",
    "centroid_mean", "flatness_mean", "spectral_flux",
    "onset_strength", "beat_strength", "vocal_proxy", "zcr_mean",
]

# Subset used for context profile matching (normalized 0-1 via min-max)
PROFILE_FEATURES = [
    "tempo", "rms_mean", "dynamic_range", "centroid_mean",
    "flatness_mean", "spectral_flux", "onset_strength",
    "beat_strength", "rms_variance", "vocal_proxy",
]


def _db_path(music_root):
    """DB lives locally (not on 9p mount -- WAL locking fails there)."""
    local_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".data")
    os.makedirs(local_dir, exist_ok=True)
    return os.path.join(local_dir, DB_FILE)


def _connect(music_root):
    """Open the features database, creating schema if needed."""
    path = _db_path(music_root)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn):
    """Create or migrate tables to current schema version."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return

    feat_sql = ", ".join(f"{c} REAL DEFAULT 0" for c in FEATURE_COLS)

    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS tracks (
            track_id TEXT PRIMARY KEY,
            artist TEXT NOT NULL,
            album TEXT NOT NULL,
            title TEXT NOT NULL,
            file TEXT NOT NULL,
            extracted_at TEXT NOT NULL DEFAULT (datetime('now')),
            {feat_sql},
            mfcc_mean_json TEXT DEFAULT '[]',
            mfcc_std_json TEXT DEFAULT '[]',
            contrast_mean_json TEXT DEFAULT '[]',
            chroma_mean_json TEXT DEFAULT '[]',
            tonnetz_mean_json TEXT DEFAULT '[]'
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

        CREATE INDEX IF NOT EXISTS idx_artist ON tracks(artist);
        CREATE INDEX IF NOT EXISTS idx_album ON tracks(artist, album);
    """)

    # Migrate: add columns that may be missing from older schemas
    existing = {row[1] for row in conn.execute("PRAGMA table_info(tracks)").fetchall()}
    for col in ("chroma_mean_json", "tonnetz_mean_json"):
        if col not in existing:
            conn.execute(f"ALTER TABLE tracks ADD COLUMN {col} TEXT DEFAULT '[]'")

    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def insert_track(conn, track_id, artist, album, title, file, features):
    """Insert a track with extracted features."""
    cols = ["track_id", "artist", "album", "title", "file"]
    vals = [track_id, artist, album, title, file]

    for c in FEATURE_COLS:
        cols.append(c)
        vals.append(features.get(c, 0.0))

    cols.append("mfcc_mean_json")
    vals.append(json.dumps(features.get("mfcc_mean", [])))
    cols.append("mfcc_std_json")
    vals.append(json.dumps(features.get("mfcc_std", [])))
    cols.append("contrast_mean_json")
    vals.append(json.dumps(features.get("contrast_mean", [])))
    cols.append("chroma_mean_json")
    vals.append(json.dumps(features.get("chroma_mean", [])))
    cols.append("tonnetz_mean_json")
    vals.append(json.dumps(features.get("tonnetz_mean", [])))

    placeholders = ", ".join("?" * len(cols))
    col_names = ", ".join(cols)
    conn.execute(
        f"INSERT OR REPLACE INTO tracks ({col_names}) VALUES ({placeholders})", vals
    )
    conn.commit()


def update_norm_ranges(conn):
    """Cache min/max per profile feature for 0-1 normalization."""
    ranges = {}
    for feat in PROFILE_FEATURES:
        row = conn.execute(f"SELECT MIN({feat}), MAX({feat}) FROM tracks").fetchone()
        if row and row[0] is not None:
            ranges[feat] = [row[0], row[1]]
        else:
            ranges[feat] = [0.0, 0.0]
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        ("norm_ranges", json.dumps(ranges)),
    )
    conn.commit()


def get_norm_ranges(conn):
    """Load cached normalization ranges."""
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", ("norm_ranges",)
    ).fetchone()
    if row:
        return json.loads(row[0])
    update_norm_ranges(conn)
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", ("norm_ranges",)
    ).fetchone()
    return json.loads(row[0]) if row else {}
