const tpl = document.createElement('template');
tpl.innerHTML = `
<style>
:host {
  display: flex;
  flex-direction: column;
  background: var(--bg-raised);
  border-right: 1px solid var(--border);
  padding: 12px 0;
  gap: 2px;
  align-items: center;
  user-select: none;
  overflow: hidden;
}

.logo {
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius);
  background: var(--accent);
  color: var(--accent-text);
  margin-bottom: 12px;
  cursor: default;
}
.logo svg {
  width: 20px; height: 20px;
  fill: currentColor; stroke: none;
}

button {
  position: relative;
  width: 40px; height: 40px;
  border: none;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  border-radius: var(--radius);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition);
}
button:hover { color: var(--text); background: var(--bg-hover); }
button[aria-selected="true"] {
  color: var(--accent);
  background: var(--accent-light);
}
button[aria-selected="true"]::after {
  content: '';
  position: absolute;
  right: -8px;
  top: 8px;
  bottom: 8px;
  width: 3px;
  background: var(--accent);
  border-radius: 3px;
}

button svg {
  width: 20px; height: 20px;
  stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
}

.badge {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--accent);
  display: none;
}
button.has-badge .badge { display: block; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
button.has-badge .badge { animation: pulse 1.8s ease-in-out infinite; }

.spacer { flex: 1; }

.divider {
  width: 24px;
  height: 1px;
  background: var(--border);
  margin: 4px 0;
}
</style>

<div class="logo">
  <svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>
</div>

<button data-tab="home" aria-selected="true" title="Home">
  <svg viewBox="0 0 24 24"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>
</button>

<button data-tab="library" title="Library">
  <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="3"/></svg>
</button>

<span class="spacer"></span>

<button data-action="download" id="dl-btn" title="Download music">
  <svg viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
  <span class="badge"></span>
</button>

<div class="divider"></div>

<button data-action="settings" title="Settings">
  <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
</button>

<button data-action="theme" title="Toggle theme">
  <svg viewBox="0 0 24 24" id="theme-icon"><circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/></svg>
</button>
`;

class NavRail extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
    this._active = 'home';
  }

  connectedCallback() {
    this.shadowRoot.addEventListener('click', (e) => {
      const btn = e.target.closest('button');
      if (!btn) return;

      const tab = btn.dataset.tab;
      const action = btn.dataset.action;

      if (tab) {
        this.active = tab;
        this.dispatchEvent(new CustomEvent('rail-navigate', {
          bubbles: true, composed: true,
          detail: { tab },
        }));
      } else if (action) {
        this.dispatchEvent(new CustomEvent('rail-action', {
          bubbles: true, composed: true,
          detail: { action },
        }));
      }
    });
  }

  get active() { return this._active; }

  set active(tab) {
    this._active = tab;
    this.shadowRoot.querySelectorAll('button[data-tab]').forEach(btn => {
      btn.setAttribute('aria-selected', btn.dataset.tab === tab ? 'true' : 'false');
    });
  }

  set downloadActive(active) {
    const btn = this.shadowRoot.getElementById('dl-btn');
    btn.classList.toggle('has-badge', active);
  }

  updateThemeIcon(isDark) {
    const icon = this.shadowRoot.getElementById('theme-icon');
    if (isDark) {
      icon.innerHTML = '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>';
    } else {
      icon.innerHTML = '<circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>';
    }
  }
}

customElements.define('nav-rail', NavRail);
