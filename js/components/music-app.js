import { fetchLibrary, fetchPlaylist, fetchZones, fetchSavedPlaylist, savePlaylistApi, deleteSavedPlaylist, fetchSimilar } from '../services/api.js';
import { loadAddons } from '../services/addons.js';
import { playback } from '../services/playback.js';
import { trackStore } from '../services/track-store.js';
import { applyTheme, applyThemeAll, onThemeChange } from '../services/theme-bridge.js';
import './nav-rail.js';
import './home-view.js';
import './album-grid.js';
import './album-detail.js';
import './playlist-list.js';
import './now-playing.js';
import './settings-panel.js';
import './addon-manager.js';

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
.albums-view          { grid-area: feed; display: none; min-height: 0; }
.albums-view[active]  { display: flex; flex-direction: column; }
playlist-list     { grid-area: feed; }

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

/* ── Albums view header ── */
.lib-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 24px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.view-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}

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

<div class="albums-view" id="albums-view">
  <div class="lib-header">
    <h2 class="view-title">Albums</h2>
    <span class="spacer"></span>
    <input class="search" id="search" type="search" placeholder="Search..." autocomplete="off">
  </div>
  <div class="lib-content">
    <album-grid id="grid"></album-grid>
  </div>
</div>

<playlist-list id="playlists"></playlist-list>

<album-detail id="detail"></album-detail>

<now-playing id="player"></now-playing>
<span id="addon-container"></span>
<settings-panel id="settings"></settings-panel>
<addon-manager id="addon-manager"></addon-manager>
`;

class MusicApp extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
    this._albums = [];
    this._pollId = null;
    this._view = 'home';
  }

  connectedCallback() {
    const $ = id => this.shadowRoot.getElementById(id);

    // ── Rail navigation ──
    $('rail').addEventListener('rail-navigate', (e) => {
      this._setView(e.detail.tab);
    });

    $('rail').addEventListener('rail-action', (e) => {
      switch (e.detail.action) {
        case 'addons': this._openAddonManager(); break;
        case 'settings': this._openSettings(); break;
        case 'theme': this._toggleTheme(); break;
        default:
          // Addon action — toggle the addon's component
          this._toggleAddon(e.detail.action);
          break;
      }
    });

    // ── Home view navigation ──
    $('home').addEventListener('navigate-album', (e) => {
      this._navigateToAlbum(e.detail.artist, e.detail.album);
    });

    $('home').addEventListener('open-zone', (e) => {
      this._openZone(e.detail.zone);
    });

    $('home').addEventListener('navigate-artist', (e) => {
      this._setView('albums');
      $('search').value = e.detail.artist;
      $('grid').search = e.detail.artist;
    });

    // ── Search ──
    $('search').addEventListener('input', () => {
      $('grid').search = $('search').value;
    });

    // ── Album → detail (slide panel open) ──
    $('grid').addEventListener('album-select', (e) => {
      $('detail').album = e.detail;
      $('detail').backLabel = 'Albums';
      this.setAttribute('detail-open', '');
    });

    // ── Playlists ──
    $('playlists').addEventListener('playlist-open', async (e) => {
      const data = await fetchSavedPlaylist(e.detail.id);
      if (!data || data.error) return;
      $('detail').playlist = {
        label: data.name,
        desc: data.zoneLabel || data.zoneDesc || '',
        zoneId: data.zone,
        tracks: data.tracks,
        saved: true,
      };
      $('detail').backLabel = 'Playlists';
      this.setAttribute('detail-open', '');
    });

    $('playlists').addEventListener('playlist-delete', async (e) => {
      if (!confirm(`Delete "${e.detail.name}"?`)) return;
      await deleteSavedPlaylist(e.detail.id);
      $('playlists').refresh();
    });

    // ── Detail → back (slide panel closed) ──
    $('detail').addEventListener('back', () => {
      this.removeAttribute('detail-open');
    });

    // ── Track play ──
    $('detail').addEventListener('track-play', (e) => {
      this._play(e.detail);
    });

    $('detail').addEventListener('playlist-play', (e) => {
      this._playPlaylist(e.detail.tracks, e.detail.index);
    });

    // ── Save playlist ──
    $('detail').addEventListener('save-playlist', async (e) => {
      const { name, zone, tracks } = e.detail;
      await savePlaylistApi(name, zone, tracks);
      $('detail').saved = true;
    });

    // ── Find similar ──
    $('detail').addEventListener('find-similar', (e) => {
      this._openSimilar(e.detail.artist, e.detail.album, e.detail.title);
    });

    // ── Now-playing controls → PlaybackController ──
    $('player').addEventListener('control', (e) => {
      const a = e.detail;
      switch (a.type) {
        case 'play':   playback.resume(); break;
        case 'pause':  playback.pause(); break;
        case 'toggle': playback.toggle(); break;
        case 'next':   playback.next(); break;
        case 'prev':   playback.prev(); break;
        case 'seek':   playback.seek(a.value); break;
        case 'volume': playback.volume(a.value); break;
      }
    });

    // ── Now-playing → navigate to album ──
    $('player').addEventListener('navigate-to-album', (e) => {
      this._navigateToAlbum(e.detail.artist, e.detail.album);
    });

    // ── Device picker (chromecast addon) ──
    $('player').addEventListener('toggle-devices', () => {
      const picker = this.shadowRoot.querySelector('device-picker');
      if (picker) {
        picker.setAttribute('open', '');
      }
    });

    // Listen for device-select from addon → PlaybackController
    this.shadowRoot.addEventListener('device-select', (e) => {
      playback.selectDevice(e.detail);
    });

    // ── Download addon events (bubbles through shadow DOM) ──
    this.shadowRoot.addEventListener('download-complete', () => {
      this._loadLibrary();
      trackStore.refresh();
    });

    // ── Analysis complete — refresh library + track store ──
    this.shadowRoot.addEventListener('analysis-complete', () => {
      this._loadLibrary();
      trackStore.refresh();
    });

    this.shadowRoot.addEventListener('download-activity', (e) => {
      $('rail').setAddonBadge('downloader', e.detail.active);
    });

    // ── Addon manager — reload addon UI after install ──
    this.shadowRoot.addEventListener('addon-installed', () => {
      this._loadAddons();
    });

    // ── View addon events — universal contract ──
    this.shadowRoot.addEventListener('addon-play', (e) => {
      this._playPlaylist(e.detail.tracks, e.detail.index);
    });

    this.shadowRoot.addEventListener('addon-playlist', (e) => {
      const { label, desc, tracks } = e.detail;
      const detail = this.shadowRoot.getElementById('detail');
      detail.playlist = { label, desc, tracks, saved: false };
      // Use addon's display name for back button, or capitalize the view ID
      const viewName = this._addonNames?.[this._view] || this._view;
      detail.backLabel = viewName.charAt(0).toUpperCase() + viewName.slice(1);
      this.setAttribute('detail-open', '');
    });

    // ── Settings events ──
    $('settings').addEventListener('username-change', (e) => {
      $('home').userName = e.detail.name;
    });

    $('settings').addEventListener('musicdir-change', () => {
      this._loadLibrary();
    });

    $('settings').addEventListener('ip-change', () => {
      playback.resetCastUrl();
    });

    // Restore theme
    const savedTheme = localStorage.getItem('musicast-theme');
    if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);
    $('rail').updateThemeIcon(savedTheme === 'dark');

    // Set greeting name
    $('home').userName = localStorage.getItem('musicast-username') || '';

    // Load addons, library, track store, and start UI update loop
    this._loadAddons();
    this._loadLibrary();
    trackStore.load(); // preload shared track data (non-blocking)
    this._startUpdateLoop();
  }

  disconnectedCallback() {
    if (this._pollId) clearInterval(this._pollId);
    if (this._themeUnsub) {
      this._themeUnsub();
      this._themeUnsub = null;
    }
    if (this._resumePoll) {
      document.removeEventListener('click', this._resumePoll);
      document.removeEventListener('keydown', this._resumePoll);
    }
  }

  // ── View routing ──

  _setView(tab) {
    const $ = id => this.shadowRoot.getElementById(id);
    this._view = tab;
    $('rail').active = tab;

    const home = $('home');
    const albumsView = $('albums-view');
    const playlists = $('playlists');

    home.removeAttribute('active');
    albumsView.removeAttribute('active');
    playlists.removeAttribute('active');

    // Hide all addon views
    if (this._addonViews) {
      for (const [id, el] of Object.entries(this._addonViews)) {
        el.style.display = 'none';
      }
    }

    if (tab === 'home') {
      home.setAttribute('active', '');
      home.refresh();
    } else if (tab === 'albums') {
      albumsView.setAttribute('active', '');
    } else if (tab === 'playlists') {
      playlists.setAttribute('active', '');
      playlists.refresh();
    } else if (this._addonViews?.[tab]) {
      // Addon view
      this._addonViews[tab].style.display = 'flex';
    }
  }

  _navigateToAlbum(artist, album) {
    const $ = id => this.shadowRoot.getElementById(id);
    this._setView('albums');

    const found = this._albums.find(a => a.artist === artist && a.album === album);
    if (found) {
      $('detail').album = found;
      $('detail').backLabel = 'Albums';
      this.setAttribute('detail-open', '');
    }
  }

  // ── Actions ──

  _toggleAddon(addonId) {
    const el = this.shadowRoot.getElementById(`addon-${addonId}`);
    if (!el) return;
    if (el.hasAttribute('open')) {
      el.removeAttribute('open');
    } else {
      el.setAttribute('open', '');
    }
  }

  async _loadAddons() {
    const addons = await loadAddons();
    const container = this.shadowRoot.getElementById('addon-container');
    const rail = this.shadowRoot.getElementById('rail');

    this._addonViews = this._addonViews || {};
    this._addonNames = this._addonNames || {};

    for (const addon of addons) {
      // Skip if already loaded
      if (this.shadowRoot.getElementById(`addon-${addon.id}`)) continue;

      const el = document.createElement(addon.component);
      el.id = `addon-${addon.id}`;

      if (addon.trigger?.slot === 'rail') {
        if (addon.type === 'view') {
          // View addon: render as a switchable view in the feed area
          el.style.gridArea = 'feed';
          el.style.display = 'none';
          el.style.minHeight = '0';
          this.shadowRoot.insertBefore(el, container);
          this._addonViews[addon.id] = el;
          this._addonNames[addon.id] = addon.name;
          rail.addAddonButton(addon.id, addon.trigger, 'tab');
          // Inject theme tokens into shadow DOM
          applyTheme(el);
        } else {
          // Backend addon: overlay (download panel, etc.)
          container.appendChild(el);
          rail.addAddonButton(addon.id, addon.trigger);
        }
      } else {
        container.appendChild(el);
      }
    }

    // Re-apply theme to all view addons when theme toggles (register once)
    if (Object.keys(this._addonViews).length > 0 && !this._themeUnsub) {
      this._themeUnsub = onThemeChange(() => applyThemeAll(Object.values(this._addonViews)));
    }
  }

  _openAddonManager() {
    this.shadowRoot.getElementById('addon-manager').setAttribute('open', '');
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

  // ── Zone playlist ──

  async _openZone(zone) {
    try {
      const [tracks, zones] = await Promise.all([
        fetchPlaylist(zone),
        fetchZones(),
      ]);
      if (!tracks.length) return;

      const zoneMeta = zones.find(z => z.id === zone) || {};
      const detail = this.shadowRoot.getElementById('detail');
      detail.playlist = {
        label: zoneMeta.label || zone,
        desc: zoneMeta.desc || '',
        zoneId: zone,
        tracks,
        saved: false,
      };
      detail.backLabel = 'Home';
      this.setAttribute('detail-open', '');
    } catch (e) {
      console.error('Zone playlist failed:', e);
    }
  }

  // ── Similar tracks ──

  async _openSimilar(artist, album, title) {
    try {
      const tracks = await fetchSimilar(artist, album, title, 25);
      if (!tracks.length) return;

      // Add cover URLs for each track
      for (const t of tracks) {
        if (!t.cover) t.cover = trackStore.getCover(t.artist, t.album);
      }

      const detail = this.shadowRoot.getElementById('detail');
      detail.playlist = {
        label: `Similar to ${title}`,
        desc: `${artist} — ${album}`,
        tracks,
        saved: false,
      };
      detail.backLabel = 'Albums';
      this.setAttribute('detail-open', '');
    } catch (e) {
      console.error('Find similar failed:', e);
    }
  }

  // ── Playback — delegate to PlaybackController ──

  _playPlaylist(tracks, index) {
    playback.play(tracks, index);
  }

  _play(detail) {
    playback.playAlbum(detail);
  }

  // ── UI Update Loop ──

  _startUpdateLoop() {
    let fails = 0;
    let paused = false;

    // Resume polling on any user interaction after server failure
    this._resumePoll = () => {
      if (paused) { fails = 0; paused = false; }
    };
    document.addEventListener('click', this._resumePoll);
    document.addEventListener('keydown', this._resumePoll);

    this._pollId = setInterval(async () => {
      if (paused) return;

      try {
        const player = this.shadowRoot.getElementById('player');
        const detail = this.shadowRoot.getElementById('detail');

        const status = await playback.getStatus();
        fails = 0;
        player.update(status);

        const track = playback.currentTrack;
        if (status.state !== 'idle' && track) {
          detail.highlightByUrl(track.url);

          // Notify active view addon which track is playing
          const activeView = this._addonViews?.[this._view];
          if (activeView) {
            activeView.dispatchEvent(new CustomEvent('highlight-track', {
              detail: { url: track.url, trackId: track.track_id },
            }));
          }
        }
      } catch {
        if (++fails >= 3) paused = true;
      }
    }, 500);
  }

}

customElements.define('music-app', MusicApp);
