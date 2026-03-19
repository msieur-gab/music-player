/**
 * Listener Gate — "Who's listening?" screen.
 * Shows on every app open (sessionStorage cleared on tab close).
 * One tap to select, then the gate disappears and the app loads.
 */

import { setActiveListener } from '../services/listener.js';

const tpl = document.createElement('template');
tpl.innerHTML = `
<style>
:host {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 500;
  background: var(--bg, #fafafa);
}
:host([open]) {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
}

.content {
  max-width: 360px;
  width: 100%;
  padding: 32px 24px;
  text-align: center;
}

h2 {
  font-size: 24px;
  font-weight: 700;
  color: var(--text, #1a1a1a);
  margin-bottom: 8px;
}

.sub {
  font-size: 14px;
  color: var(--text-muted, #666);
  margin-bottom: 32px;
}

.listeners {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 24px;
}

.listener-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid var(--border, #e0e0e0);
  border-radius: var(--radius, 8px);
  background: var(--bg-raised, #fff);
  color: var(--text, #1a1a1a);
  font-size: 15px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: all 150ms ease;
  text-align: left;
  width: 100%;
}
.listener-btn:hover {
  border-color: var(--accent, #f0802a);
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.listener-btn:active {
  transform: scale(0.98);
}

.listener-btn .avatar {
  width: 36px; height: 36px;
  border-radius: 50%;
  background: var(--accent-light, #fff3e8);
  color: var(--accent, #f0802a);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
}
.listener-btn.guest .avatar {
  background: var(--bg-hover, #f0f0f0);
  color: var(--text-faint, #999);
}

.listener-btn .name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.delete-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px; height: 28px;
  border: none;
  border-radius: 50%;
  background: none;
  color: var(--text-faint, #999);
  cursor: pointer;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 150ms ease, color 150ms ease, background 150ms ease;
}
.listener-btn:hover .delete-btn { opacity: 1; }
.delete-btn:hover {
  color: #c44;
  background: rgba(204,68,68,0.08);
}
.delete-btn svg {
  width: 14px; height: 14px;
  stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
}

.new-section {
  display: flex;
  gap: 8px;
  align-items: center;
}

.new-input {
  flex: 1;
  padding: 10px 14px;
  border: 1px solid var(--border, #e0e0e0);
  border-radius: var(--radius, 8px);
  background: var(--bg, #fafafa);
  color: var(--text, #1a1a1a);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: border-color 150ms ease;
}
.new-input:focus {
  border-color: var(--accent, #f0802a);
}
.new-input::placeholder {
  color: var(--text-faint, #999);
}

.new-btn {
  padding: 10px 18px;
  border: none;
  border-radius: var(--radius, 8px);
  background: var(--accent, #f0802a);
  color: var(--accent-text, #fff);
  font-size: 14px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  flex-shrink: 0;
  transition: opacity 150ms ease;
}
.new-btn:hover { opacity: 0.9; }
.new-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.error {
  font-size: 12px;
  color: #c44;
  margin-top: 8px;
  min-height: 16px;
}

.divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 20px 0 16px;
  color: var(--text-faint, #999);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.divider::before, .divider::after {
  content: '';
  flex: 1;
  height: 1px;
  background: var(--border, #e0e0e0);
}

.guest-btn {
  display: block;
  width: 100%;
  padding: 12px 16px;
  border: 1px dashed var(--border, #e0e0e0);
  border-radius: var(--radius, 8px);
  background: none;
  color: var(--text-muted, #666);
  font-size: 14px;
  font-family: inherit;
  cursor: pointer;
  transition: all 150ms ease;
  text-align: center;
}
.guest-btn:hover {
  border-color: var(--text-muted, #666);
  color: var(--text, #1a1a1a);
}
</style>

<div class="content">
  <h2>Who's listening?</h2>
  <div class="sub">Pick your name to get started</div>

  <div class="listeners" id="listeners"></div>

  <div class="new-section">
    <input class="new-input" id="new-name" type="text" placeholder="New listener..." maxlength="50" autocomplete="off">
    <button class="new-btn" id="new-btn">Add</button>
  </div>
  <div class="error" id="error"></div>

  <div class="divider">or</div>
  <button class="guest-btn" id="guest-btn">Continue as Guest</button>
</div>
`;

class ListenerGate extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
  }

  connectedCallback() {
    this.shadowRoot.getElementById('new-btn').addEventListener('click', () => this._createListener());
    this.shadowRoot.getElementById('new-name').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this._createListener();
    });
    this.shadowRoot.getElementById('guest-btn').addEventListener('click', () => {
      if (this._guest) this._select(this._guest);
    });
  }

  async show() {
    this.setAttribute('open', '');
    await this._loadListeners();
  }

  hide() {
    this.removeAttribute('open');
  }

  async _loadListeners() {
    const container = this.shadowRoot.getElementById('listeners');
    container.innerHTML = '';
    this._guest = null;

    try {
      const r = await fetch('/api/listeners');
      const listeners = await r.json();

      for (const l of listeners) {
        // Guest gets its own button at the bottom
        if (l.id === 'guest') {
          this._guest = l;
          continue;
        }
        const btn = document.createElement('button');
        btn.className = 'listener-btn';
        const initial = l.name.charAt(0).toUpperCase();
        btn.innerHTML = `
          <span class="avatar">${initial}</span>
          <span class="name">${this._esc(l.name)}</span>
          <span class="delete-btn" data-id="${l.id}" data-name="${this._esc(l.name)}">
            <svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </span>
        `;
        btn.addEventListener('click', (e) => {
          if (e.target.closest('.delete-btn')) return;
          this._select(l);
        });
        btn.querySelector('.delete-btn').addEventListener('click', (e) => {
          e.stopPropagation();
          this._deleteListener(l.id, l.name);
        });
        container.appendChild(btn);
      }
    } catch {
      container.innerHTML = '<div style="color:var(--text-faint);font-size:13px">Could not load listeners</div>';
    }
  }

  _select(listener) {
    setActiveListener(listener);
    this.hide();
    this.dispatchEvent(new CustomEvent('listener-selected', {
      bubbles: true, composed: true,
      detail: listener,
    }));
  }

  async _createListener() {
    const input = this.shadowRoot.getElementById('new-name');
    const error = this.shadowRoot.getElementById('error');
    const name = input.value.trim();

    if (!name) {
      error.textContent = 'Please enter a name';
      return;
    }

    const btn = this.shadowRoot.getElementById('new-btn');
    btn.disabled = true;
    error.textContent = '';

    try {
      const r = await fetch('/api/listeners', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
      });
      const result = await r.json();

      if (result.error) {
        error.textContent = result.error;
        btn.disabled = false;
        return;
      }

      input.value = '';
      this._select(result);
    } catch {
      error.textContent = 'Could not create listener';
    }
    btn.disabled = false;
  }

  async _deleteListener(id, name) {
    if (!confirm(`Delete "${name}"? Their favorites and playlists will be removed.`)) return;
    try {
      await fetch(`/api/listeners/${id}`, { method: 'DELETE' });
      await this._loadListeners();
    } catch { /* silent */ }
  }

  _esc(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }
}

customElements.define('listener-gate', ListenerGate);
