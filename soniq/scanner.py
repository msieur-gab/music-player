"""Library scanning — find audio files, extract features, classify, populate DB.

Pipeline per track:
  1. Check for v0.6 Soniq tag with cls section → fast path (insert directly)
  2. Otherwise: extract features → classify → insert + write tag back

Extraction runs in ProcessPool (CPU-bound librosa).
Classification runs in main process (~3ms per track, pure Python).
"""

import os
import re
from concurrent.futures import ProcessPoolExecutor, as_completed

from .db import _connect, insert_track, update_norm_ranges
from .extractor import extract_track_features
from .tags import read_tag, write_tag, CURRENT_VERSION
from .classifiers import predict_all


def analyze_library(music_root, on_progress=None, workers=4):
    """Analyze audio files: read from tags when available, extract with librosa otherwise."""
    conn = _connect(music_root)
    existing = {row[0] for row in conn.execute("SELECT track_id FROM tracks").fetchall()}

    audio_files = _find_audio_files(music_root)
    total = len(audio_files)
    skipped = 0
    from_tags = 0

    work = []
    for path in audio_files:
        artist, album, title = _info_from_path(path, music_root)
        track_id = f"{artist}::{album}::{title}"
        if track_id in existing:
            skipped += 1
            continue

        feats, cls, version = read_tag(path)
        if feats and version == CURRENT_VERSION and cls:
            # Fast path: v0.6 tag with classifier outputs
            insert_track(
                conn, track_id, artist, album, title,
                os.path.relpath(path, music_root), feats, cls,
            )
            from_tags += 1
        else:
            work.append((path, artist, album, title, track_id))

    if on_progress:
        on_progress({
            "message": f"Loaded {from_tags} from tags, extracting {len(work)} tracks "
                       f"({skipped} in DB, {workers} workers)",
            "track": 0, "total": total, "status": "analyzing",
        })

    done = 0
    analyzed = 0
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_track_features, item[0]): item for item in work}
        for future in as_completed(futures):
            done += 1
            path, artist, album, title, track_id = futures[future]
            try:
                feats = future.result()
                if feats:
                    # Classification in main process (~3ms)
                    cls = predict_all(feats)
                    insert_track(
                        conn, track_id, artist, album, title,
                        os.path.relpath(path, music_root), feats, cls,
                    )
                    write_tag(path, feats, cls)
                    analyzed += 1
            except Exception as e:
                print(f"  Error extracting {title}: {e}")

            if on_progress:
                on_progress({
                    "message": f"Extracted {done}/{len(work)}: {title}",
                    "track": skipped + from_tags + done, "total": total,
                    "status": "analyzing",
                })

    update_norm_ranges(conn)
    conn.close()

    if on_progress:
        on_progress({
            "message": f"Done -- {from_tags} from tags, {analyzed} extracted ({skipped} cached)",
            "analyzed": analyzed, "from_tags": from_tags,
            "skipped": skipped, "total": total,
            "status": "complete",
        })


def migrate_from_json(music_root):
    """Legacy cleanup — remove old JSON feature files."""
    for suffix in ("", ".bak"):
        path = os.path.join(music_root, f".audio_features.json{suffix}")
        if os.path.isfile(path):
            try:
                os.remove(path)
            except OSError:
                pass
    return 0


def _find_audio_files(music_root):
    """Walk the music directory and return sorted list of audio file paths."""
    audio = []
    for root, _, files in os.walk(music_root):
        for f in sorted(files):
            if f.lower().endswith((".m4a", ".mp3")) and not f.startswith("_temp_"):
                audio.append(os.path.join(root, f))
    return audio


def _info_from_path(filepath, music_root):
    """Derive artist/album/title from path: root/Artist/Album/01 - Title.{m4a,mp3}"""
    rel = os.path.relpath(filepath, music_root)
    parts = rel.replace("\\", "/").split("/")
    artist = parts[0] if len(parts) >= 3 else "Unknown"
    album = parts[1] if len(parts) >= 3 else (parts[0] if len(parts) >= 2 else "Unknown")
    fname = os.path.splitext(parts[-1])[0]
    m = re.match(r"^\d+\s*[-\u2013]\s*(.+)$", fname)
    title = m.group(1).strip() if m else fname
    return artist, album, title
