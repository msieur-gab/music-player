// Self-contained API calls — no dependency on main app's api.js
async function startDownload(url) {
  const r = await fetch('/api/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  return r.json();
}

function streamJob(id) {
  return new EventSource(`/api/download/${id}`);
}

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
  width: 480px;
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

h3 {
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 6px;
  color: var(--text);
}
.subtitle {
  font-size: 12px;
  color: var(--text-faint);
  margin-bottom: 20px;
  line-height: 1.4;
}

/* ── URL input ── */
.form {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.input {
  flex: 1;
  min-width: 0;
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--text);
  font-size: 13px;
  font-family: inherit;
  outline: none;
  transition: border-color var(--transition);
  text-overflow: ellipsis;
}
.input:focus { border-color: var(--accent); }
.input::placeholder { color: var(--text-faint); }

.submit {
  padding: 9px 18px;
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
.submit:hover { opacity: 0.9; }
.submit:disabled { opacity: 0.5; cursor: default; }

/* ── Download jobs ── */
.jobs { display: flex; flex-direction: column; gap: 16px; }
.jobs:empty { display: none; }

.job {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  background: var(--bg);
}

/* ── Job header ── */
.job-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
}
.job-icon {
  width: 36px; height: 36px;
  border-radius: 6px;
  background: var(--bg-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--text-faint);
}
.job-icon svg {
  width: 18px; height: 18px;
  stroke: currentColor; fill: none;
  stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round;
}
.job-icon.active { color: var(--accent); }
.job-icon.done { color: var(--accent); background: var(--accent-light); }
.job-icon.error { color: #c44; background: rgba(204,68,68,0.06); }

.job-meta {
  flex: 1;
  min-width: 0;
}
.job-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.job-sub {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 1px;
}

.job-dismiss {
  width: 28px; height: 28px;
  border: none;
  background: none;
  color: var(--text-faint);
  cursor: pointer;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all var(--transition);
}
.job-dismiss:hover { color: var(--text); background: var(--bg-hover); }
.job-dismiss svg {
  width: 14px; height: 14px;
  stroke: currentColor; fill: none;
  stroke-width: 2; stroke-linecap: round;
}

/* ── Progress bar ── */
.job-progress {
  padding: 0 14px;
}
.progress-bar {
  height: 4px;
  background: var(--bg-hover);
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 300ms ease;
  width: 0%;
}
.progress-text {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 6px;
  padding-bottom: 10px;
}

/* ── Track list ── */
.job-tracks {
  max-height: 200px;
  overflow-y: auto;
  scrollbar-width: thin;
  border-top: 1px solid var(--border);
}
.job-tracks:empty { display: none; }

.track {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 14px;
  font-size: 12px;
}
.track + .track { border-top: 1px solid var(--border); }

.track-num {
  width: 20px;
  text-align: right;
  color: var(--text-faint);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}
.track-name {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text);
}
.track-status {
  flex-shrink: 0;
  width: 18px; height: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.track-status svg {
  width: 14px; height: 14px;
  stroke-width: 2; stroke-linecap: round; stroke-linejoin: round;
  fill: none;
}

/* Status icons */
.st-waiting { color: var(--text-faint); }
.st-downloading { color: var(--accent); }
.st-done { color: var(--accent); }
.st-skipped { color: var(--text-faint); }
.st-error { color: #c44; }

@keyframes spin {
  to { transform: rotate(360deg); }
}
.spinner {
  width: 14px; height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 800ms linear infinite;
}

/* ── Empty state ── */
.empty {
  text-align: center;
  padding: 32px 16px;
  color: var(--text-faint);
  font-size: 13px;
  line-height: 1.5;
}
.empty svg {
  width: 36px; height: 36px;
  stroke: var(--text-faint);
  fill: none;
  stroke-width: 1.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  margin-bottom: 12px;
  opacity: 0.5;
}
</style>

<div class="scrim" id="scrim"></div>
<div class="sheet">
  <h3>Download music</h3>
  <div class="subtitle">Paste a YouTube Music album or playlist URL to add it to your library.</div>

  <form class="form" id="form">
    <input class="input" id="url" type="url" placeholder="https://music.youtube.com/playlist?list=..." autocomplete="off" required>
    <button class="submit" type="submit" id="submit-btn">Download</button>
  </form>

  <div class="jobs" id="jobs"></div>
</div>
`;

/* Icon fragments */
const icons = {
  note: `<svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`,
  check: `<svg viewBox="0 0 24 24" stroke="currentColor"><polyline points="20 6 9 17 4 12"/></svg>`,
  x: `<svg viewBox="0 0 24 24" stroke="currentColor"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
  skip: `<svg viewBox="0 0 24 24" stroke="currentColor"><line x1="5" y1="12" x2="19" y2="12"/></svg>`,
  alert: `<svg viewBox="0 0 24 24" stroke="currentColor"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  dismiss: `<svg viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>`,
};

class DownloadPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
    this._activeJobs = new Map(); // jobId → { el, source, state }
  }

  connectedCallback() {
    const $ = id => this.shadowRoot.getElementById(id);

    $('scrim').addEventListener('click', () => {
      this.removeAttribute('open');
    });

    $('form').addEventListener('submit', (e) => {
      e.preventDefault();
      const input = $('url');
      const url = input.value.trim();
      if (url) {
        input.value = '';
        this._start(url);
      }
    });
  }

  async _start(url) {
    const jobEl = this._createJobEl(url);
    this.shadowRoot.getElementById('jobs').prepend(jobEl);

    try {
      const { id } = await startDownload(url);
      const state = {
        el: jobEl,
        id,
        done: false,
        total: 0,
        completed: 0,
        artist: '',
        album: '',
        tracks: new Map(),
      };
      this._activeJobs.set(id, state);
      this._emitActivity(true);
      this._follow(id, state);
    } catch (err) {
      this._setJobError(jobEl, `Failed to start: ${err.message}`);
    }
  }

  _createJobEl(url) {
    const el = document.createElement('div');
    el.className = 'job';
    el.innerHTML = `
      <div class="job-header">
        <div class="job-icon active">${icons.note}</div>
        <div class="job-meta">
          <div class="job-title">Preparing download...</div>
          <div class="job-sub">Extracting playlist info</div>
        </div>
      </div>
    `;
    return el;
  }

  _follow(id, state) {
    const source = streamJob(id);
    state.source = source;

    source.addEventListener('message', (e) => {
      try {
        const data = JSON.parse(e.data);
        this._handleEvent(state, data);
      } catch {
        // raw text fallback
        this._updateJobSub(state.el, e.data);
      }
    });

    source.addEventListener('error', () => {
      source.close();
      if (!state.done) {
        this._setJobError(state.el, 'Connection lost — download may still be running on server');
        state.done = true;
      }
    });
  }

  _handleEvent(state, data) {
    const el = state.el;

    // Metadata discovered (has artist + album + total)
    if (data.artist && data.album && data.total && !state.total) {
      state.artist = data.artist;
      state.album = data.album;
      state.total = data.total;
      this._updateJobTitle(el, `${data.artist} — ${data.album}`);
      this._updateJobSub(el, `${data.total} tracks found`);
      this._addProgressBar(el, state);
      this._addTrackList(el, state);
      return;
    }

    // Per-track progress
    if (data.track != null && data.status) {
      const trackNum = data.track;
      const trackTitle = this._extractTrackTitle(data.message || '');

      // Register track title if new
      if (trackTitle && !state.tracks.has(trackNum)) {
        state.tracks.set(trackNum, { title: trackTitle, status: 'waiting' });
        this._renderTrack(el, trackNum, trackTitle, 'waiting');
      }

      // Update track status
      if (state.tracks.has(trackNum)) {
        state.tracks.get(trackNum).status = data.status;
      }

      if (data.status === 'done' || data.status === 'skipped') {
        state.completed++;
        this._updateProgress(el, state);
      }

      this._updateTrackStatus(el, trackNum, data.status);

      // Update subtitle with current action
      if (data.status === 'downloading') {
        this._updateJobSub(el, `Downloading track ${trackNum} of ${state.total}...`);
      } else if (data.status === 'done') {
        this._updateJobSub(el, `Track ${state.completed} of ${state.total} complete`);
      } else if (data.status === 'skipped') {
        this._updateJobSub(el, `Track ${trackNum} already exists`);
      } else if (data.status === 'error') {
        this._updateTrackStatus(el, trackNum, 'error');
      }
      return;
    }

    // Cover art
    if (data.message && data.message.includes('Cover art')) {
      this._updateJobSub(el, data.message);
      return;
    }

    // Complete
    if (data.status === 'complete') {
      state.source.close();
      state.done = true;
      const icon = el.querySelector('.job-icon');
      icon.className = 'job-icon done';
      this._updateJobTitle(el, `${data.artist} — ${data.album}`);
      this._updateJobSub(el, `${data.downloaded} of ${data.total} tracks downloaded`);
      this._updateProgress(el, { completed: data.downloaded, total: data.total });
      this._addDismissBtn(el, state.id);
      this._emitActivity(this._hasActiveJobs());
      this.dispatchEvent(new CustomEvent('download-complete', { bubbles: true, composed: true }));
      return;
    }

    // Error
    if (data.status === 'error') {
      state.source.close();
      state.done = true;
      this._setJobError(el, data.message || 'Download failed');
      this._addDismissBtn(el, state.id);
      this._emitActivity(this._hasActiveJobs());
      return;
    }

    // Generic message fallback
    if (data.message) {
      this._updateJobSub(el, data.message);
    }
  }

  _extractTrackTitle(message) {
    // Messages like "Downloading 03/12: Track Name" or "Done 03/12: Track Name"
    const match = message.match(/\d+\/\d+:\s*(.+)$/);
    if (match) return match[1];
    // "Skipping 03/12: Track Name (exists)"
    const skipMatch = message.match(/\d+\/\d+:\s*(.+?)\s*\(exists\)$/);
    if (skipMatch) return skipMatch[1];
    return '';
  }

  _updateJobTitle(el, text) {
    const title = el.querySelector('.job-title');
    if (title) title.textContent = text;
  }

  _updateJobSub(el, text) {
    const sub = el.querySelector('.job-sub');
    if (sub) sub.textContent = text;
  }

  _addProgressBar(el, state) {
    // Don't add twice
    if (el.querySelector('.job-progress')) return;
    const div = document.createElement('div');
    div.className = 'job-progress';
    div.innerHTML = `
      <div class="progress-bar"><div class="progress-fill"></div></div>
      <div class="progress-text">
        <span class="progress-count">0 of ${state.total} tracks</span>
        <span class="progress-pct">0%</span>
      </div>
    `;
    // Insert after header
    const header = el.querySelector('.job-header');
    header.after(div);
  }

  _updateProgress(el, state) {
    const fill = el.querySelector('.progress-fill');
    const count = el.querySelector('.progress-count');
    const pct = el.querySelector('.progress-pct');
    if (!fill) return;

    const ratio = state.total ? (state.completed / state.total) : 0;
    fill.style.width = `${Math.round(ratio * 100)}%`;
    if (count) count.textContent = `${state.completed} of ${state.total} tracks`;
    if (pct) pct.textContent = `${Math.round(ratio * 100)}%`;
  }

  _addTrackList(el, state) {
    if (el.querySelector('.job-tracks')) return;
    const div = document.createElement('div');
    div.className = 'job-tracks';
    el.appendChild(div);
  }

  _renderTrack(el, num, title, status) {
    const list = el.querySelector('.job-tracks');
    if (!list) return;

    // Check if track row already exists
    if (list.querySelector(`[data-track="${num}"]`)) return;

    const row = document.createElement('div');
    row.className = 'track';
    row.dataset.track = num;
    row.innerHTML = `
      <span class="track-num">${num}</span>
      <span class="track-name">${this._esc(title)}</span>
      <span class="track-status st-waiting" data-status></span>
    `;
    list.appendChild(row);
    this._updateTrackStatus(el, num, status);

    // Auto-scroll to show the latest track
    list.scrollTop = list.scrollHeight;
  }

  _updateTrackStatus(el, num, status) {
    const row = el.querySelector(`[data-track="${num}"]`);
    if (!row) return;
    const badge = row.querySelector('[data-status]');
    if (!badge) return;

    badge.className = `track-status st-${status}`;

    switch (status) {
      case 'downloading':
        badge.innerHTML = '<div class="spinner"></div>';
        break;
      case 'done':
        badge.innerHTML = icons.check;
        break;
      case 'skipped':
        badge.innerHTML = icons.skip;
        break;
      case 'error':
        badge.innerHTML = icons.alert;
        break;
      default:
        badge.innerHTML = '';
    }
  }

  _setJobError(el, message) {
    const icon = el.querySelector('.job-icon');
    if (icon) icon.className = 'job-icon error';
    this._updateJobTitle(el, 'Download failed');
    this._updateJobSub(el, message);
  }

  _addDismissBtn(el, jobId) {
    // Don't add twice
    if (el.querySelector('.job-dismiss')) return;
    const btn = document.createElement('button');
    btn.className = 'job-dismiss';
    btn.title = 'Dismiss';
    btn.innerHTML = icons.dismiss;
    btn.addEventListener('click', () => {
      el.remove();
      this._activeJobs.delete(jobId);
    });
    const header = el.querySelector('.job-header');
    header.appendChild(btn);
  }

  _hasActiveJobs() {
    return [...this._activeJobs.values()].some(j => !j.done);
  }

  _emitActivity(active) {
    this.dispatchEvent(new CustomEvent('download-activity', {
      bubbles: true, composed: true,
      detail: { active },
    }));
  }

  _esc(str) {
    return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
  }
}

customElements.define('download-panel', DownloadPanel);
