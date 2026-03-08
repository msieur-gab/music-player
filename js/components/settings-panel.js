import { fetchConfig, updateConfig, browseFolders, startAnalysis, streamAnalysis } from '../services/api.js';

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
  to { transform: translate(-50%, 0); opacity: 1; }
}

.sheet {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 400px;
  max-width: calc(100% - 32px);
  max-height: calc(100vh - 120px);
  overflow-y: auto;
  background: var(--bg-raised);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
  padding: 24px;
  animation: slideUp 250ms cubic-bezier(0.32, 0.72, 0, 1);
}

h3 {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 20px;
  color: var(--text);
}

.field {
  margin-bottom: 16px;
}

.field label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-bottom: 6px;
}

.field input {
  width: 100%;
  min-width: 0;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--text);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  text-overflow: ellipsis;
  overflow: hidden;
  transition: border-color var(--transition);
  box-sizing: border-box;
}
.field input:focus {
  border-color: var(--accent);
  text-overflow: clip;
}

.field .hint {
  font-size: 11px;
  color: var(--text-faint);
  margin-top: 4px;
  line-height: 1.4;
}

.field-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  min-width: 0;
}
.field-row input { flex: 1; min-width: 0; }

.save-btn {
  padding: 6px 14px;
  border: none;
  border-radius: var(--radius);
  background: var(--accent);
  color: var(--accent-text);
  font-size: 13px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  flex-shrink: 0;
  transition: opacity var(--transition);
}
.save-btn:hover { opacity: 0.9; }

.section {
  padding-top: 16px;
  margin-top: 16px;
  border-top: 1px solid var(--border);
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  margin-bottom: 12px;
}

.status {
  font-size: 12px;
  color: var(--accent);
  margin-top: 4px;
  min-height: 16px;
}

/* ── Folder browser ── */

.browse-btn {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--text-muted);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  flex-shrink: 0;
  transition: all var(--transition);
}
.browse-btn:hover { color: var(--text); border-color: var(--text-muted); }

.browser {
  display: none;
  margin-top: 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  overflow: hidden;
}
.browser[open] { display: block; }

.browser-path {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 8px 10px;
  background: var(--bg-hover);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  overflow: hidden;
  white-space: nowrap;
  direction: rtl;
  text-align: left;
}
.browser-path span {
  direction: ltr;
  unicode-bidi: bidi-override;
}

.browser-list {
  max-height: 200px;
  overflow-y: auto;
  scrollbar-width: thin;
}

.browser-list .dir {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  transition: background var(--transition);
  border: none;
  background: none;
  width: 100%;
  text-align: left;
  font-family: inherit;
}
.dir:hover { background: var(--bg-hover); }
.dir.parent { color: var(--text-muted); font-style: italic; }

.dir-icon {
  width: 16px;
  height: 16px;
  flex-shrink: 0;
  stroke: var(--accent);
  fill: none;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.dir.parent .dir-icon { stroke: var(--text-muted); }

.dir-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.browser-actions {
  display: flex;
  gap: 8px;
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  justify-content: flex-end;
}

.browser-select {
  padding: 5px 12px;
  border: none;
  border-radius: var(--radius);
  background: var(--accent);
  color: var(--accent-text);
  font-size: 12px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: opacity var(--transition);
}
.browser-select:hover { opacity: 0.9; }

.browser-cancel {
  padding: 5px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: none;
  color: var(--text-muted);
  font-size: 12px;
  font-family: inherit;
  cursor: pointer;
  transition: all var(--transition);
}
.browser-cancel:hover { color: var(--text); border-color: var(--text-muted); }

.browser-empty {
  padding: 16px 10px;
  font-size: 12px;
  color: var(--text-faint);
  text-align: center;
}

.browser-error {
  padding: 8px 10px;
  font-size: 12px;
  color: #c44;
  background: rgba(204,68,68,0.06);
}

.analyze-progress {
  margin-top: 8px;
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.5;
}
.analyze-progress:empty { display: none; }
.analyze-progress .done { color: var(--accent); font-weight: 600; }

@media (max-width: 480px) {
  .sheet { padding: 20px 16px; }
}
</style>

<div class="scrim" id="scrim"></div>
<div class="sheet">
  <h3>Settings</h3>

  <div class="field">
    <label>Your name</label>
    <input type="text" id="username" placeholder="How should we greet you?" autocomplete="off">
  </div>

  <div class="section">
    <div class="section-title">Music library</div>
    <div class="field">
      <label>Music folder</label>
      <div class="field-row">
        <input type="text" id="music-dir" placeholder="/path/to/music" autocomplete="off">
        <button class="browse-btn" id="browse-btn">Browse</button>
        <button class="save-btn" id="save-dir">Save</button>
      </div>
      <div class="hint">Where music files are stored and downloads are saved.</div>
      <div class="status" id="dir-status"></div>

      <div class="browser" id="browser">
        <div class="browser-path"><span id="browser-current"></span></div>
        <div class="browser-list" id="browser-list"></div>
        <div class="browser-actions">
          <button class="browser-cancel" id="browser-cancel">Cancel</button>
          <button class="browser-select" id="browser-use">Use this folder</button>
        </div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Network</div>
    <div class="field">
      <label>Server IP (detected)</label>
      <input type="text" id="lan-ip" readonly>
      <div class="hint">Auto-detected. Used by Chromecasts to stream audio from this server.</div>
    </div>
    <div class="field">
      <label>WiFi IP override</label>
      <div class="field-row">
        <input type="text" id="wifi-ip" placeholder="e.g. 192.168.86.32" autocomplete="off">
        <button class="save-btn" id="save-ip">Save</button>
      </div>
      <div class="hint">Only needed on Chromebooks (Crostini). Leave empty on Mac/Linux.</div>
      <div class="status" id="ip-status"></div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Audio analysis</div>
    <div class="field">
      <div class="hint" style="margin-bottom:8px">Scan your library to extract audio features. This enables "sounds like" recommendations based on how tracks actually sound — no genre tags needed.</div>
      <button class="save-btn" id="analyze-btn" style="width:100%">Analyze library</button>
      <div class="analyze-progress" id="analyze-progress"></div>
    </div>
  </div>
</div>
`;

const folderSvg = `<svg class="dir-icon" viewBox="0 0 24 24"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>`;
const upSvg = `<svg class="dir-icon" viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>`;

class SettingsPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
    this._browsePath = '';
  }

  connectedCallback() {
    const $ = id => this.shadowRoot.getElementById(id);

    $('scrim').addEventListener('click', () => this.removeAttribute('open'));

    // ── Username — save on blur or Enter ──
    $('username').value = localStorage.getItem('musicast-username') || '';
    const saveName = () => {
      const name = $('username').value.trim();
      localStorage.setItem('musicast-username', name);
      this.dispatchEvent(new CustomEvent('username-change', {
        bubbles: true, composed: true,
        detail: { name },
      }));
    };
    $('username').addEventListener('change', saveName);
    $('username').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') { e.preventDefault(); saveName(); }
    });

    // ── WiFi IP ──
    $('wifi-ip').value = localStorage.getItem('musicast-lan-ip') || '';
    $('save-ip').addEventListener('click', () => {
      const ip = $('wifi-ip').value.trim();
      if (ip) {
        localStorage.setItem('musicast-lan-ip', ip);
      } else {
        localStorage.removeItem('musicast-lan-ip');
      }
      $('ip-status').textContent = ip ? `Saved: ${ip}` : 'Cleared — will auto-detect';
      this.dispatchEvent(new CustomEvent('ip-change', {
        bubbles: true, composed: true,
        detail: { ip },
      }));
      setTimeout(() => { $('ip-status').textContent = ''; }, 2000);
    });

    // ── Music dir — save to server ──
    $('save-dir').addEventListener('click', () => this._saveDir());

    // ── Folder browser ──
    $('browse-btn').addEventListener('click', async () => {
      const browser = $('browser');
      if (browser.hasAttribute('open')) {
        browser.removeAttribute('open');
        return;
      }
      // Start browsing from the current music dir value or home
      const startPath = $('music-dir').value.trim() || '';
      await this._browse(startPath);
      browser.setAttribute('open', '');
    });

    $('browser-cancel').addEventListener('click', () => {
      $('browser').removeAttribute('open');
    });

    $('browser-use').addEventListener('click', () => {
      $('music-dir').value = this._browsePath;
      $('browser').removeAttribute('open');
      this._saveDir();
    });

    $('analyze-btn').addEventListener('click', () => this._startAnalysis());
  }

  async _browse(path) {
    const $ = id => this.shadowRoot.getElementById(id);
    try {
      const result = await browseFolders(path);
      this._browsePath = result.current;
      $('browser-current').textContent = result.current;

      const list = $('browser-list');
      list.innerHTML = '';

      if (result.error) {
        list.innerHTML = `<div class="browser-error">${result.error}</div>`;
      }

      if (result.dirs.length === 0 && !result.error) {
        list.innerHTML = '<div class="browser-empty">No subfolders</div>';
        return;
      }

      for (const dir of result.dirs) {
        const isParent = dir.name === '..';
        const btn = document.createElement('button');
        btn.className = `dir${isParent ? ' parent' : ''}`;
        btn.innerHTML = `${isParent ? upSvg : folderSvg}<span class="dir-name">${isParent ? 'Parent folder' : dir.name}</span>`;
        btn.addEventListener('click', () => this._browse(dir.path));
        list.appendChild(btn);
      }
    } catch (e) {
      const list = $('browser-list');
      list.innerHTML = '<div class="browser-error">Failed to load folders</div>';
    }
  }

  async _saveDir() {
    const $ = id => this.shadowRoot.getElementById(id);
    const dir = $('music-dir').value.trim();
    if (!dir) return;
    $('dir-status').textContent = 'Saving...';
    try {
      const result = await updateConfig({ musicDir: dir });
      if (result.error) {
        $('dir-status').textContent = result.error;
      } else {
        $('dir-status').textContent = 'Saved — library will reload';
        this.dispatchEvent(new CustomEvent('musicdir-change', {
          bubbles: true, composed: true,
        }));
        setTimeout(() => { $('dir-status').textContent = ''; }, 2000);
      }
    } catch {
      $('dir-status').textContent = 'Failed to save';
    }
  }

  async _startAnalysis() {
    const $ = id => this.shadowRoot.getElementById(id);
    const btn = $('analyze-btn');
    const progress = $('analyze-progress');

    btn.disabled = true;
    btn.textContent = 'Analyzing...';
    progress.innerHTML = 'Starting analysis...';

    try {
      const { id } = await startAnalysis();
      const source = streamAnalysis(id);

      source.addEventListener('message', (e) => {
        try {
          const data = JSON.parse(e.data);

          if (data.status === 'complete') {
            source.close();
            progress.innerHTML = `<span class="done">${data.message}</span>`;
            btn.disabled = false;
            btn.textContent = 'Analyze library';
          } else if (data.status === 'error') {
            source.close();
            progress.textContent = data.message || 'Analysis failed';
            btn.disabled = false;
            btn.textContent = 'Analyze library';
          } else {
            progress.textContent = data.message;
          }
        } catch {
          progress.textContent = e.data;
        }
      });

      source.addEventListener('error', () => {
        source.close();
        progress.textContent = 'Connection lost';
        btn.disabled = false;
        btn.textContent = 'Analyze library';
      });
    } catch (err) {
      progress.textContent = `Failed: ${err.message}`;
      btn.disabled = false;
      btn.textContent = 'Analyze library';
    }
  }

  async load() {
    const $ = id => this.shadowRoot.getElementById(id);
    $('username').value = localStorage.getItem('musicast-username') || '';
    $('wifi-ip').value = localStorage.getItem('musicast-lan-ip') || '';
    try {
      const cfg = await fetchConfig();
      $('music-dir').value = cfg.musicDir || '';
      $('lan-ip').value = cfg.lanIp || '';
    } catch { /* silent */ }
  }
}

customElements.define('settings-panel', SettingsPanel);
