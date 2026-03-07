import { fetchLibrary } from '../services/api.js';

/**
 * Manages the album data and provides filtered/grouped views.
 * Dispatches 'album-selected' when a card is clicked.
 */
export class Library {
  constructor(gridEl, navEl, searchEl) {
    this.grid = gridEl;
    this.albums = [];
    this.view = 'artists';

    // Nav tabs
    navEl.addEventListener('click', (e) => {
      const tab = e.target.closest('.tab');
      if (!tab) return;
      navEl.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      this.view = tab.dataset.view;
      this.render();
    });

    // Search
    searchEl.addEventListener('input', () => {
      this._searchTerm = searchEl.value.trim().toLowerCase();
      this.render();
    });
    this._searchTerm = '';
  }

  async load() {
    this.albums = await fetchLibrary();
    this.render();
  }

  _filtered() {
    if (!this._searchTerm) return this.albums;
    const q = this._searchTerm;
    return this.albums.filter(a =>
      a.artist.toLowerCase().includes(q) ||
      a.album.toLowerCase().includes(q) ||
      a.genre.toLowerCase().includes(q) ||
      a.tracks.some(t => t.toLowerCase().includes(q))
    );
  }

  _grouped(albums) {
    const groups = {};
    for (const a of albums) {
      let key;
      if (this.view === 'artists') key = a.artist;
      else if (this.view === 'albums') key = a.album[0]?.toUpperCase() || '#';
      else if (this.view === 'genres') key = a.genre || 'Unknown';
      else key = a.artist;

      if (!groups[key]) groups[key] = [];
      groups[key].push(a);
    }
    // Sort group keys
    const sorted = Object.keys(groups).sort((a, b) => a.localeCompare(b));
    return sorted.map(key => ({ key, albums: groups[key] }));
  }

  render() {
    const filtered = this._filtered();
    const groups = this._grouped(filtered);

    this.grid.innerHTML = '';

    for (const group of groups) {
      const header = document.createElement('div');
      header.className = 'group-header';
      header.textContent = group.key;
      this.grid.appendChild(header);

      for (const album of group.albums) {
        this.grid.appendChild(this._createCard(album));
      }
    }
  }

  _createCard(album) {
    const card = document.createElement('article');
    card.className = 'album-card';

    if (album.cover) {
      const img = document.createElement('img');
      img.className = 'cover';
      img.src = album.cover;
      img.alt = `${album.album} cover`;
      img.loading = 'lazy';
      card.appendChild(img);
    } else {
      const ph = document.createElement('div');
      ph.className = 'cover-placeholder';
      ph.textContent = '\u266B';
      card.appendChild(ph);
    }

    const info = document.createElement('div');
    info.className = 'card-info';

    const title = document.createElement('div');
    title.className = 'card-title';
    title.textContent = album.album;

    const subtitle = document.createElement('div');
    subtitle.className = 'card-subtitle';
    subtitle.textContent = album.artist;

    info.append(title, subtitle);
    card.appendChild(info);

    card.addEventListener('click', () => {
      this.grid.dispatchEvent(new CustomEvent('album-selected', {
        bubbles: true,
        detail: album,
      }));
    });

    return card;
  }
}
