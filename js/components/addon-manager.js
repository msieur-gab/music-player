/**
 * <addon-manager> — standalone panel for discovering, installing, and
 * managing add-ons. Opens as a modal overlay.
 */

const tpl = document.createElement('template');
tpl.innerHTML = `
<style>
:host {
  display: none;
  position: fixed;
  inset: 0;
  z-index: 200;
}
:host([open]) { display: block; }

.scrim {
  position: absolute;
  inset: 0;
  background: rgba(0,0,0,0.4);
  animation: fadeIn 200ms ease;
}

@keyframes fadeIn { from { opacity: 0; } }
@keyframes slideUp {
  from { transform: translate(-50%, 20px); opacity: 0; }
  to   { transform: translate(-50%, 0);    opacity: 1; }
}

.sheet {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 440px;
  max-width: calc(100% - 32px);
  max-height: calc(100vh - 80px);
  overflow-y: auto;
  background: var(--bg-raised);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 24px;
  animation: slideUp 250ms cubic-bezier(0.32, 0.72, 0, 1);
  scrollbar-width: thin;
}

.header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 6px;
}
.header svg {
  width: 22px; height: 22px;
  stroke: var(--accent); fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
}
h3 {
  font-size: 16px;
  font-weight: 700;
  color: var(--text);
  margin: 0;
}
.subtitle {
  font-size: 12px;
  color: var(--text-faint);
  margin-bottom: 20px;
  line-height: 1.4;
}

/* ── Addon list ── */

.list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.loading {
  font-size: 12px;
  color: var(--text-faint);
  padding: 16px 0;
  text-align: center;
}

/* ── Addon card ── */

.card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  transition: border-color var(--transition);
}
.card.loaded    { border-left: 3px solid var(--accent); }
.card.available { border-left: 3px solid var(--text-muted, #6e6d6a); }
.card.not-installed { border-left: 3px solid var(--text-faint); }
.card.error     { border-left: 3px solid #c44; }

.card-icon {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: var(--bg-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--text-muted);
}
.card.loaded .card-icon {
  color: var(--accent);
  background: var(--accent-light);
}
.card-icon svg {
  width: 20px; height: 20px;
  stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
}

.card-body {
  flex: 1;
  min-width: 0;
}

.card-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.card-version {
  font-size: 11px;
  color: var(--text-faint);
  margin-left: 4px;
  font-weight: 400;
}

.card-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
  line-height: 1.3;
}

.card-status {
  font-size: 11px;
  margin-top: 4px;
  color: var(--text-faint);
}
.card-status.active { color: var(--accent); }
.card-status.err    { color: #c44; }

/* ── Action button ── */

.card-action {
  padding: 7px 16px;
  border: none;
  border-radius: var(--radius);
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  flex-shrink: 0;
  transition: opacity var(--transition);
  white-space: nowrap;
}
.card-action:hover { opacity: 0.9; }
.card-action:disabled { opacity: 0.5; cursor: default; }

.card-action.install {
  background: var(--accent);
  color: var(--accent-text);
}
.card-action.active-badge {
  background: var(--accent-light);
  color: var(--accent);
  cursor: default;
  font-weight: 500;
}
.card-action.error-badge {
  background: rgba(204,68,68,0.08);
  color: #c44;
  cursor: default;
  font-weight: 500;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
.spinner {
  display: inline-block;
  width: 12px; height: 12px;
  border: 2px solid var(--accent-text);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 800ms linear infinite;
  vertical-align: middle;
  margin-right: 4px;
}

@media (max-width: 480px) {
  .sheet { padding: 20px 16px; }
  .card { padding: 12px; }
}
</style>

<div class="scrim" id="scrim"></div>
<div class="sheet">
  <div class="header">
    <svg viewBox="0 0 24 24"><path d="M15.5 2.5a2.12 2.12 0 0 1 3 3L12 12l-4 1 1-4 6.5-6.5z"/><path d="M20 7v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7"/><path d="M9 22h6"/><path d="M2 12h4"/><path d="M18 12h4"/></svg>
    <h3>Add-ons</h3>
  </div>
  <div class="subtitle">Extend MusiCast with additional capabilities. Install add-ons to unlock new features.</div>
  <div class="list" id="list">
    <div class="loading">Loading add-ons...</div>
  </div>
</div>
`;

class AddonManager extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
  }

  connectedCallback() {
    this.shadowRoot.getElementById('scrim').addEventListener('click', () => {
      this.removeAttribute('open');
    });
  }

  static get observedAttributes() { return ['open']; }

  attributeChangedCallback(name, oldVal, newVal) {
    if (name === 'open' && newVal !== null) {
      this._load();
    }
  }

  async _load() {
    const list = this.shadowRoot.getElementById('list');
    list.innerHTML = '<div class="loading">Loading add-ons...</div>';

    try {
      const r = await fetch('/api/addons');
      const addons = await r.json();
      list.innerHTML = '';

      if (!addons.length) {
        list.innerHTML = '<div class="loading">No add-ons discovered</div>';
        return;
      }

      for (const addon of addons) {
        list.appendChild(this._card(addon));
      }
    } catch {
      list.innerHTML = '<div class="loading">Failed to load add-ons</div>';
    }
  }

  _card(addon) {
    const card = document.createElement('div');
    const statusClass = addon.status === 'missing_deps' ? 'not-installed' : addon.status;
    card.className = `card ${statusClass}`;
    card.dataset.id = addon.id;

    // Use addon-specific icon from trigger, or fallback to jigsaw
    const icon = addon.ui?.trigger?.icon
      || '<svg viewBox="0 0 24 24"><path d="M15.5 2.5a2.12 2.12 0 0 1 3 3L12 12l-4 1 1-4 6.5-6.5z"/><path d="M20 7v10a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7"/></svg>';

    let statusHtml = '';
    let actionHtml = '';

    if (addon.status === 'loaded') {
      statusHtml = '<div class="card-status active">Installed and active</div>';
      actionHtml = '<span class="card-action active-badge">Active</span>';
    } else if (addon.status === 'available') {
      statusHtml = '<div class="card-status">Ready to enable</div>';
      actionHtml = '<button class="card-action install">Enable</button>';
    } else if (addon.status === 'missing_deps') {
      const deps = (addon.missingDeps || []).join(', ');
      statusHtml = `<div class="card-status">Requires: ${deps}</div>`;
      actionHtml = '<button class="card-action install">Install</button>';
    } else if (addon.status === 'error') {
      statusHtml = `<div class="card-status err">${this._esc(addon.error || 'Load error')}</div>`;
      actionHtml = '<span class="card-action error-badge">Error</span>';
    }

    card.innerHTML = `
      <div class="card-icon">${icon}</div>
      <div class="card-body">
        <div class="card-name">${this._esc(addon.name)}<span class="card-version">v${addon.version || '?'}</span></div>
        <div class="card-desc">${this._esc(addon.description || '')}</div>
        ${statusHtml}
      </div>
      ${actionHtml}
    `;

    const installBtn = card.querySelector('.card-action.install');
    if (installBtn) {
      installBtn.addEventListener('click', () => this._install(addon.id, card));
    }

    return card;
  }

  async _install(addonId, card) {
    const btn = card.querySelector('.card-action.install');
    const status = card.querySelector('.card-status');
    if (!btn) return;

    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span>Installing';
    status.textContent = 'Installing dependencies...';
    status.className = 'card-status';

    try {
      const r = await fetch('/api/addons/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: addonId }),
      });
      const result = await r.json();

      if (result.ok) {
        // Refresh the list to show updated state
        await this._load();

        // Tell the app to discover the new addon's UI
        this.dispatchEvent(new CustomEvent('addon-installed', {
          bubbles: true, composed: true,
          detail: { id: addonId },
        }));
      } else {
        status.textContent = result.error || 'Install failed';
        status.className = 'card-status err';
        btn.disabled = false;
        btn.textContent = 'Retry';
      }
    } catch (e) {
      status.textContent = `Error: ${e.message}`;
      status.className = 'card-status err';
      btn.disabled = false;
      btn.textContent = 'Retry';
    }
  }

  _esc(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }
}

customElements.define('addon-manager', AddonManager);
