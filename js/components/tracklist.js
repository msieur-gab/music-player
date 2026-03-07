/**
 * Renders the track list for a selected album.
 * Dispatches 'track-selected' on click.
 */
export class Tracklist {
  constructor(sectionEl, gridEl) {
    this.section = sectionEl;
    this.grid = gridEl;
    this.coverEl = sectionEl.querySelector('#album-cover');
    this.titleEl = sectionEl.querySelector('#album-title');
    this.artistEl = sectionEl.querySelector('#album-artist');
    this.metaEl = sectionEl.querySelector('#album-meta');
    this.listEl = sectionEl.querySelector('#track-list');
    this.backBtn = sectionEl.querySelector('#back-to-grid');
    this.currentAlbum = null;

    this.backBtn.addEventListener('click', () => this.hide());
  }

  show(album) {
    this.currentAlbum = album;
    this.titleEl.textContent = album.album;
    this.artistEl.textContent = album.artist;

    const parts = [];
    if (album.year) parts.push(album.year);
    if (album.genre) parts.push(album.genre);
    parts.push(`${album.trackCount} tracks`);
    this.metaEl.textContent = parts.join(' \u2022 ');

    if (album.cover) {
      this.coverEl.src = album.cover;
      this.coverEl.hidden = false;
    } else {
      this.coverEl.hidden = true;
    }

    this.grid.style.display = 'none';
    this.section.hidden = false;
    this._renderTracks();
  }

  hide() {
    this.section.hidden = true;
    this.grid.style.display = '';
  }

  _renderTracks() {
    this.listEl.innerHTML = '';
    const tracks = this.currentAlbum.tracks;

    for (let i = 0; i < tracks.length; i++) {
      const file = tracks[i];
      const match = file.match(/^(\d+)\s*-\s*(.+)\.mp3$/i);
      const num = match ? match[1] : String(i + 1).padStart(2, '0');
      const name = match ? match[2] : file;

      const li = document.createElement('li');
      li.dataset.index = i;

      const numSpan = document.createElement('span');
      numSpan.className = 'track-num';
      numSpan.textContent = num;

      const nameSpan = document.createElement('span');
      nameSpan.className = 'track-name';
      nameSpan.textContent = name;

      li.append(numSpan, nameSpan);
      li.addEventListener('click', () => {
        this.listEl.dispatchEvent(new CustomEvent('track-selected', {
          bubbles: true,
          detail: {
            artist: this.currentAlbum.artist,
            album: this.currentAlbum.album,
            tracks,
            index: i,
          }
        }));
      });

      this.listEl.appendChild(li);
    }
  }

  highlightTrack(index) {
    this.listEl.querySelectorAll('li').forEach(li => {
      li.setAttribute('aria-current', li.dataset.index === String(index) ? 'true' : 'false');
    });
  }
}
