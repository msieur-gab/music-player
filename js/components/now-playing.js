const tpl = document.createElement('template');
tpl.innerHTML = `
<style>
:host {
  display: block;
  position: fixed;
  bottom: 24px;
  left: calc(var(--rail-w, 56px) + 24px);
  right: 24px;
  z-index: 100;
  transform: translateY(calc(100% + 48px));
  transition: transform 300ms cubic-bezier(0.32, 0.72, 0, 1);
  pointer-events: none;
}
:host([visible]) {
  transform: translateY(0);
  pointer-events: auto;
}

.bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  background: var(--player-bg);
  color: var(--player-text);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0,0,0,0.35), 0 2px 8px rgba(0,0,0,0.2);
  max-width: 840px;
  margin: 0 auto;
}

.art {
  width: 48px; height: 48px;
  border-radius: 6px;
  object-fit: cover;
  flex-shrink: 0;
  background: #2a2a2a;
}
.art[hidden] { display: none; }

.art-ph {
  width: 48px; height: 48px;
  border-radius: 6px;
  background: #2a2a2a;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #555;
}
.art-ph[hidden] { display: none; }
.art-ph svg {
  width: 24px; height: 24px;
  stroke: currentColor; fill: none;
  stroke-width: 1.5;
}

.info {
  flex: 1;
  min-width: 0;
}
.info-title {
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.info-artist {
  font-size: 12px;
  color: var(--player-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-top: 1px;
}

.controls {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.ctrl-btn {
  width: 40px; height: 40px;
  border: none;
  background: none;
  color: var(--player-text);
  cursor: pointer;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background var(--transition);
}
.ctrl-btn:hover { background: rgba(255,255,255,0.08); }
.ctrl-btn svg {
  width: 20px; height: 20px;
  fill: currentColor; stroke: none;
}
.ctrl-btn.play-btn {
  width: 44px; height: 44px;
  background: var(--player-accent);
  color: #000;
}
.ctrl-btn.play-btn:hover { opacity: 0.9; background: var(--player-accent); }
.ctrl-btn.play-btn svg { width: 22px; height: 22px; }

.progress {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  max-width: 400px;
}
.progress time {
  font-size: 11px;
  color: var(--player-muted);
  min-width: 3.5em;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.seek {
  flex: 1;
  -webkit-appearance: none;
  appearance: none;
  height: 4px;
  background: rgba(255,255,255,0.15);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}
.seek::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 12px; height: 12px;
  border-radius: 50%;
  background: var(--player-accent);
  cursor: pointer;
}

.volume {
  width: 80px;
  -webkit-appearance: none;
  appearance: none;
  height: 4px;
  background: rgba(255,255,255,0.15);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}
.volume::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 10px; height: 10px;
  border-radius: 50%;
  background: var(--player-text);
  cursor: pointer;
}

.device-btn {
  width: 36px; height: 36px;
  border: none;
  background: none;
  color: var(--player-muted);
  cursor: pointer;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: color var(--transition);
}
.device-btn:hover { color: var(--player-text); }
.device-btn.active { color: var(--player-accent); }
.device-btn svg {
  width: 18px; height: 18px;
  stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
}

.now-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  cursor: pointer;
  border-radius: 8px;
  padding: 4px;
  margin: -4px;
  transition: background var(--transition);
}
.now-meta:hover { background: rgba(255,255,255,0.06); }

</style>

<div class="bar">
  <div class="now-meta" id="now-meta">
    <img class="art" id="art" hidden>
    <div class="art-ph" id="art-ph">
      <svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
    </div>

    <div class="info">
      <div class="info-title" id="title">--</div>
      <div class="info-artist" id="artist"></div>
    </div>
  </div>

  <div class="controls">
    <button class="ctrl-btn" id="prev" title="Previous">
      <svg viewBox="0 0 24 24"><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5" stroke="currentColor" stroke-width="2" fill="none"/></svg>
    </button>
    <button class="ctrl-btn play-btn" id="play" title="Play">
      <svg viewBox="0 0 24 24" id="play-icon"><polygon points="5 3 19 12 5 21 5 3"/></svg>
    </button>
    <button class="ctrl-btn" id="next" title="Next">
      <svg viewBox="0 0 24 24"><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19" stroke="currentColor" stroke-width="2" fill="none"/></svg>
    </button>
  </div>

  <div class="progress">
    <time id="current">0:00</time>
    <input type="range" class="seek" id="seek" min="0" max="100" value="0" step="0.1">
    <time id="duration">0:00</time>
  </div>

  <input type="range" class="volume" id="volume" min="0" max="1" value="1" step="0.01" title="Volume">

  <button class="device-btn" id="device-btn" title="Cast to speaker">
    <svg viewBox="0 0 24 24">
      <path d="M2 16.1A5 5 0 0 1 5.9 20M2 12.05A9 9 0 0 1 9.95 20M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6"/>
      <line x1="2" y1="20" x2="2.01" y2="20"/>
    </svg>
  </button>
</div>
`;

class NowPlaying extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
    this._playing = false;
    this._seeking = false;
    this._adjustingVolume = false;
  }

  connectedCallback() {
    const $ = id => this.shadowRoot.getElementById(id);

    const emit = (type, value) => {
      this.dispatchEvent(new CustomEvent('control', {
        bubbles: true, composed: true,
        detail: { type, value },
      }));
    };

    $('play').addEventListener('click', () => emit('toggle'));
    $('next').addEventListener('click', () => emit('next'));
    $('prev').addEventListener('click', () => emit('prev'));

    $('seek').addEventListener('mousedown', () => { this._seeking = true; });
    $('seek').addEventListener('touchstart', () => { this._seeking = true; }, { passive: true });
    $('seek').addEventListener('change', () => {
      const pct = parseFloat($('seek').value);
      const dur = this._duration || 0;
      if (dur) emit('seek', (pct / 100) * dur);
      this._seeking = false;
    });

    $('volume').addEventListener('mousedown', () => { this._adjustingVolume = true; });
    $('volume').addEventListener('touchstart', () => { this._adjustingVolume = true; }, { passive: true });
    $('volume').addEventListener('input', () => {
      emit('volume', parseFloat($('volume').value));
    });
    $('volume').addEventListener('change', () => { this._adjustingVolume = false; });
    $('volume').addEventListener('mouseup', () => { this._adjustingVolume = false; });
    $('volume').addEventListener('touchend', () => { this._adjustingVolume = false; });

    $('device-btn').addEventListener('click', () => {
      this.dispatchEvent(new CustomEvent('toggle-devices', { bubbles: true, composed: true }));
    });

    $('now-meta').addEventListener('click', () => {
      if (this._currentArtist && this._currentAlbum) {
        this.dispatchEvent(new CustomEvent('navigate-to-album', {
          bubbles: true, composed: true,
          detail: { artist: this._currentArtist, album: this._currentAlbum },
        }));
      }
    });
  }

  update(status) {
    if (!status || status.state === 'idle') {
      this.removeAttribute('visible');
      return;
    }

    this.setAttribute('visible', '');
    const $ = id => this.shadowRoot.getElementById(id);

    this._currentArtist = status.artist || '';
    this._currentAlbum = status.album || '';

    $('title').textContent = status.title || '--';
    $('artist').textContent = status.artist || '';

    if (status.cover) {
      $('art').src = status.cover;
      $('art').hidden = false;
      $('art-ph').hidden = true;
    } else {
      $('art').hidden = true;
      $('art-ph').hidden = false;
    }

    this._playing = status.state === 'playing';
    $('play-icon').innerHTML = this._playing
      ? '<rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/>'
      : '<polygon points="5 3 19 12 5 21 5 3"/>';

    this._duration = status.duration || 0;
    if (!this._seeking && this._duration) {
      $('seek').value = (status.currentTime / this._duration) * 100;
    }
    $('current').textContent = this._fmt(status.currentTime || 0);
    $('duration').textContent = this._fmt(this._duration);

    if (!this._adjustingVolume && status.volume != null) {
      $('volume').value = status.volume;
    }

    const deviceBtn = $('device-btn');
    deviceBtn.classList.toggle('active', !!status.device);
  }

  _fmt(s) {
    if (!s || !isFinite(s)) return '0:00';
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, '0')}`;
  }
}

customElements.define('now-playing', NowPlaying);
