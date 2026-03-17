"""Database management — SQLite schema, connection, track storage.

Tracks table stores objective audio features + classifier outputs (cls_json).
Schema v11: clean break from v10 — new feature set, full re-analysis required.
"""

import sqlite3
import json
import os

DB_FILE = ".audio_features.db"
SCHEMA_VERSION = 11

# Numeric feature columns in tracks table (v0.6 — 25 scalars)
FEATURE_COLS = [
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


def _db_path(music_root):
    """DB lives locally (not on 9p mount — WAL locking fails there)."""
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
    """Create or migrate tables to current schema version.

    v11 is a clean break — DROP and recreate tracks table.
    """
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= SCHEMA_VERSION:
        return

    feat_sql = ", ".join(f"{c} REAL DEFAULT 0" for c in FEATURE_COLS)

    # Clean break: drop old tracks table if upgrading
    conn.executescript(f"""
        DROP TABLE IF EXISTS tracks;

        CREATE TABLE tracks (
            track_id TEXT PRIMARY KEY,
            artist TEXT NOT NULL,
            album TEXT NOT NULL,
            title TEXT NOT NULL,
            file TEXT NOT NULL,
            extracted_at TEXT NOT NULL DEFAULT (datetime('now')),
            {feat_sql},
            mfcc_mean_json TEXT DEFAULT '[]',
            chroma_mean_json TEXT DEFAULT '[]',
            tonnetz_mean_json TEXT DEFAULT '[]',
            cls_json TEXT DEFAULT '{{}}'
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

    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    conn.commit()


def insert_track(conn, track_id, artist, album, title, file, features, classifications=None):
    """Insert a track with extracted features and optional classifier outputs."""
    cols = ["track_id", "artist", "album", "title", "file"]
    vals = [track_id, artist, album, title, file]

    for c in FEATURE_COLS:
        cols.append(c)
        vals.append(features.get(c, 0.0))

    cols.append("mfcc_mean_json")
    vals.append(json.dumps(features.get("mfcc_mean", [])))
    cols.append("chroma_mean_json")
    vals.append(json.dumps(features.get("chroma_mean", [])))
    cols.append("tonnetz_mean_json")
    vals.append(json.dumps(features.get("tonnetz_mean", [])))

    cols.append("cls_json")
    vals.append(json.dumps(classifications or {}))

    placeholders = ", ".join("?" * len(cols))
    col_names = ", ".join(cols)
    conn.execute(
        f"INSERT OR REPLACE INTO tracks ({col_names}) VALUES ({placeholders})", vals
    )
    conn.commit()


def get_norm_ranges(conn):
    """Compute feature min/max ranges on demand from raw features.

    Used by similarity/transitions for z-score normalization of vectors.
    """
    row = conn.execute(
        "SELECT value FROM meta WHERE key = ?", ("norm_ranges",)
    ).fetchone()
    if row:
        return json.loads(row[0])

    # Compute and cache
    ranges = {}
    for feat in FEATURE_COLS:
        r = conn.execute(f"SELECT MIN({feat}), MAX({feat}) FROM tracks").fetchone()
        if r and r[0] is not None:
            ranges[feat] = [r[0], r[1]]
        else:
            ranges[feat] = [0.0, 0.0]
    conn.execute(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
        ("norm_ranges", json.dumps(ranges)),
    )
    conn.commit()
    return ranges


def update_norm_ranges(conn):
    """Refresh cached min/max ranges after analysis."""
    # Delete cached value so get_norm_ranges recomputes
    conn.execute("DELETE FROM meta WHERE key = ?", ("norm_ranges",))
    conn.commit()
    return get_norm_ranges(conn)
