import { fetchSavedPlaylists } from '../services/api.js';

const tpl = document.createElement('template');
tpl.innerHTML = `
<style>
:host {
  display: block;
  padding: 24px;
  overflow-y: auto;
  height: 100%;
  min-height: 0;
}
:host(:not([active])) { display: none; }

.header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 20px;
}
.header h2 {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}
.count {
  font-size: 12px;
  color: var(--text-faint);
}

.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  padding-bottom: 120px;
}

.card {
  position: relative;
  display: flex;
  gap: 14px;
  padding: 14px;
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  cursor: pointer;
  transition: all var(--transition);
}
.card:hover {
  border-color: var(--accent);
  box-shadow: var(--shadow-sm);
}

.card-icon {
  width: 44px; height: 44px;
  border-radius: var(--radius);
  background: var(--accent-light);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.card-icon svg {
  width: 20px; height: 20px;
  stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
}

.card-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 2px;
}
.card-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-zone {
  font-size: 12px;
  color: var(--accent);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.card-meta {
  font-size: 11px;
  color: var(--text-faint);
}

.delete-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 24px; height: 24px;
  border: none;
  background: none;
  color: var(--text-faint);
  cursor: pointer;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: all var(--transition);
}
.card:hover .delete-btn { opacity: 1; }
.delete-btn:hover { color: #c44; background: rgba(204,68,68,0.08); }
.delete-btn svg {
  width: 14px; height: 14px;
  stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
}

.empty {
  text-align: center;
  padding: 80px 24px;
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
.empty h3 {
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

<div class="header">
  <h2>Playlists</h2>
  <span class="count" id="count"></span>
</div>
<div class="grid" id="grid"></div>
`;

const listSvg = `<svg viewBox="0 0 24 24"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>`;
const xSvg = `<svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`;

function relativeDate(isoStr) {
  if (!isoStr) return '';
  const d = new Date(isoStr + 'Z');
  const diff = Date.now() - d.getTime();
  const days = Math.floor(diff / 86400000);
  if (days < 1) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 7) return `${days}d ago`;
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

class PlaylistList extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
    this._playlists = [];
  }

  async refresh() {
    try {
      this._playlists = await fetchSavedPlaylists();
    } catch {
      this._playlists = [];
    }
    this._render();
  }

  _render() {
    const grid = this.shadowRoot.getElementById('grid');
    const count = this.shadowRoot.getElementById('count');
    grid.innerHTML = '';

    if (!this._playlists.length) {
      count.textContent = '';
      grid.innerHTML = `
        <div class="empty">
          <svg class="empty-icon" viewBox="0 0 24 24"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>
          <h3>No saved playlists</h3>
          <p>Generate a playlist from a zone on the Home screen,<br>then save it to find it here.</p>
        </div>`;
      return;
    }

    count.textContent = `${this._playlists.length} saved`;

    for (const pl of this._playlists) {
      const card = document.createElement('div');
      card.className = 'card';

      card.innerHTML = `
        <div class="card-icon">${listSvg}</div>
        <div class="card-info">
          <div class="card-name"></div>
          ${pl.zoneLabel ? `<div class="card-zone">${pl.zoneLabel}</div>` : ''}
          <div class="card-meta">${pl.trackCount} tracks \u2022 ${relativeDate(pl.createdAt)}</div>
        </div>
        <button class="delete-btn" title="Delete">${xSvg}</button>
      `;

      // Set name via textContent to escape HTML
      card.querySelector('.card-name').textContent = pl.name;

      // Card click → open playlist
      card.addEventListener('click', (e) => {
        if (e.target.closest('.delete-btn')) return;
        this.dispatchEvent(new CustomEvent('playlist-open', {
          bubbles: true, composed: true,
          detail: { id: pl.id },
        }));
      });

      // Delete click
      card.querySelector('.delete-btn').addEventListener('click', (e) => {
        e.stopPropagation();
        this.dispatchEvent(new CustomEvent('playlist-delete', {
          bubbles: true, composed: true,
          detail: { id: pl.id, name: pl.name },
        }));
      });

      grid.appendChild(card);
    }
  }
}

customElements.define('playlist-list', PlaylistList);
