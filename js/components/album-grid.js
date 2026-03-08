const tpl = document.createElement('template');
tpl.innerHTML = `
<style>
:host { display: block; }

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 16px;
  padding: 24px;
}

.empty {
  grid-column: 1 / -1;
  text-align: center;
  padding: 80px 24px;
  color: var(--text-muted);
  font-size: 15px;
  line-height: 1.6;
}

.group-header {
  grid-column: 1 / -1;
  font-size: 13px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-muted);
  padding: 12px 0 4px;
  border-bottom: 1px solid var(--border);
  margin-top: 8px;
}
.group-header:first-child { margin-top: 0; }

.card {
  cursor: pointer;
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--bg-raised);
  box-shadow: var(--shadow-sm);
  transition: transform var(--transition), box-shadow var(--transition);
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
}
.card:active {
  transform: translateY(0);
}

.cover {
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
  display: block;
  background: var(--bg-hover);
}

.cover-ph {
  width: 100%;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-hover);
  color: var(--text-faint);
  font-size: 32px;
}
.cover-ph svg {
  width: 40px; height: 40px;
  stroke: currentColor; fill: none;
  stroke-width: 1.5;
}

.info { padding: 10px 12px 12px; }

.title {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text);
}

.subtitle {
  font-size: 12px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 2px;
}

.meta {
  font-size: 11px;
  color: var(--text-faint);
  margin-top: 2px;
}

@media (max-width: 600px) {
  .grid {
    grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
    gap: 12px;
    padding: 16px;
  }
}
</style>
<div class="grid"></div>
`;

class AlbumGrid extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
    this._grid = this.shadowRoot.querySelector('.grid');
    this._albums = [];
    this._view = 'artists';
    this._search = '';
  }

  set albums(list) {
    this._albums = list || [];
    this._render();
  }

  set view(v) {
    this._view = v;
    this._render();
  }

  set search(term) {
    this._search = (term || '').toLowerCase();
    this._render();
  }

  _filtered() {
    if (!this._search) return this._albums;
    const q = this._search;
    return this._albums.filter(a =>
      a.artist.toLowerCase().includes(q) ||
      a.album.toLowerCase().includes(q) ||
      (a.genre || '').toLowerCase().includes(q) ||
      a.tracks.some(t => t.toLowerCase().includes(q))
    );
  }

  _grouped(albums) {
    const groups = {};
    for (const a of albums) {
      let key;
      if (this._view === 'artists') key = a.artist;
      else if (this._view === 'albums') key = (a.album[0] || '#').toUpperCase();
      else if (this._view === 'genres') key = a.genre || 'Unknown';
      else key = a.artist;
      (groups[key] ??= []).push(a);
    }
    return Object.keys(groups).sort((a, b) => a.localeCompare(b))
      .map(key => ({ key, albums: groups[key] }));
  }

  _render() {
    const filtered = this._filtered();
    const groups = this._grouped(filtered);
    this._grid.innerHTML = '';

    if (!filtered.length) {
      this._grid.innerHTML = `<div class="empty">
        ${this._albums.length ? 'No results' : 'No music yet — paste a YouTube Music playlist URL to get started.'}
      </div>`;
      return;
    }

    for (const group of groups) {
      const header = document.createElement('div');
      header.className = 'group-header';
      header.textContent = group.key;
      this._grid.appendChild(header);

      for (const album of group.albums) {
        const card = document.createElement('article');
        card.className = 'card';

        if (album.cover) {
          const img = document.createElement('img');
          img.className = 'cover';
          img.src = album.cover;
          img.alt = album.album;
          img.loading = 'lazy';
          card.appendChild(img);
        } else {
          const ph = document.createElement('div');
          ph.className = 'cover-ph';
          ph.innerHTML = '<svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>';
          card.appendChild(ph);
        }

        const info = document.createElement('div');
        info.className = 'info';

        const title = document.createElement('div');
        title.className = 'title';
        title.textContent = album.album;

        const sub = document.createElement('div');
        sub.className = 'subtitle';
        sub.textContent = album.artist;

        info.append(title, sub);

        if (album.year || album.trackCount) {
          const meta = document.createElement('div');
          meta.className = 'meta';
          const parts = [];
          if (album.year) parts.push(album.year);
          parts.push(`${album.trackCount} tracks`);
          meta.textContent = parts.join(' \u2022 ');
          info.appendChild(meta);
        }

        card.appendChild(info);
        card.addEventListener('click', () => {
          this.dispatchEvent(new CustomEvent('album-select', {
            bubbles: true, composed: true, detail: album,
          }));
        });
        this._grid.appendChild(card);
      }
    }
  }
}

customElements.define('album-grid', AlbumGrid);
