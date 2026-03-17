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
  from { transform: translateY(100%); }
  to { transform: translateY(0); }
}

.sheet {
  position: absolute;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  width: 320px;
  max-width: calc(100% - 32px);
  background: var(--bg-raised);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 16px;
  animation: slideUp 250ms cubic-bezier(0.32, 0.72, 0, 1);
}

h3 {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--text);
}

.devices {
  list-style: none;
  padding: 0;
}

.device {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 14px;
  color: var(--text);
  transition: background var(--transition);
}
.device:hover { background: var(--bg-hover); }
.device.active { color: var(--accent); }

.device svg {
  width: 20px; height: 20px;
  stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  flex-shrink: 0;
}

.device-name { flex: 1; }

.device-model {
  font-size: 11px;
  color: var(--text-faint);
}

.check {
  width: 18px; height: 18px;
  color: var(--accent);
  display: none;
}
.device.active .check { display: block; }

.empty {
  text-align: center;
  padding: 20px;
  color: var(--text-muted);
  font-size: 13px;
}

.scanning {
  font-size: 12px;
  color: var(--text-faint);
  text-align: center;
  margin-top: 8px;
}

.wifi-ip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-faint);
}
.wifi-ip button {
  border: none;
  background: none;
  color: var(--accent);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  padding: 0;
}
.wifi-ip button:hover { text-decoration: underline; }
</style>

<div class="scrim" id="scrim"></div>
<div class="sheet">
  <h3>Cast to</h3>
  <ul class="devices" id="devices"></ul>
  <div class="scanning">Devices are discovered automatically</div>
  <div class="wifi-ip" id="wifi-ip"></div>
</div>
`;

class DevicePicker extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
    this._devices = [];
  }

  connectedCallback() {
    this.shadowRoot.getElementById('scrim').addEventListener('click', () => {
      this.removeAttribute('open');
    });

    this.shadowRoot.getElementById('devices').addEventListener('click', (e) => {
      const li = e.target.closest('.device');
      if (!li) return;
      this.dispatchEvent(new CustomEvent('device-select', {
        bubbles: true, composed: true,
        detail: { id: li.dataset.id, name: li.dataset.name },
      }));
      this.removeAttribute('open');
    });
  }

  /** Auto-fetch devices when opened via attribute. */
  static get observedAttributes() { return ['open']; }

  attributeChangedCallback(name, oldVal, newVal) {
    if (name === 'open' && newVal !== null) {
      this._fetchDevices();
    }
  }

  async _fetchDevices() {
    try {
      const r = await fetch('/api/devices');
      this.devices = await r.json();
    } catch { /* addon API unavailable — list stays empty */ }
  }

  set devices(list) {
    this._devices = list || [];
    this._render();
    this._renderWifiIp();
  }

  _render() {
    const ul = this.shadowRoot.getElementById('devices');
    ul.innerHTML = '';

    if (!this._devices.length) {
      ul.innerHTML = '<li class="empty">No Chromecast devices found</li>';
      return;
    }

    // "This device" (local playback) option
    const local = document.createElement('li');
    local.className = 'device' + (this._devices.every(d => !d.is_active) ? ' active' : '');
    local.dataset.id = 'local';
    local.dataset.name = 'This device';
    local.innerHTML = `
      <svg viewBox="0 0 24 24">
        <rect x="4" y="2" width="16" height="16" rx="2"/>
        <path d="M2 20h20"/>
        <path d="M9 22v-2M15 22v-2"/>
      </svg>
      <span class="device-name">This device</span>
      <span class="device-model">Browser</span>
      <svg class="check" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
    `;
    ul.appendChild(local);

    for (const d of this._devices) {
      const li = document.createElement('li');
      li.className = 'device' + (d.is_active ? ' active' : '');
      li.dataset.id = d.id;
      li.dataset.name = d.name;

      li.innerHTML = `
        <svg viewBox="0 0 24 24">
          <path d="M2 16.1A5 5 0 0 1 5.9 20M2 12.05A9 9 0 0 1 9.95 20M2 8V6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-6"/>
          <line x1="2" y1="20" x2="2.01" y2="20"/>
        </svg>
        <span class="device-name">${d.name}</span>
        <span class="device-model">${d.model || ''}</span>
        <svg class="check" viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>
      `;
      ul.appendChild(li);
    }
  }

  _renderWifiIp() {
    const div = this.shadowRoot.getElementById('wifi-ip');
    const saved = localStorage.getItem('musicast-lan-ip');
    if (saved) {
      div.innerHTML = `WiFi IP: ${saved} <button id="change-ip">change</button>`;
      div.querySelector('#change-ip').addEventListener('click', () => {
        const ip = prompt('Enter your WiFi IP:', saved);
        if (ip && ip.trim()) {
          localStorage.setItem('musicast-lan-ip', ip.trim());
          this._renderWifiIp();
        }
      });
    } else {
      div.textContent = '';
    }
  }
}

customElements.define('device-picker', DevicePicker);
