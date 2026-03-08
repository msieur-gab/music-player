import { fetchLibrary, fetchDevices, fetchStatus, castTrack, controlPlayback } from '../services/api.js';
import { recordPlay } from '../services/stats.js';
import './nav-rail.js';
import './home-view.js';
import './album-grid.js';
import './album-detail.js';
import './now-playing.js';
import './device-picker.js';
import './download-panel.js';
import './settings-panel.js';

const tpl = document.createElement('template');
tpl.innerHTML = `
<style>
/* ── Shell: 3-column grid — rail | feed | detail (slides in) ── */
:host {
  display: grid;
  height: 100dvh;
  overflow: clip;
  grid-template-columns: var(--rail-w) 1fr 0px;
  grid-template-rows: 1fr;
  grid-template-areas: "rail feed detail";
  background: var(--bg);
  transition: grid-template-columns var(--detail-slide);
}
:host([detail-open]) {
  grid-template-columns: var(--rail-w) 1fr var(--detail-w);
}

/* ── Grid placement ── */
nav-rail          { grid-area: rail; }
home-view         { grid-area: feed; display: none; min-height: 0; }
home-view[active] { display: block; }
.library          { grid-area: feed; display: none; min-height: 0; }
.library[active]  { display: flex; flex-direction: column; }

/* ── Detail panel (slides in from right like Loomr reader) ── */
album-detail {
  grid-area: detail;
  overflow-y: auto;
  overflow-x: hidden;
  min-width: 0;
  min-height: 0;
  border-left: 1px solid var(--border);
  box-shadow: -4px 0 16px rgba(0,0,0,0.06);
  background: var(--bg);
  padding-bottom: 120px;
}

/* ── Library internals ── */
.lib-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.tabs { display: flex; gap: 2px; }
.tab {
  padding: 6px 12px;
  border: none;
  border-radius: var(--radius);
  background: transparent;
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition);
}
.tab:hover { color: var(--text); background: var(--bg-hover); }
.tab.active { color: var(--accent); background: var(--accent-light); }

.spacer { flex: 1; }

.search {
  width: 240px;
  padding: 7px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  outline: none;
  transition: border-color var(--transition);
}
.search:focus { border-color: var(--accent); }

.lib-content {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding-bottom: 120px;
}
</style>

<nav-rail id="rail"></nav-rail>

<home-view id="home" active></home-view>

<div class="library" id="library">
  <div class="lib-header">
    <div class="tabs" id="tabs">
      <button class="tab active" data-view="artists">Artists</button>
      <button class="tab" data-view="albums">Albums</button>
      <button class="tab" data-view="genres">Genres</button>
    </div>
    <span class="spacer"></span>
    <input class="search" id="search" type="search" placeholder="Search..." autocomplete="off">
  </div>
  <div class="lib-content">
    <album-grid id="grid"></album-grid>
  </div>
</div>

<album-detail id="detail"></album-detail>

<now-playing id="player"></now-playing>
<download-panel id="downloader"></download-panel>
<device-picker id="devices"></device-picker>
<settings-panel id="settings"></settings-panel>
`;

class MusicApp extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
    this._albums = [];
    this._selectedDevice = null;
    this._pollId = null;
    this._view = 'home';

    // Local playback
    this._audio = new Audio();
    this._audio.preload = 'metadata';
    this._queue = [];
    this._queueIndex = -1;
    this._mode = 'local'; // 'local' or 'cast'
  }

  connectedCallback() {
    const $ = id => this.shadowRoot.getElementById(id);

    // ── Local audio: auto-advance ──
    this._audio.addEventListener('ended', () => {
      if (this._queueIndex < this._queue.length - 1) {
        this._queueIndex++;
        this._playLocal(); // also updates media session metadata
      }
    });

    // ── Rail navigation ──
    $('rail').addEventListener('rail-navigate', (e) => {
      this._setView(e.detail.tab);
    });

    $('rail').addEventListener('rail-action', (e) => {
      switch (e.detail.action) {
        case 'download': this._toggleDownload(); break;
        case 'settings': this._openSettings(); break;
        case 'theme': this._toggleTheme(); break;
      }
    });

    // ── Home view navigation ──
    $('home').addEventListener('navigate-album', (e) => {
      this._navigateToAlbum(e.detail.artist, e.detail.album);
    });

    $('home').addEventListener('navigate-artist', (e) => {
      this._setView('library');
      $('search').value = e.detail.artist;
      $('grid').search = e.detail.artist;
    });

    // ── Library tabs ──
    $('tabs').addEventListener('click', (e) => {
      const tab = e.target.closest('.tab');
      if (!tab) return;
      $('tabs').querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      $('grid').view = tab.dataset.view;
    });

    // ── Search ──
    $('search').addEventListener('input', () => {
      $('grid').search = $('search').value;
    });

    // ── Album → detail (slide panel open) ──
    $('grid').addEventListener('album-select', (e) => {
      $('detail').album = e.detail;
      this.setAttribute('detail-open', '');
    });

    // ── Detail → back (slide panel closed) ──
    $('detail').addEventListener('back', () => {
      this.removeAttribute('detail-open');
    });

    // ── Track play ──
    $('detail').addEventListener('track-play', (e) => {
      this._play(e.detail);
    });

    // ── Now-playing controls ──
    $('player').addEventListener('control', (e) => {
      this._handleControl(e.detail);
    });

    // ── Now-playing → navigate to album ──
    $('player').addEventListener('navigate-to-album', (e) => {
      this._navigateToAlbum(e.detail.artist, e.detail.album);
    });

    // ── Device picker ──
    $('player').addEventListener('toggle-devices', async () => {
      const devices = await fetchDevices();
      $('devices').devices = devices;
      $('devices').setAttribute('open', '');
    });

    $('devices').addEventListener('device-select', async (e) => {
      if (e.detail.id === 'local') {
        if (this._mode === 'cast') controlPlayback('stop');
        this._selectedDevice = null;
        this._mode = 'local';
        if (this._queueIndex >= 0 && this._queue.length) this._playLocal();
        return;
      }

      this._selectedDevice = e.detail;
      this._mode = 'cast';
      await this._fetchServerIp();
      if (this._queueIndex >= 0 && this._queue.length) {
        const ok = await this._castQueue(this._queue, this._queueIndex);
        if (ok) {
          this._audio.pause();
        } else {
          this._mode = 'local';
          this._playLocal();
        }
      }
    });

    // ── Settings events ──
    $('settings').addEventListener('username-change', (e) => {
      $('home').userName = e.detail.name;
    });

    $('settings').addEventListener('musicdir-change', () => {
      this._loadLibrary();
    });

    $('settings').addEventListener('ip-change', () => {
      this._castBaseUrl = null;
    });

    // ── Download events ──
    $('downloader').addEventListener('download-complete', () => {
      this._loadLibrary();
    });

    $('downloader').addEventListener('download-activity', (e) => {
      $('rail').downloadActive = e.detail.active;
    });

    // Restore theme
    const savedTheme = localStorage.getItem('musicast-theme');
    if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);
    $('rail').updateThemeIcon(savedTheme === 'dark');

    // Set greeting name
    $('home').userName = localStorage.getItem('musicast-username') || '';

    // Media Session (lock screen / notification controls)
    this._setupMediaSession();

    // Load library and start UI update loop
    this._loadLibrary();
    this._startUpdateLoop();
  }

  disconnectedCallback() {
    if (this._pollId) clearInterval(this._pollId);
  }

  // ── View routing ──

  _setView(tab) {
    const $ = id => this.shadowRoot.getElementById(id);
    this._view = tab;
    $('rail').active = tab;

    const home = $('home');
    const library = $('library');

    home.removeAttribute('active');
    library.removeAttribute('active');

    if (tab === 'home') {
      home.setAttribute('active', '');
      home.refresh();
    } else if (tab === 'library') {
      library.setAttribute('active', '');
    }
  }

  _navigateToAlbum(artist, album) {
    const $ = id => this.shadowRoot.getElementById(id);
    this._setView('library');

    const found = this._albums.find(a => a.artist === artist && a.album === album);
    if (found) {
      $('detail').album = found;
      this.setAttribute('detail-open', '');
    }
  }

  // ── Actions ──

  _toggleDownload() {
    const $ = id => this.shadowRoot.getElementById(id);
    const dl = $('downloader');
    if (dl.hasAttribute('open')) {
      dl.removeAttribute('open');
    } else {
      dl.setAttribute('open', '');
    }
  }

  _openSettings() {
    const $ = id => this.shadowRoot.getElementById(id);
    const sp = $('settings');
    sp.load();
    sp.setAttribute('open', '');
  }

  _toggleTheme() {
    const $ = id => this.shadowRoot.getElementById(id);
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const next = isDark ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('musicast-theme', next);
    $('rail').updateThemeIcon(!isDark);
  }

  // ── Library ──

  async _loadLibrary() {
    try {
      this._albums = await fetchLibrary();
      this.shadowRoot.getElementById('grid').albums = this._albums;
    } catch (e) {
      console.error('Library load failed:', e);
    }
  }

  // ── Playback ──

  _play({ artist, album, cover, tracks, index }) {
    this._queue = tracks.map((file) => {
      const match = file.match(/^\d+\s*-\s*(.+)\.mp3$/i);
      const title = match ? match[1] : file;
      return {
        url: `/music/${encodeURIComponent(artist)}/${encodeURIComponent(album)}/${encodeURIComponent(file)}`,
        title, artist, album,
        cover: cover || null,
      };
    });
    this._queueIndex = index;

    if (this._mode === 'cast' && this._selectedDevice) {
      this._castQueue(this._queue, index).then(ok => {
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

  _playLocal() {
    const track = this._queue[this._queueIndex];
    if (!track) return;
    this._audio.src = track.url;
    this._audio.play();
    this._updateMediaSession(track);
    recordPlay(track);
  }

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

  async _castQueue(queue, index) {
    if (!this._selectedDevice) return false;
    try {
      const baseUrl = this._getCastBaseUrl();
      const result = await castTrack(
        this._selectedDevice.id, queue[index], queue, index, baseUrl
      );
      if (result.error) {
        console.error('Cast error:', result.error);
        return false;
      }
      recordPlay(queue[index]);
      return true;
    } catch (e) {
      console.error('Cast failed:', e);
      return false;
    }
  }

  _handleControl(action) {
    if (this._mode === 'cast') {
      if (action.type === 'seek') controlPlayback('seek', action.value);
      else if (action.type === 'volume') controlPlayback('volume', action.value);
      else controlPlayback(action.type);
    } else {
      switch (action.type) {
        case 'play':
          this._audio.play(); break;
        case 'pause':
          this._audio.pause(); break;
        case 'toggle':
          this._audio.paused ? this._audio.play() : this._audio.pause(); break;
        case 'next':
          if (this._queueIndex < this._queue.length - 1) {
            this._queueIndex++;
            this._playLocal();
          }
          break;
        case 'prev':
          if (this._audio.currentTime > 3) {
            this._audio.currentTime = 0;
          } else if (this._queueIndex > 0) {
            this._queueIndex--;
            this._playLocal();
          }
          break;
        case 'seek':
          if (action.value != null) this._audio.currentTime = action.value;
          break;
        case 'volume':
          if (action.value != null) this._audio.volume = action.value;
          break;
      }
    }
  }

  // ── UI Update Loop ──

  _startUpdateLoop() {
    this._pollId = setInterval(async () => {
      const player = this.shadowRoot.getElementById('player');
      const detail = this.shadowRoot.getElementById('detail');

      if (this._mode === 'cast' && this._selectedDevice) {
        try {
          const status = await fetchStatus();
          const track = this._queue[this._queueIndex];
          if (status.state === 'idle' && track) {
            player.update({
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
            });
          } else {
            player.update(status);
          }
          if (status.state !== 'idle') {
            const playing = this._queue[this._queueIndex];
            if (playing && detail._album &&
                playing.artist === detail._album.artist &&
                playing.album === detail._album.album) {
              detail.highlightTrack(status.queueIndex);
            } else {
              detail.highlightTrack(-1);
            }
          }
        } catch { /* silent */ }
      } else {
        const track = this._queue[this._queueIndex];
        if (track && this._audio.src) {
          player.update({
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
          });
          const playing = this._queue[this._queueIndex];
          if (playing && detail._album &&
              playing.artist === detail._album.artist &&
              playing.album === detail._album.album) {
            detail.highlightTrack(this._queueIndex);
          } else {
            detail.highlightTrack(-1);
          }
          this._syncMediaSessionPosition();
        } else {
          player.update({ state: 'idle' });
        }
      }
    }, 500);
  }

  // ── Media Session API ──

  _setupMediaSession() {
    if (!('mediaSession' in navigator)) return;
    const ms = navigator.mediaSession;

    ms.setActionHandler('play', () => this._handleControl({ type: 'play' }));
    ms.setActionHandler('pause', () => this._handleControl({ type: 'pause' }));
    ms.setActionHandler('previoustrack', () => this._handleControl({ type: 'prev' }));
    ms.setActionHandler('nexttrack', () => this._handleControl({ type: 'next' }));
    ms.setActionHandler('seekto', (e) => {
      this._handleControl({ type: 'seek', value: e.seekTime });
    });
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

customElements.define('music-app', MusicApp);
