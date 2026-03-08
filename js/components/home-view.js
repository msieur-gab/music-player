import { getRecentlyPlayed, getMostPlayed, getMostPlayedArtists } from '../services/stats.js';
import { fetchZones } from '../services/api.js';

const noteSvg = `<svg viewBox="0 0 24 24" style="width:24px;height:24px;stroke:currentColor;fill:none;stroke-width:1.5;stroke-linecap:round;stroke-linejoin:round;opacity:0.4"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`;

function relativeTime(ts) {
  const diff = Date.now() - ts;
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'Just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days}d ago`;
  return new Date(ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

const tpl = document.createElement('template');
tpl.innerHTML = `
<style>
:host {
  display: block;
  padding: 40px 40px 120px;
  overflow-y: auto;
  height: 100%;
  min-height: 0;
}
:host(:not([active])) { display: none; }

/* ── Greeting ── */
.greeting {
  margin-bottom: 40px;
}
.greeting h1 {
  font-size: 2rem;
  font-weight: 800;
  color: var(--text);
  line-height: 1.2;
  letter-spacing: -0.02em;
}
.greeting .name {
  color: var(--accent);
}
.greeting .sub {
  font-size: 14px;
  color: var(--text-faint);
  margin-top: 6px;
}

/* ── Sections ── */
.section {
  margin-bottom: 36px;
}
.section-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 14px;
}

/* ── Card row (horizontal scroll) ── */
.card-row {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  scroll-snap-type: x mandatory;
  scrollbar-width: none;
  padding-bottom: 4px;
}
.card-row::-webkit-scrollbar { display: none; }

/* ── Track card ── */
.track-card {
  flex: 0 0 200px;
  scroll-snap-align: start;
  display: flex;
  gap: 12px;
  padding: 10px;
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all var(--transition);
  min-width: 0;
}
.track-card:hover {
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.card-cover {
  width: 48px; height: 48px;
  border-radius: 6px;
  flex-shrink: 0;
  overflow: hidden;
  background: var(--bg-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-faint);
}
.card-cover img {
  width: 100%; height: 100%;
  object-fit: cover;
}

.card-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
}
.card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-sub {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-meta {
  font-size: 10px;
  color: var(--text-faint);
}

/* ── Artist card ── */
.artist-card {
  flex: 0 0 140px;
  scroll-snap-align: start;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 16px 12px;
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all var(--transition);
  text-align: center;
}
.artist-card:hover {
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
}
.artist-cover {
  width: 72px; height: 72px;
  border-radius: 50%;
  overflow: hidden;
  background: var(--bg-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-faint);
}
.artist-cover img {
  width: 100%; height: 100%;
  object-fit: cover;
}
.artist-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
.artist-plays {
  font-size: 11px;
  color: var(--text-faint);
}

/* ── Play count badge ── */
.play-count {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  color: var(--accent);
  font-weight: 600;
}
.play-count::before {
  content: '';
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--accent);
}

/* ── Zone tags ── */
.zone-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.zone-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid var(--border);
  border-radius: 20px;
  background: var(--bg-raised);
  color: var(--text);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition);
  white-space: nowrap;
}
.zone-tag:hover {
  border-color: var(--accent);
  background: var(--accent-light);
  color: var(--accent);
}
.zone-tag .count {
  font-size: 11px;
  color: var(--text-faint);
  font-weight: 400;
}
.zone-tag:hover .count { color: var(--accent); opacity: 0.7; }

/* ── Empty state ── */
.empty {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-faint);
}
.empty-icon {
  width: 48px; height: 48px;
  stroke: var(--text-faint);
  fill: none;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  margin-bottom: 16px;
}
.empty h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 8px;
}
.empty p {
  font-size: 13px;
  line-height: 1.5;
}
</style>

<div class="greeting" id="greeting"></div>
<div id="content"></div>
`;

class HomeView extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
  }

  connectedCallback() {
    this.refresh();
  }

  set userName(name) {
    this._userName = name;
    this._renderGreeting();
  }

  async refresh() {
    this._renderGreeting();

    const [recent, top, artists, zones] = await Promise.all([
      getRecentlyPlayed(8),
      getMostPlayed(8),
      getMostPlayedArtists(6),
      fetchZones().catch(() => []),
    ]);

    const content = this.shadowRoot.getElementById('content');
    let html = '';

    // Zone tags — split by group
    const activities = zones.filter(z => z.group === 'activity' && z.trackCount > 0);
    const moods = zones.filter(z => z.group === 'mood' && z.trackCount > 0);
    const support = zones.filter(z => z.group === 'support' && z.trackCount > 0);

    if (activities.length) {
      html += `<div class="section">
        <div class="section-label">What are you up to?</div>
        <div class="zone-row">${activities.map(z =>
          `<button class="zone-tag" data-zone="${z.id}">${z.label} <span class="count">${z.trackCount}</span></button>`
        ).join('')}</div>
      </div>`;
    }

    if (moods.length) {
      html += `<div class="section">
        <div class="section-label">How do you feel?</div>
        <div class="zone-row">${moods.map(z =>
          `<button class="zone-tag" data-zone="${z.id}">${z.label} <span class="count">${z.trackCount}</span></button>`
        ).join('')}</div>
      </div>`;
    }

    if (support.length) {
      html += `<div class="section">
        <div class="section-label">What do you need?</div>
        <div class="zone-row">${support.map(z =>
          `<button class="zone-tag" data-zone="${z.id}">${z.label} <span class="count">${z.trackCount}</span></button>`
        ).join('')}</div>
      </div>`;
    }

    if (!recent.length && !top.length && !activities.length && !moods.length && !support.length) {
      content.innerHTML = `
        <div class="empty">
          <svg class="empty-icon" viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
          <h2>Your music, your history</h2>
          <p>Play some tracks and your listening activity will appear here.</p>
        </div>`;
      return;
    }

    if (recent.length) {
      html += `<div class="section">
        <div class="section-label">Recently played</div>
        <div class="card-row">${recent.map(t => this._trackCard(t, relativeTime(t.lastPlayed))).join('')}</div>
      </div>`;
    }

    if (artists.length) {
      html += `<div class="section">
        <div class="section-label">Your top artists</div>
        <div class="card-row">${artists.map(a => this._artistCard(a)).join('')}</div>
      </div>`;
    }

    if (top.length) {
      html += `<div class="section">
        <div class="section-label">Most played</div>
        <div class="card-row">${top.map(t => this._trackCard(t, `${t.playCount} play${t.playCount > 1 ? 's' : ''}`)).join('')}</div>
      </div>`;
    }

    content.innerHTML = html;

    // Attach click handlers
    content.querySelectorAll('[data-artist][data-album]').forEach(card => {
      card.addEventListener('click', () => {
        this.dispatchEvent(new CustomEvent('navigate-album', {
          bubbles: true, composed: true,
          detail: { artist: card.dataset.artist, album: card.dataset.album },
        }));
      });
    });

    content.querySelectorAll('[data-artist]:not([data-album])').forEach(card => {
      card.addEventListener('click', () => {
        this.dispatchEvent(new CustomEvent('navigate-artist', {
          bubbles: true, composed: true,
          detail: { artist: card.dataset.artist },
        }));
      });
    });

    content.querySelectorAll('[data-zone]').forEach(tag => {
      tag.addEventListener('click', () => {
        this.dispatchEvent(new CustomEvent('open-zone', {
          bubbles: true, composed: true,
          detail: { zone: tag.dataset.zone },
        }));
      });
    });
  }

  _renderGreeting() {
    const h = new Date().getHours();
    const base = h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
    const name = this._userName || localStorage.getItem('musicast-username') || '';
    const greeting = this.shadowRoot.getElementById('greeting');

    if (name) {
      greeting.innerHTML = `<h1>${base}, <span class="name">${name}</span></h1>`;
    } else {
      greeting.innerHTML = `<h1>${base}</h1><div class="sub">Set your name in settings</div>`;
    }
  }

  _trackCard(track, meta) {
    const cover = track.cover
      ? `<img src="${track.cover}" alt="" loading="lazy">`
      : noteSvg;
    return `<div class="track-card" data-artist="${this._esc(track.artist)}" data-album="${this._esc(track.album)}">
      <div class="card-cover">${cover}</div>
      <div class="card-info">
        <div class="card-title">${this._esc(track.title)}</div>
        <div class="card-sub">${this._esc(track.artist)}</div>
        <div class="card-meta">${meta}</div>
      </div>
    </div>`;
  }

  _artistCard(artist) {
    const cover = artist.cover
      ? `<img src="${artist.cover}" alt="" loading="lazy">`
      : noteSvg;
    return `<div class="artist-card" data-artist="${this._esc(artist.artist)}">
      <div class="artist-cover">${cover}</div>
      <div class="artist-name">${this._esc(artist.artist)}</div>
      <div class="artist-plays"><span class="play-count">${artist.playCount} play${artist.playCount > 1 ? 's' : ''}</span></div>
    </div>`;
  }

  _esc(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }
}

customElements.define('home-view', HomeView);
