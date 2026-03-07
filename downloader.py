#!/usr/bin/env python3
"""
YouTube Music playlist downloader.
Self-bootstrapping: installs yt-dlp and ffmpeg if missing.
Downloads as 192kbps CBR MP3 with clean ID3 tags + cover art.
"""

import subprocess
import sys
import shutil
import os
import json
import re
import struct
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

MUSIC_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "music")


# ---------------------------------------------------------------------------
# Dependency bootstrap
# ---------------------------------------------------------------------------

VENV_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv")


def _ensure_venv():
    """Create a project-local venv if we're not already running inside it."""
    venv_python = os.path.join(VENV_DIR, "bin", "python3")

    # Already inside the venv
    if sys.prefix != sys.base_prefix:
        return

    if not os.path.isfile(venv_python):
        print("[bootstrap] Creating virtual environment...")
        # Make sure python3-venv is available
        if shutil.which("apt-get"):
            subprocess.run(
                ["sudo", "apt-get", "install", "-y", "-qq", "python3-venv"],
                check=False
            )
        subprocess.check_call([sys.executable, "-m", "venv", VENV_DIR])

    # Re-exec the current script inside the venv
    print("[bootstrap] Switching to venv...")
    os.execv(venv_python, [venv_python] + sys.argv)


def _pip_install(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", package])


def _ensure_yt_dlp():
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        print("[bootstrap] Installing yt-dlp...")
        _pip_install("yt-dlp")


def _ensure_ffmpeg():
    if shutil.which("ffmpeg"):
        return
    print("[bootstrap] ffmpeg not found, attempting install...")
    if shutil.which("apt-get"):
        subprocess.run(["sudo", "apt-get", "update", "-qq"], check=False)
        subprocess.run(["sudo", "apt-get", "install", "-y", "-qq", "ffmpeg"], check=True)
    elif shutil.which("pacman"):
        subprocess.run(["sudo", "pacman", "-S", "--noconfirm", "ffmpeg"], check=True)
    else:
        url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        local_bin = os.path.expanduser("~/.local/bin")
        os.makedirs(local_bin, exist_ok=True)
        archive = "/tmp/ffmpeg-static.tar.xz"
        print(f"[bootstrap] Downloading static ffmpeg...")
        urllib.request.urlretrieve(url, archive)
        subprocess.run(
            f"tar -xf {archive} -C /tmp && cp /tmp/ffmpeg-*-static/ffmpeg /tmp/ffmpeg-*-static/ffprobe {local_bin}/",
            shell=True, check=True
        )
        os.environ["PATH"] = local_bin + ":" + os.environ["PATH"]
    if not shutil.which("ffmpeg"):
        raise RuntimeError("Could not install ffmpeg. Please install it manually.")


def _ensure_mutagen():
    try:
        import mutagen  # noqa: F401
    except ImportError:
        print("[bootstrap] Installing mutagen...")
        _pip_install("mutagen")



def bootstrap():
    _ensure_venv()  # creates venv + re-execs into it if needed
    _ensure_yt_dlp()
    _ensure_ffmpeg()
    _ensure_mutagen()


# ---------------------------------------------------------------------------
# Sanitise helpers
# ---------------------------------------------------------------------------

def _sanitise(name):
    """Filesystem-safe name: remove/replace problematic characters."""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.strip('. ')
    return name


# ---------------------------------------------------------------------------
# Tag writer
# ---------------------------------------------------------------------------

def _write_tags(filepath, meta):
    """Write clean ID3v2.4 tags with embedded cover art."""
    from mutagen.mp3 import MP3
    from mutagen.id3 import (
        ID3, TIT2, TPE1, TPE2, TALB, TRCK, TCON, TDRC, APIC, ID3NoHeaderError
    )

    try:
        audio = MP3(filepath)
    except Exception:
        return

    # Start fresh – remove existing tags and write clean ones
    try:
        audio.delete()
        audio.save()
    except Exception:
        pass

    try:
        tags = ID3(filepath)
    except ID3NoHeaderError:
        tags = ID3()

    tags.update_to_v24()

    if meta.get("title"):
        tags.add(TIT2(encoding=3, text=[meta["title"]]))
    if meta.get("artist"):
        tags.add(TPE1(encoding=3, text=[meta["artist"]]))
    if meta.get("album_artist"):
        tags.add(TPE2(encoding=3, text=[meta["album_artist"]]))
    if meta.get("album"):
        tags.add(TALB(encoding=3, text=[meta["album"]]))
    if meta.get("track_number"):
        total = meta.get("track_total", "")
        trck = f"{meta['track_number']}/{total}" if total else str(meta["track_number"])
        tags.add(TRCK(encoding=3, text=[trck]))
    if meta.get("genre"):
        tags.add(TCON(encoding=3, text=[meta["genre"]]))
    if meta.get("release_year"):
        tags.add(TDRC(encoding=3, text=[str(meta["release_year"])]))

    # Embed cover art
    cover_path = meta.get("cover_path")
    if cover_path and os.path.isfile(cover_path):
        with open(cover_path, "rb") as f:
            cover_data = f.read()
        mime = "image/jpeg" if cover_path.endswith(".jpg") else "image/png"
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Front Cover", data=cover_data))

    tags.save(filepath, v2_version=4)


# ---------------------------------------------------------------------------
# Core download
# ---------------------------------------------------------------------------

def download_playlist(url, music_root=None, on_progress=None):
    """
    Download a YouTube Music playlist.

    Args:
        url: YouTube Music playlist URL
        music_root: destination root folder (default: ./music)
        on_progress: callback(dict) for progress updates

    Returns:
        dict with artist, album, folder path, and list of tracks
    """
    import yt_dlp

    music_root = music_root or MUSIC_ROOT

    def _notify(msg, **extra):
        info = {"message": msg, **extra}
        if on_progress:
            on_progress(info)
        else:
            print(f"[downloader] {msg}")

    # ---- Step 1: Extract playlist metadata ----
    _notify("Extracting playlist info...")

    extract_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(extract_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if not info:
        raise ValueError("Could not extract playlist info")

    entries = info.get("entries", [])
    if not entries:
        raise ValueError("Playlist is empty or unavailable")

    # Resolve album/artist — prefer entry-level metadata (more reliable)
    first = entries[0] or {}
    album = (
        first.get("album")
        or info.get("album")
        or re.sub(r'^Album\s*-\s*', '', info.get("title", ""), flags=re.IGNORECASE)
        or "Unknown Album"
    )
    artist = (
        first.get("artist")
        or info.get("artist")
        or first.get("uploader")
        or info.get("uploader")
        or first.get("channel")
        or "Unknown Artist"
    )
    # Clean up "- Topic" suffix YouTube adds
    artist = re.sub(r'\s*-\s*Topic$', '', artist)

    genre = first.get("genre", "")
    release_year = (
        first.get("release_year")
        or info.get("release_year")
        or (first.get("upload_date", "")[:4] if first.get("upload_date") else "")
    )

    safe_artist = _sanitise(artist)
    safe_album = _sanitise(album)
    album_dir = os.path.join(music_root, safe_artist, safe_album)
    os.makedirs(album_dir, exist_ok=True)

    total = len(entries)
    _notify(f"Found {total} tracks: {artist} - {album}", artist=artist, album=album, total=total)

    # ---- Step 2: Download cover art ----
    cover_path = None
    # Collect candidate thumbnail URLs: playlist first (square album art), then first track
    thumb_candidates = []
    for source in [info, first]:
        for t in reversed(source.get("thumbnails", [])):
            url_t = t.get("url")
            if url_t:
                thumb_candidates.append(url_t)

    cover_dest = os.path.join(album_dir, "cover.jpg")
    for thumb_url in thumb_candidates:
        try:
            req = urllib.request.Request(thumb_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                img_data = resp.read()

            if thumb_url.endswith(".webp") or b'WEBP' in img_data[:16]:
                webp_path = cover_dest + ".webp"
                with open(webp_path, "wb") as f:
                    f.write(img_data)
                subprocess.run(
                    ["ffmpeg", "-y", "-i", webp_path, cover_dest],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True
                )
                os.remove(webp_path)
            else:
                with open(cover_dest, "wb") as f:
                    f.write(img_data)

            cover_path = cover_dest
            _notify("Cover art downloaded")
            break
        except Exception:
            continue

    if not cover_path:
        _notify("Cover art: no usable thumbnail found")

    # ---- Step 3: Download tracks in parallel ----
    tracks_result = {}  # idx → filename

    def _download_track(idx, entry):
        track_num = str(idx).zfill(2)
        track_title = entry.get("title", f"Track {idx}")
        track_title = re.sub(r'\s*\(Official Audio\)', '', track_title, flags=re.IGNORECASE)
        track_title = re.sub(r'\s*\(Official Video\)', '', track_title, flags=re.IGNORECASE)
        track_title = re.sub(r'\s*\[Official Audio\]', '', track_title, flags=re.IGNORECASE)
        track_title = re.sub(r'\s*\[Official Video\]', '', track_title, flags=re.IGNORECASE)

        safe_title = _sanitise(track_title)
        filename = f"{track_num} - {safe_title}.mp3"
        filepath = os.path.join(album_dir, filename)

        if os.path.isfile(filepath):
            _notify(f"Skipping {track_num}/{total}: {track_title} (exists)",
                    track=idx, total=total, status="skipped")
            return idx, filename

        _notify(f"Downloading {track_num}/{total}: {track_title}",
                track=idx, total=total, status="downloading")

        track_url = entry.get("webpage_url") or entry.get("url") or entry.get("id")
        if not track_url:
            _notify(f"Skipping {track_num}: no URL found", track=idx, status="error")
            return idx, None

        if not track_url.startswith("http"):
            track_url = f"https://www.youtube.com/watch?v={track_url}"

        temp_path = os.path.join(album_dir, f"_temp_{track_num}")

        dl_opts = {
            "format": "bestaudio/best",
            "outtmpl": temp_path + ".%(ext)s",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "postprocessor_args": ["-ar", "44100", "-ac", "2", "-b:a", "192k", "-cbr", "true"],
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        try:
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                ydl.download([track_url])

            temp_mp3 = temp_path + ".mp3"
            if os.path.isfile(temp_mp3):
                os.rename(temp_mp3, filepath)
            else:
                for f in os.listdir(album_dir):
                    if f.startswith(f"_temp_{track_num}") and f.endswith(".mp3"):
                        os.rename(os.path.join(album_dir, f), filepath)
                        break

            if os.path.isfile(filepath):
                track_artist = entry.get("artist") or artist
                track_artist = re.sub(r'\s*-\s*Topic$', '', track_artist)

                _write_tags(filepath, {
                    "title": track_title,
                    "artist": track_artist,
                    "album_artist": artist,
                    "album": album,
                    "track_number": idx,
                    "track_total": total,
                    "genre": entry.get("genre") or genre,
                    "release_year": release_year,
                    "cover_path": cover_path,
                })
                _notify(f"Done {track_num}/{total}: {track_title}",
                        track=idx, total=total, status="done")
                return idx, filename
            else:
                _notify(f"Failed {track_num}: file not found after download",
                        track=idx, status="error")
                return idx, None

        except Exception as e:
            _notify(f"Error {track_num}: {e}", track=idx, status="error")
            for f in os.listdir(album_dir):
                if f.startswith(f"_temp_{track_num}"):
                    os.remove(os.path.join(album_dir, f))
            return idx, None

    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}
        for idx, entry in enumerate(entries, 1):
            if entry is None:
                continue
            futures[pool.submit(_download_track, idx, entry)] = idx

        for future in as_completed(futures):
            idx, filename = future.result()
            if filename:
                tracks_result[idx] = filename

    # Collect tracks in order
    tracks = [tracks_result[i] for i in sorted(tracks_result)]

    # Keep cover.jpg in the album folder for the player UI

    result = {
        "artist": artist,
        "album": album,
        "folder": album_dir,
        "tracks": tracks,
        "total": total,
        "downloaded": len(tracks),
    }
    _notify(f"Complete: {len(tracks)}/{total} tracks downloaded", **result)
    return result


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <youtube-music-playlist-url>")
        sys.exit(1)

    bootstrap()
    result = download_playlist(sys.argv[1])
    print(json.dumps(result, indent=2))
