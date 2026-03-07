import { formatTime } from '../utils/format.js';

/**
 * Audio player controlling an <audio> element with Web Audio API.
 * Handles play/pause, next/prev, seek, and volume.
 */
export class Player {
  constructor(playerEl) {
    this.el = playerEl;
    this.audio = new Audio();
    this.audio.preload = 'metadata';

    this.titleEl = playerEl.querySelector('#track-title');
    this.artistEl = playerEl.querySelector('#track-artist');
    this.seekBar = playerEl.querySelector('#seek-bar');
    this.currentTimeEl = playerEl.querySelector('#current-time');
    this.durationEl = playerEl.querySelector('#duration');
    this.btnPlay = playerEl.querySelector('#btn-play');
    this.btnPrev = playerEl.querySelector('#btn-prev');
    this.btnNext = playerEl.querySelector('#btn-next');
    this.volumeEl = playerEl.querySelector('#volume');

    this.playlist = [];
    this.currentIndex = -1;
    this._seeking = false;

    this._bindEvents();
  }

  _bindEvents() {
    this.btnPlay.addEventListener('click', () => this.togglePlay());
    this.btnPrev.addEventListener('click', () => this.prev());
    this.btnNext.addEventListener('click', () => this.next());

    this.volumeEl.addEventListener('input', () => {
      this.audio.volume = parseFloat(this.volumeEl.value);
    });

    this.seekBar.addEventListener('mousedown', () => { this._seeking = true; });
    this.seekBar.addEventListener('touchstart', () => { this._seeking = true; }, { passive: true });
    this.seekBar.addEventListener('input', () => {
      this.currentTimeEl.textContent = formatTime(
        (parseFloat(this.seekBar.value) / 100) * this.audio.duration
      );
    });
    this.seekBar.addEventListener('change', () => {
      this.audio.currentTime = (parseFloat(this.seekBar.value) / 100) * this.audio.duration;
      this._seeking = false;
    });

    this.audio.addEventListener('timeupdate', () => {
      if (this._seeking) return;
      const pct = (this.audio.currentTime / this.audio.duration) * 100;
      this.seekBar.value = isFinite(pct) ? pct : 0;
      this.currentTimeEl.textContent = formatTime(this.audio.currentTime);
    });

    this.audio.addEventListener('loadedmetadata', () => {
      this.durationEl.textContent = formatTime(this.audio.duration);
    });

    this.audio.addEventListener('ended', () => this.next());

    this.audio.addEventListener('play', () => { this.btnPlay.textContent = '⏸'; });
    this.audio.addEventListener('pause', () => { this.btnPlay.textContent = '▶'; });
  }

  loadAlbum(artist, album, tracks, startIndex = 0) {
    this.playlist = tracks.map(file => ({
      file,
      url: `/music/${encodeURIComponent(artist)}/${encodeURIComponent(album)}/${encodeURIComponent(file)}`,
      artist,
      album,
    }));
    this.play(startIndex);
  }

  play(index) {
    if (index < 0 || index >= this.playlist.length) return;
    this.currentIndex = index;
    const track = this.playlist[index];

    const match = track.file.match(/^\d+\s*-\s*(.+)\.mp3$/i);
    const name = match ? match[1] : track.file;

    this.titleEl.textContent = name;
    this.artistEl.textContent = track.artist;
    this.audio.src = track.url;
    this.audio.play();
    this.el.hidden = false;

    this.el.dispatchEvent(new CustomEvent('track-change', {
      bubbles: true,
      detail: { index },
    }));
  }

  togglePlay() {
    if (this.audio.paused) {
      this.audio.play();
    } else {
      this.audio.pause();
    }
  }

  next() {
    if (this.currentIndex < this.playlist.length - 1) {
      this.play(this.currentIndex + 1);
    }
  }

  prev() {
    // If more than 3s in, restart track; otherwise go to previous
    if (this.audio.currentTime > 3) {
      this.audio.currentTime = 0;
    } else if (this.currentIndex > 0) {
      this.play(this.currentIndex - 1);
    }
  }
}
