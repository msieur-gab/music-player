const tpl = document.createElement('template');
tpl.innerHTML = `
<style>
:host {
  display: block;
  padding: 24px;
  animation: fadeIn 200ms ease;
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}

.back {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: none;
  color: var(--accent);
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  padding: 4px 0;
  margin-bottom: 20px;
}
.back svg {
  width: 18px; height: 18px;
  stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round;
}

.header {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  margin-bottom: 24px;
}

.cover {
  width: 200px; height: 200px;
  border-radius: var(--radius-lg);
  object-fit: cover;
  flex-shrink: 0;
  box-shadow: var(--shadow-md);
  background: var(--bg-hover);
}

.cover-ph {
  width: 200px; height: 200px;
  border-radius: var(--radius-lg);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-hover);
  color: var(--text-faint);
  flex-shrink: 0;
}
.cover-ph[hidden] { display: none; }
.cover-ph svg {
  width: 64px; height: 64px;
  stroke: currentColor; fill: none;
  stroke-width: 1.2;
}

.details h2 {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
  margin-bottom: 4px;
}

.artist {
  font-size: 16px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.meta {
  font-size: 13px;
  color: var(--text-faint);
  margin-bottom: 16px;
}

.play-all {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 20px;
  border: none;
  border-radius: 20px;
  background: var(--accent);
  color: var(--accent-text);
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: opacity var(--transition);
}
.play-all:hover { opacity: 0.9; }
.play-all svg {
  width: 16px; height: 16px;
  fill: currentColor; stroke: none;
}

.actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

.save-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition);
}
.save-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}
.save-btn[hidden] { display: none; }
.save-btn svg {
  width: 14px; height: 14px;
  stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
}

.tracks {
  list-style: none;
  padding: 0;
}

.track {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 14px;
  transition: background var(--transition);
}
.track:hover { background: var(--bg-hover); }
.track[aria-current="true"] { color: var(--accent); }

.track-num {
  width: 28px;
  text-align: right;
  margin-right: 16px;
  color: var(--text-faint);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}
.track[aria-current="true"] .track-num { color: var(--accent); }

.track-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.track-artist {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  flex: 1;
}
.track-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.track-dur {
  font-size: 12px;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
  margin-left: 12px;
  flex-shrink: 0;
}

@media (max-width: 600px) {
  .header { flex-direction: column; gap: 16px; }
  .cover, .cover-ph { width: 140px; height: 140px; }
  :host { padding: 16px; }
}
</style>

<button class="back">
  <svg viewBox="0 0 24 24"><path d="m15 18-6-6 6-6"/></svg>
  <span id="back-label">Albums</span>
</button>

<div class="header">
  <img class="cover" id="cover" hidden>
  <div class="cover-ph" id="cover-ph">
    <svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
  </div>
  <div class="details">
    <h2 id="title"></h2>
    <div class="artist" id="artist"></div>
    <div class="meta" id="meta"></div>
    <div class="actions">
      <button class="play-all" id="play-all">
        <svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        Play album
      </button>
      <button class="save-btn" id="save-btn" hidden>
        <svg viewBox="0 0 24 24"><path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z"/></svg>
        Save
      </button>
    </div>
  </div>
</div>

<ol class="tracks" id="tracks"></ol>
`;

class AlbumDetail extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
    this._album = null;
  }

  connectedCallback() {
    this.shadowRoot.querySelector('.back').addEventListener('click', () => {
      this.dispatchEvent(new CustomEvent('back', { bubbles: true, composed: true }));
    });

    this.shadowRoot.getElementById('play-all').addEventListener('click', () => {
      if (this._album || this._playlist) this._emitPlay(0);
    });

    this.shadowRoot.getElementById('save-btn').addEventListener('click', () => {
      if (!this._playlist) return;
      const now = new Date();
      const defaultName = `${this._playlist.label} \u2014 ${now.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })}`;
      const name = prompt('Playlist name:', defaultName);
      if (!name) return;
      this.dispatchEvent(new CustomEvent('save-playlist', {
        bubbles: true, composed: true,
        detail: {
          name,
          zone: this._playlist.zoneId || '',
          tracks: this._playlist.tracks.map(t => t.key),
        },
      }));
    });

    this.shadowRoot.getElementById('tracks').addEventListener('click', (e) => {
      const li = e.target.closest('.track');
      if (li) this._emitPlay(parseInt(li.dataset.index, 10));
    });
  }

  set backLabel(label) {
    this.shadowRoot.getElementById('back-label').textContent = label;
  }

  set saved(v) {
    this.shadowRoot.getElementById('save-btn').hidden = !!v;
  }

  set album(a) {
    this._album = a;
    this._playlist = null;
    if (!a) return;

    this.shadowRoot.getElementById('save-btn').hidden = true;

    const cover = this.shadowRoot.getElementById('cover');
    const coverPh = this.shadowRoot.getElementById('cover-ph');
    if (a.cover) {
      cover.src = a.cover;
      cover.hidden = false;
      coverPh.hidden = true;
    } else {
      cover.hidden = true;
      coverPh.hidden = false;
    }

    this.shadowRoot.getElementById('title').textContent = a.album;
    this.shadowRoot.getElementById('artist').textContent = a.artist;

    const parts = [];
    if (a.year) parts.push(a.year);
    if (a.genre) parts.push(a.genre);
    parts.push(`${a.trackCount} tracks`);
    const totalDur = a.tracks.reduce((sum, t) => sum + (typeof t === 'string' ? 0 : (t.duration || 0)), 0);
    if (totalDur) parts.push(this._fmtDur(totalDur));
    this.shadowRoot.getElementById('meta').textContent = parts.join(' \u2022 ');

    this.shadowRoot.getElementById('play-all').innerHTML =
      '<svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg> Play album';

    this._renderTracks();
  }

  set playlist(p) {
    this._playlist = p;
    this._album = null;
    if (!p) return;

    this.shadowRoot.getElementById('save-btn').hidden = !!p.saved;

    const cover = this.shadowRoot.getElementById('cover');
    const coverPh = this.shadowRoot.getElementById('cover-ph');
    cover.hidden = true;
    coverPh.hidden = false;

    this.shadowRoot.getElementById('title').textContent = p.label;
    this.shadowRoot.getElementById('artist').textContent = p.desc;
    this.shadowRoot.getElementById('meta').textContent = `${p.tracks.length} tracks`;

    this.shadowRoot.getElementById('play-all').innerHTML =
      '<svg viewBox="0 0 24 24"><polygon points="5 3 19 12 5 21 5 3"/></svg> Play all';

    this._renderPlaylistTracks();
  }

  highlightTrack(index) {
    this.shadowRoot.querySelectorAll('.track').forEach(li => {
      li.setAttribute('aria-current', li.dataset.index === String(index) ? 'true' : 'false');
    });
  }

  highlightByUrl(url) {
    if (!url) { this.highlightTrack(-1); return; }
    const decoded = decodeURIComponent(url);
    const tracks = this._playlist ? this._playlist.tracks : null;
    const albumTracks = this._album ? this._album.tracks : null;

    if (tracks) {
      const idx = tracks.findIndex(t => decoded.includes(t.file));
      this.highlightTrack(idx);
    } else if (albumTracks) {
      const idx = albumTracks.findIndex(t => {
        const f = typeof t === 'string' ? t : t.file;
        return decoded.includes(f);
      });
      this.highlightTrack(idx);
    }
  }

  _fmtDur(s) {
    if (!s || !isFinite(s)) return '';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  }

  _renderTracks() {
    const list = this.shadowRoot.getElementById('tracks');
    list.innerHTML = '';
    if (!this._album) return;

    this._album.tracks.forEach((t, i) => {
      const file = typeof t === 'string' ? t : t.file;
      const duration = typeof t === 'string' ? 0 : (t.duration || 0);
      const match = file.match(/^(\d+)\s*-\s*(.+)\.mp3$/i);
      const num = match ? match[1] : String(i + 1).padStart(2, '0');
      const name = match ? match[2] : file;

      const li = document.createElement('li');
      li.className = 'track';
      li.dataset.index = i;

      const numSpan = document.createElement('span');
      numSpan.className = 'track-num';
      numSpan.textContent = num;

      const nameSpan = document.createElement('span');
      nameSpan.className = 'track-name';
      nameSpan.textContent = name;

      li.append(numSpan, nameSpan);

      if (duration) {
        const durSpan = document.createElement('span');
        durSpan.className = 'track-dur';
        durSpan.textContent = this._fmtDur(duration);
        li.append(durSpan);
      }

      list.appendChild(li);
    });
  }

  _renderPlaylistTracks() {
    const list = this.shadowRoot.getElementById('tracks');
    list.innerHTML = '';
    if (!this._playlist) return;

    this._playlist.tracks.forEach((track, i) => {
      const li = document.createElement('li');
      li.className = 'track';
      li.dataset.index = i;

      const numSpan = document.createElement('span');
      numSpan.className = 'track-num';
      numSpan.textContent = String(i + 1).padStart(2, '0');

      const info = document.createElement('div');
      info.className = 'track-info';

      const nameSpan = document.createElement('span');
      nameSpan.className = 'track-name';
      nameSpan.textContent = track.title;

      const artistSpan = document.createElement('span');
      artistSpan.className = 'track-artist';
      artistSpan.textContent = track.artist;

      info.append(nameSpan, artistSpan);
      li.append(numSpan, info);
      list.appendChild(li);
    });
  }

  _emitPlay(index) {
    if (this._playlist) {
      this.dispatchEvent(new CustomEvent('playlist-play', {
        bubbles: true, composed: true,
        detail: { tracks: this._playlist.tracks, index },
      }));
    } else if (this._album) {
      this.dispatchEvent(new CustomEvent('track-play', {
        bubbles: true, composed: true,
        detail: {
          artist: this._album.artist,
          album: this._album.album,
          cover: this._album.cover,
          tracks: this._album.tracks,
          index,
        },
      }));
    }
  }
}

customElements.define('album-detail', AlbumDetail);
