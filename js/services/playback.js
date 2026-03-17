/**
 * PlaybackController — owns all playback state and delegates to local Audio or cast.
 *
 * The single source of truth for: queue, current track, play/pause state,
 * seek position, volume. Components read from getStatus(), send controls
 * via play/pause/next/prev/seek/volume methods.
 *
 * Cast is a backend swap — same interface, different transport.
 */

import { castTrack, controlPlayback, fetchStatus } from './api.js';
import { recordPlay } from './stats.js';

class PlaybackController {
  constructor() {
    this._audio = new Audio();
    this._audio.preload = 'metadata';
    this._queue = [];
    this._queueIndex = -1;
    this._mode = 'local'; // 'local' or 'cast'
    this._selectedDevice = null;
    this._castBaseUrl = null;
    this._listeners = new Set();

    // Auto-advance on track end
    this._audio.addEventListener('ended', () => {
      if (this._queueIndex < this._queue.length - 1) {
        this._queueIndex++;
        this._playLocal();
      }
    });

    // Media Session
    this._setupMediaSession();
  }

  // ── Public API ──

  /**
   * Start playing a queue of tracks at the given index.
   * Track format: { file, title, artist, album, cover, url }
   * If url is missing, it's built from file.
   */
  play(tracks, index = 0) {
    this._queue = tracks.map(t => ({
      ...t,
      url: t.url || `/music/${t.file.split('/').map(s => encodeURIComponent(s)).join('/')}`,
    }));
    this._queueIndex = index;

    if (this._mode === 'cast' && this._selectedDevice) {
      this._castQueue(index).then(ok => {
        if (!ok) {
          this._mode = 'local';
          this._playLocal();
        }
      });
    } else {
      this._mode = 'local';
      this._playLocal();
    }
  }

  /**
   * Play tracks from an album (file names only, no url/title).
   * Builds full track objects from artist/album/cover + file list.
   */
  playAlbum({ artist, album, cover, tracks, index }) {
    const queue = tracks.map(t => {
      const file = typeof t === 'string' ? t : t.file;
      const match = file.match(/^\d+\s*-\s*(.+)\.\w+$/i);
      const title = match ? match[1] : file;
      return {
        url: `/music/${encodeURIComponent(artist)}/${encodeURIComponent(album)}/${encodeURIComponent(file)}`,
        file: `${artist}/${album}/${file}`,
        title, artist, album,
        cover: cover || null,
      };
    });
    this.play(queue, index);
  }

  toggle() {
    if (this._mode === 'cast') {
      controlPlayback('toggle');
    } else {
      this._audio.paused ? this._audio.play().catch(() => {}) : this._audio.pause();
    }
  }

  pause() {
    if (this._mode === 'cast') controlPlayback('pause');
    else this._audio.pause();
  }

  resume() {
    if (this._mode === 'cast') controlPlayback('play');
    else this._audio.play().catch(() => {});
  }

  next() {
    if (this._mode === 'cast') {
      controlPlayback('next');
    } else if (this._queueIndex < this._queue.length - 1) {
      this._queueIndex++;
      this._playLocal();
    }
  }

  prev() {
    if (this._mode === 'cast') {
      controlPlayback('prev');
    } else {
      if (this._audio.currentTime > 3) {
        this._audio.currentTime = 0;
      } else if (this._queueIndex > 0) {
        this._queueIndex--;
        this._playLocal();
      }
    }
  }

  seek(time) {
    if (this._mode === 'cast') controlPlayback('seek', time);
    else if (time != null) this._audio.currentTime = time;
  }

  volume(level) {
    if (this._mode === 'cast') controlPlayback('volume', level);
    else if (level != null) this._audio.volume = level;
  }

  // ── Cast device management ──

  async selectDevice(device) {
    if (!device || device.id === 'local') {
      if (this._mode === 'cast') {
        await controlPlayback('stop').catch(() => {});
      }
      this._selectedDevice = null;
      this._mode = 'local';
      if (this._queueIndex >= 0 && this._queue.length) this._playLocal();
      return;
    }

    // Switching to cast — stop local audio first
    this._audio.pause();
    this._audio.src = '';

    this._selectedDevice = device;
    this._mode = 'cast';
    await this._fetchServerIp();

    if (this._queueIndex >= 0 && this._queue.length) {
      const ok = await this._castQueue(this._queueIndex);
      if (!ok) {
        this._mode = 'local';
        this._playLocal();
      }
    }
  }

  get selectedDevice() { return this._selectedDevice; }
  get mode() { return this._mode; }
  get currentTrack() { return this._queue[this._queueIndex] || null; }
  get queue() { return this._queue; }
  get queueIndex() { return this._queueIndex; }

  // ── Status (unified for now-playing bar) ──

  async getStatus() {
    if (this._mode === 'cast' && this._selectedDevice) {
      try {
        const status = await fetchStatus();
        const track = this._queue[this._queueIndex];
        if (status.state === 'idle' && track) {
          return {
            state: 'paused',
            currentTime: 0,
            duration: 0,
            volume: status.volume != null ? status.volume : 1,
            title: track.title,
            artist: track.artist,
            album: track.album,
            cover: track.cover,
            queueIndex: this._queueIndex,
            queueLength: this._queue.length,
            device: this._selectedDevice.name,
          };
        }
        return status;
      } catch {
        return { state: 'idle' };
      }
    }

    const track = this._queue[this._queueIndex];
    if (track && this._audio.src) {
      this._syncMediaSessionPosition();
      const status = {
        state: this._audio.paused ? 'paused' : 'playing',
        currentTime: this._audio.currentTime || 0,
        duration: this._audio.duration || 0,
        volume: this._audio.volume,
        title: track.title,
        artist: track.artist,
        album: track.album,
        cover: track.cover,
        queueIndex: this._queueIndex,
        queueLength: this._queue.length,
        device: null,
      };
      this._pushState(status);
      return status;
    }

    this._pushState({ state: 'idle' });
    return { state: 'idle' };
  }

  /** Push local playback state to server for remote. */
  _pushState(status) {
    fetch('/api/playback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(status),
    }).catch(() => {});
  }

  /** Connect SSE stream for instant remote commands. */
  connectRemoteCommands() {
    if (this._remoteSse) return;
    this._remoteSse = new EventSource('/api/playback/commands');
    this._remoteSse.addEventListener('message', (e) => {
      try {
        const cmd = JSON.parse(e.data);
        switch (cmd.action) {
          case 'toggle': this.toggle(); break;
          case 'play':   this.resume(); break;
          case 'pause':  this.pause(); break;
          case 'next':   this.next(); break;
          case 'prev':   this.prev(); break;
          case 'seek':   this.seek(cmd.value); break;
          case 'volume': this.volume(cmd.value); break;
        }
      } catch {}
    });
    this._remoteSse.addEventListener('error', () => {
      // Reconnect after a delay
      this._remoteSse.close();
      this._remoteSse = null;
      setTimeout(() => this.connectRemoteCommands(), 2000);
    });
  }

  // ── Private: local playback ──

  _playLocal() {
    const track = this._queue[this._queueIndex];
    if (!track) return;
    this._audio.pause();
    this._audio.src = track.url;
    this._audio.play().catch(() => {});
    this._updateMediaSession(track);
    recordPlay(track);
  }

  // ── Private: cast ──

  _getCastBaseUrl() {
    if (this._castBaseUrl) return this._castBaseUrl;
    const saved = localStorage.getItem('musicast-lan-ip');
    if (saved) {
      this._castBaseUrl = `http://${saved}:${location.port || 8000}`;
      return this._castBaseUrl;
    }
    return location.origin;
  }

  async _fetchServerIp() {
    try {
      const r = await fetch('/api/config');
      const cfg = await r.json();
      const ip = cfg.lanIp;

      if (ip && !ip.startsWith('100.115.') && ip !== '127.0.0.1') {
        localStorage.setItem('musicast-lan-ip', ip);
        this._castBaseUrl = `http://${ip}:${cfg.port || 8000}`;
      } else if (!localStorage.getItem('musicast-lan-ip')) {
        const manual = prompt(
          'Chromecast needs your WiFi IP to stream audio.\n' +
          'Find it in: ChromeOS Settings > Network > WiFi\n\n' +
          'Enter WiFi IP (e.g. 192.168.86.32):'
        );
        if (manual && manual.trim()) {
          localStorage.setItem('musicast-lan-ip', manual.trim());
          this._castBaseUrl = `http://${manual.trim()}:${cfg.port || 8000}`;
        }
      }
    } catch { /* silent */ }
  }

  async _castQueue(index) {
    if (!this._selectedDevice) return false;
    try {
      const baseUrl = this._getCastBaseUrl();
      const result = await castTrack(
        this._selectedDevice.id, this._queue[index], this._queue, index, baseUrl
      );
      if (result.error) {
        console.error('Cast error:', result.error);
        return false;
      }
      recordPlay(this._queue[index]);
      return true;
    } catch (e) {
      console.error('Cast failed:', e);
      return false;
    }
  }

  /** Reset cast base URL (called when user changes IP in settings). */
  resetCastUrl() {
    this._castBaseUrl = null;
  }

  // ── Private: Media Session API ──

  _setupMediaSession() {
    if (!('mediaSession' in navigator)) return;
    const ms = navigator.mediaSession;
    ms.setActionHandler('play', () => this.resume());
    ms.setActionHandler('pause', () => this.pause());
    ms.setActionHandler('previoustrack', () => this.prev());
    ms.setActionHandler('nexttrack', () => this.next());
    ms.setActionHandler('seekto', (e) => this.seek(e.seekTime));
  }

  _updateMediaSession(track) {
    if (!('mediaSession' in navigator) || !track) return;
    const artwork = [];
    if (track.cover) {
      const coverUrl = new URL(track.cover, location.origin).href;
      artwork.push({ src: coverUrl, sizes: '512x512', type: 'image/jpeg' });
    }
    navigator.mediaSession.metadata = new MediaMetadata({
      title: track.title,
      artist: track.artist,
      album: track.album,
      artwork,
    });
  }

  _syncMediaSessionPosition() {
    if (!('mediaSession' in navigator) || !navigator.mediaSession.setPositionState) return;
    if (!this._audio.duration || !isFinite(this._audio.duration)) return;
    navigator.mediaSession.setPositionState({
      duration: this._audio.duration,
      playbackRate: this._audio.playbackRate,
      position: Math.min(this._audio.currentTime, this._audio.duration),
    });
  }
}

// Singleton
export const playback = new PlaybackController();
