/**
 * <sonic-sunburst> — View addon: seed a track, rings of similarity expand outward,
 * wedges reveal the emotional axis that connects.
 *
 * Contract:
 *   - Fetches /api/tracks on open
 *   - Emits 'addon-play' { tracks, index } when user wants to play
 *   - Reads CSS variables for theming (--bg, --text, --accent, etc.)
 *   - Renders as full feed view
 */

const tpl = document.createElement('template');
tpl.innerHTML = `
<style>
:host {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--bg, #0a0a0f);
  color: var(--text, #e8e6e3);
  font-family: system-ui, -apple-system, sans-serif;
  -webkit-user-select: none; user-select: none;
}

.top-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; border-bottom: 1px solid var(--border, #1a1a24);
  flex-shrink: 0; min-height: 48px;
}
.top-bar h1 {
  font-family: Georgia, 'Times New Roman', serif;
  font-weight: 400; font-size: 18px; margin: 0;
  color: var(--text, #e8e6e3);
}
.search-wrap { position: relative; flex: 0 0 280px; }
.search-input {
  width: 100%; padding: 7px 12px; font-size: 13px;
  background: var(--bg, #12121a); border: 1px solid var(--border, #2a2a3a);
  border-radius: var(--radius, 6px);
  color: var(--text, #e8e6e3); outline: none; font-family: inherit;
}
.search-input:focus { border-color: var(--accent, #c4704b); }
.search-input::placeholder { color: var(--text-faint, #3a3a4a); }
.search-results {
  position: absolute; top: 100%; left: 0; right: 0;
  background: var(--bg-raised, #14141f); border: 1px solid var(--border, #2a2a3a);
  border-radius: 0 0 6px 6px;
  max-height: 300px; overflow-y: auto; z-index: 200; display: none;
}
.search-results.open { display: block; }
.sr-item {
  padding: 8px 12px; cursor: pointer;
  border-bottom: 1px solid var(--border, #1a1a24);
}
.sr-item:hover { background: var(--bg-hover, rgba(196,112,75,0.08)); }
.sr-item:last-child { border-bottom: none; }
.sr-title { font-size: 13px; color: var(--text, #e8e6e3); }
.sr-meta { font-size: 11px; color: var(--text-muted, #5a5a5a); }
.status { font-size: 12px; color: var(--text-muted, #6e6d6a); margin-left: auto; }

.main { flex: 1; overflow: hidden; position: relative; min-height: 0; }
canvas { width: 100%; height: 100%; display: block; touch-action: none; }
</style>

<div class="top-bar">
  <h1>Sonic Sunburst</h1>
  <div class="search-wrap">
    <input type="text" class="search-input" id="search" placeholder="search a track to seed..." autocomplete="off">
    <div class="search-results" id="results"></div>
  </div>
  <span class="status" id="status">Loading...</span>
</div>

<div class="main">
  <canvas id="cv"></canvas>
</div>
`;

/* ─── emotional dimensions — the wedges of the sunburst ── */

const WEDGES = [
  { key: 'relaxed',       label: 'Relaxed',       color: [105, 160, 125] },
  { key: 'warm',          label: 'Warm',          color: [185, 150, 100] },
  { key: 'happy',         label: 'Happy',         color: [210, 190, 85] },
  { key: 'radiant',       label: 'Radiant',       color: [215, 185, 120] },
  { key: 'energetic',     label: 'Energetic',     color: [210, 125, 75] },
  { key: 'danceable',     label: 'Danceable',     color: [205, 130, 95] },
  { key: 'aggressive',    label: 'Aggressive',    color: [190, 82, 78] },
  { key: 'hypnotic',      label: 'Hypnotic',      color: [140, 110, 170] },
  { key: 'contemplative', label: 'Contemplative', color: [100, 128, 175] },
  { key: 'somber',        label: 'Somber',        color: [90, 105, 140] },
  { key: 'sad',           label: 'Sad',           color: [100, 110, 155] },
  { key: 'instrumental',  label: 'Instrumental',  color: [155, 148, 110] },
];

const CLS_KEYS = [
  'happy','sad','relaxed','aggressive',
  'danceable','instrumental','vocal',
  'radiant','somber','warm','energetic','still',
  'hypnotic','contemplative','restless',
  'arousal','valence'
];

const RINGS = [
  { min: 0.92, max: 1.00 },
  { min: 0.85, max: 0.92 },
  { min: 0.78, max: 0.85 },
  { min: 0.70, max: 0.78 },
  { min: 0.60, max: 0.70 },
];

const WEDGE_MIN_SCORE = 0.08;
const WEDGE_GAP = 0.03;

/* ─── helpers ── */

function rgb(c, a) {
  return a !== undefined
    ? `rgba(${c[0]},${c[1]},${c[2]},${a})`
    : `rgb(${c[0]},${c[1]},${c[2]})`;
}

function cosineSim(a, b) {
  let dot = 0, ma = 0, mb = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i]; ma += a[i] * a[i]; mb += b[i] * b[i];
  }
  return dot / (Math.sqrt(ma) * Math.sqrt(mb) + 0.0001);
}

function trackVector(t) { return CLS_KEYS.map(k => t[k] || 0); }
function truncate(s, max) { return s.length > max ? s.substring(0, max - 1) + '\u2026' : s; }
function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

class SonicSunburst extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));

    this._tracks = [];
    this._seed = null;
    this._burst = [];
    this._activeWedges = [];
    this._selectedWedge = -1;
    this._hoveredItem = -1;
    this._playlist = [];
    this._playIdx = -1;

    // zoom/pan
    this._zoom = 1;
    this._panX = 0; this._panY = 0;
    this._isPanning = false; this._didPan = false;
    this._panStartX = 0; this._panStartY = 0;
    this._panStartPX = 0; this._panStartPY = 0;

    // geometry
    this._cx = 0; this._cy = 0;
    this._innerR = 0; this._outerR = 0;
    this._W = 0; this._H = 0;

    this._canvas = null;
    this._ctx = null;
    this._resizeObserver = null;
  }

  connectedCallback() {
    const $ = id => this.shadowRoot.getElementById(id);

    this._canvas = $('cv');
    this._ctx = this._canvas.getContext('2d');

    // Search
    const search = $('search');
    const results = $('results');
    let searchTimer = 0;

    search.addEventListener('input', () => {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(() => this._doSearch(search, results), 100);
    });
    search.addEventListener('focus', () => {
      if (search.value.length >= 2) this._doSearch(search, results);
    });
    this.shadowRoot.addEventListener('click', e => {
      if (!e.target.closest('.search-wrap')) results.classList.remove('open');
    });

    // Canvas interaction
    this._setupInteraction();

    // Resize
    this._resizeObserver = new ResizeObserver(() => this._resize());
    this._resizeObserver.observe(this._canvas.parentElement);

    // Redraw on theme change (canvas colors come from CSS vars at draw time)
    new MutationObserver(() => requestAnimationFrame(() => this._draw()))
      .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

    // Highlight currently playing track (sent by main app)
    this._playingUrl = null;
    this.addEventListener('highlight-track', (e) => {
      const url = e.detail?.url || null;
      if (url !== this._playingUrl) {
        this._playingUrl = url;
        this._draw();
      }
    });

    this._loadTracks();
  }

  disconnectedCallback() {
    if (this._resizeObserver) this._resizeObserver.disconnect();
  }

  /* ─── data loading ── */

  async _loadTracks() {
    try {
      // Use TrackStore if available (loaded by main app), else fetch directly
      const mod = await import('/js/services/track-store.js').catch(() => null);
      if (mod?.trackStore) {
        await mod.trackStore.load();
        this._tracks = mod.trackStore.getAll();
      } else {
        // Fallback: direct fetch (standalone mode)
        const r = await fetch('/api/tracks?per_page=5000');
        const data = await r.json();
        const rows = data.tracks || data;
        this._tracks = rows.map(t => {
          const cls = typeof t.cls_json === 'string' ? JSON.parse(t.cls_json) : (t.cls_json || {});
          return { ...t, ...cls };
        });
      }

      this.shadowRoot.getElementById('status').textContent = this._tracks.length + ' tracks';
      this._resize();
    } catch {
      this.shadowRoot.getElementById('status').textContent = 'could not load tracks';
    }
  }

  /* ─── search ── */

  _doSearch(input, results) {
    const q = input.value.trim().toLowerCase();
    if (q.length < 2) { results.classList.remove('open'); return; }

    const matches = [];
    for (const t of this._tracks) {
      const hay = `${t.title || ''} ${t.artist || ''} ${t.album || ''}`.toLowerCase();
      if (hay.includes(q)) {
        matches.push(t);
        if (matches.length >= 20) break;
      }
    }

    results.innerHTML = matches.map((t, i) =>
      `<div class="sr-item" data-idx="${i}">
        <div class="sr-title">${esc(t.title || 'Untitled')}</div>
        <div class="sr-meta">${esc(t.artist)} \u00b7 ${esc(t.album)}</div>
      </div>`
    ).join('');

    results.classList.toggle('open', matches.length > 0);

    results.querySelectorAll('.sr-item').forEach(el => {
      el.addEventListener('click', () => {
        this._setSeed(matches[parseInt(el.dataset.idx)]);
        input.value = '';
        results.classList.remove('open');
      });
    });
  }

  /* ─── seed & burst computation ── */

  _setSeed(track) {
    this._seed = track;
    this._selectedWedge = -1;
    this._zoom = 1; this._panX = 0; this._panY = 0;
    this._computeBurst();
    this._buildPlaylist();
    this._draw();
  }

  _computeBurst() {
    this._burst = [];
    this._activeWedges = [];
    if (!this._seed) return;

    // Build active wedges proportional to seed's scores
    const scored = [];
    let totalScore = 0;
    for (let w = 0; w < WEDGES.length; w++) {
      const val = this._seed[WEDGES[w].key] || 0;
      if (val >= WEDGE_MIN_SCORE) {
        scored.push({ idx: w, key: WEDGES[w].key, label: WEDGES[w].label, color: WEDGES[w].color, score: val });
        totalScore += val;
      }
    }
    if (!scored.length || !totalScore) return;

    scored.sort((a, b) => b.score - a.score);

    const totalGap = scored.length * WEDGE_GAP;
    const availableArc = Math.PI * 2 - totalGap;
    let cursor = -Math.PI / 2;

    for (const s of scored) {
      const span = (s.score / totalScore) * availableArc;
      this._activeWedges.push({
        ...s, startAngle: cursor, endAngle: cursor + span, span,
      });
      cursor += span + WEDGE_GAP;
    }

    // Find similar tracks
    const seedVec = trackVector(this._seed);
    const candidates = [];

    for (const t of this._tracks) {
      if (t === this._seed) continue;
      const sim = cosineSim(seedVec, trackVector(t));
      if (sim < RINGS[RINGS.length - 1].min) continue;

      let ringIdx = -1;
      for (let r = 0; r < RINGS.length; r++) {
        if (sim >= RINGS[r].min) { ringIdx = r; break; }
      }
      if (ringIdx < 0) continue;

      let bestWedgeSlot = 0, bestProduct = 0;
      for (let aw = 0; aw < this._activeWedges.length; aw++) {
        const product = (this._seed[this._activeWedges[aw].key] || 0) * (t[this._activeWedges[aw].key] || 0);
        if (product > bestProduct) { bestProduct = product; bestWedgeSlot = aw; }
      }

      candidates.push({ track: t, sim, wedgeSlot: bestWedgeSlot, ringIdx, sharedStrength: bestProduct });
    }

    candidates.sort((a, b) => b.sim - a.sim);

    const perRing = new Array(RINGS.length).fill(0);
    const MAX_PER_RING = 50;
    const cellCounts = {};

    for (const c of candidates) {
      if (perRing[c.ringIdx] >= MAX_PER_RING) continue;
      perRing[c.ringIdx]++;

      const wedge = this._activeWedges[c.wedgeSlot];
      const cellKey = `${c.wedgeSlot}-${c.ringIdx}`;
      const cellIdx = cellCounts[cellKey] || 0;
      cellCounts[cellKey] = cellIdx + 1;

      const padding = wedge.span * 0.06;
      const usableSpan = wedge.span - padding * 2;
      const t = (cellIdx + 0.5) / Math.max(cellIdx + 1, 12);
      const angle = wedge.startAngle + padding + t * usableSpan;

      const ring = RINGS[c.ringIdx];
      const simNorm = (c.sim - ring.min) / (ring.max - ring.min);

      this._burst.push({
        track: c.track, sim: c.sim, wedgeSlot: c.wedgeSlot,
        ringIdx: c.ringIdx, angle, simNorm, sharedStrength: c.sharedStrength,
      });
    }
  }

  /* ─── playlist → emit to main app's detail panel ── */

  _buildPlaylist() {
    if (!this._seed) {
      this._playlist = [];
      return;
    }

    this._playlist = [this._seed];
    const items = this._selectedWedge >= 0
      ? this._burst.filter(item => item.wedgeSlot === this._selectedWedge)
      : this._burst;
    for (const item of items) this._playlist.push(item.track);

    let label = `Similar to ${this._seed.title || 'Untitled'}`;
    let desc = this._seed.artist || '';
    if (this._selectedWedge >= 0 && this._activeWedges[this._selectedWedge]) {
      desc += ` \u00b7 ${this._activeWedges[this._selectedWedge].label}`;
    }

    // Tell the main app to show this playlist in album-detail
    const tracks = this._playlist.map(t => ({
      file: t.file,
      title: t.title || 'Untitled',
      artist: t.artist || '',
      album: t.album || '',
      cover: t.cover || null,
      url: t.url || `/music/${(t.file || '').split('/').map(s => encodeURIComponent(s)).join('/')}`,
    }));

    this.dispatchEvent(new CustomEvent('addon-playlist', {
      bubbles: true, composed: true,
      detail: { label, desc, tracks },
    }));
  }

  /* ─── emit play to main app ── */

  _emitPlay(index) {
    const tracks = this._playlist.map(t => ({
      file: t.file,
      title: t.title || 'Untitled',
      artist: t.artist || '',
      album: t.album || '',
      cover: t.cover || null,
      url: t.url || `/music/${(t.file || '').split('/').map(s => encodeURIComponent(s)).join('/')}`,
    }));

    this.dispatchEvent(new CustomEvent('addon-play', {
      bubbles: true, composed: true,
      detail: { tracks, index },
    }));
  }

  /* ─── transform helpers ── */

  _toScreen(bx, by) {
    return {
      x: (bx - this._cx) * this._zoom + this._cx + this._panX,
      y: (by - this._cy) * this._zoom + this._cy + this._panY,
    };
  }

  _toBase(sx, sy) {
    return {
      x: (sx - this._cx - this._panX) / this._zoom + this._cx,
      y: (sy - this._cy - this._panY) / this._zoom + this._cy,
    };
  }

  /* ─── hit testing ── */

  _hitItem(mx, my) {
    for (let i = 0; i < this._burst.length; i++) {
      const item = this._burst[i];
      if (item._sx === undefined) continue;
      const dx = mx - item._sx, dy = my - item._sy;
      if (dx * dx + dy * dy < 100) return i;
    }
    return -1;
  }

  _hitCenter(mx, my) {
    const b = this._toBase(mx, my);
    const dx = b.x - this._cx, dy = b.y - this._cy;
    return Math.sqrt(dx * dx + dy * dy) < this._innerR;
  }

  _hitWedge(mx, my) {
    if (!this._activeWedges.length) return -1;
    const b = this._toBase(mx, my);
    const dx = b.x - this._cx, dy = b.y - this._cy;
    const dist = Math.sqrt(dx * dx + dy * dy);
    if (dist < this._innerR || dist > this._outerR + 30) return -1;
    let angle = Math.atan2(dy, dx);
    for (let i = 0; i < this._activeWedges.length; i++) {
      const w = this._activeWedges[i];
      let a = angle;
      if (w.startAngle <= w.endAngle) {
        if (a >= w.startAngle && a <= w.endAngle) return i;
      } else {
        if (a >= w.startAngle || a <= w.endAngle) return i;
      }
      a += Math.PI * 2;
      if (w.startAngle <= w.endAngle && a >= w.startAngle && a <= w.endAngle) return i;
    }
    return -1;
  }

  _handleClick(mx, my) {
    const hit = this._hitItem(mx, my);
    if (hit >= 0) {
      const track = this._burst[hit].track;
      const pIdx = this._playlist.indexOf(track);
      if (pIdx >= 0) this._emitPlay(pIdx);
      return;
    }
    if (this._hitCenter(mx, my) && this._seed) {
      this._emitPlay(0);
      return;
    }
    const wHit = this._hitWedge(mx, my);
    if (wHit >= 0) {
      this._selectedWedge = this._selectedWedge === wHit ? -1 : wHit;
      this._buildPlaylist();
      this._draw();
      return;
    }
    if (this._selectedWedge >= 0) {
      this._selectedWedge = -1;
      this._buildPlaylist();
      this._draw();
    }
  }

  /* ─── interaction setup ── */

  _setupInteraction() {
    const cv = this._canvas;

    const getXY = e => {
      const t = e.touches ? e.touches[0] : e;
      const r = cv.getBoundingClientRect();
      return { x: t.clientX - r.left, y: t.clientY - r.top };
    };

    // Mouse
    cv.addEventListener('mousedown', e => {
      const p = getXY(e);
      this._isPanning = true; this._didPan = false;
      this._panStartX = p.x; this._panStartY = p.y;
      this._panStartPX = this._panX; this._panStartPY = this._panY;
    });

    cv.addEventListener('mousemove', e => {
      const p = getXY(e);
      if (this._isPanning) {
        const dx = p.x - this._panStartX, dy = p.y - this._panStartY;
        if (Math.abs(dx) > 3 || Math.abs(dy) > 3) this._didPan = true;
        if (this._didPan) {
          this._panX = this._panStartPX + dx;
          this._panY = this._panStartPY + dy;
          cv.style.cursor = 'grabbing';
          this._draw();
        }
        return;
      }
      const hit = this._hitItem(p.x, p.y);
      cv.style.cursor = hit >= 0 || this._hitCenter(p.x, p.y) || this._hitWedge(p.x, p.y) >= 0 ? 'pointer' : 'default';
      if (hit !== this._hoveredItem) {
        this._hoveredItem = hit;
        this._draw();
      }
    });

    document.addEventListener('mouseup', e => {
      if (!this._isPanning) return;
      const wasDrag = this._didPan;
      this._isPanning = false; this._didPan = false;
      cv.style.cursor = 'default';
      if (wasDrag) return;
      const r = cv.getBoundingClientRect();
      this._handleClick(e.clientX - r.left, e.clientY - r.top);
    });

    cv.addEventListener('mouseleave', () => {
      if (this._hoveredItem >= 0) { this._hoveredItem = -1; this._draw(); }
    });

    // Double-click: re-seed
    cv.addEventListener('dblclick', e => {
      const r = cv.getBoundingClientRect();
      const hit = this._hitItem(e.clientX - r.left, e.clientY - r.top);
      if (hit >= 0) this._setSeed(this._burst[hit].track);
    });

    // Scroll wheel zoom
    cv.addEventListener('wheel', e => {
      e.preventDefault();
      const r = cv.getBoundingClientRect();
      const mx = e.clientX - r.left, my = e.clientY - r.top;
      const delta = e.deltaY > 0 ? 0.85 : 1.18;
      const newZoom = Math.max(0.5, Math.min(6, this._zoom * delta));
      const scale = newZoom / this._zoom;
      this._panX = mx - scale * (mx - this._panX);
      this._panY = my - scale * (my - this._panY);
      this._zoom = newZoom;
      this._draw();
    }, { passive: false });

    // Touch: pinch + pan + tap
    let lastPinchDist = 0, touchDidMove = false;

    cv.addEventListener('touchstart', e => {
      touchDidMove = false;
      if (e.touches.length === 2) {
        e.preventDefault();
        const dx = e.touches[1].clientX - e.touches[0].clientX;
        const dy = e.touches[1].clientY - e.touches[0].clientY;
        lastPinchDist = Math.sqrt(dx * dx + dy * dy);
        this._isPanning = false;
      } else if (e.touches.length === 1) {
        const p = getXY(e);
        this._isPanning = true;
        this._panStartX = p.x; this._panStartY = p.y;
        this._panStartPX = this._panX; this._panStartPY = this._panY;
      }
    }, { passive: false });

    cv.addEventListener('touchmove', e => {
      e.preventDefault();
      touchDidMove = true;
      if (e.touches.length === 2 && lastPinchDist > 0) {
        const dx = e.touches[1].clientX - e.touches[0].clientX;
        const dy = e.touches[1].clientY - e.touches[0].clientY;
        const dist = Math.sqrt(dx * dx + dy * dy);
        const newZoom = Math.max(0.5, Math.min(6, this._zoom * (dist / lastPinchDist)));
        const r = cv.getBoundingClientRect();
        const pcx = (e.touches[0].clientX + e.touches[1].clientX) / 2 - r.left;
        const pcy = (e.touches[0].clientY + e.touches[1].clientY) / 2 - r.top;
        const s = newZoom / this._zoom;
        this._panX = pcx - s * (pcx - this._panX);
        this._panY = pcy - s * (pcy - this._panY);
        this._zoom = newZoom;
        lastPinchDist = dist;
        this._draw();
      } else if (this._isPanning && e.touches.length === 1) {
        const p = getXY(e);
        this._panX = this._panStartPX + (p.x - this._panStartX);
        this._panY = this._panStartPY + (p.y - this._panStartY);
        this._draw();
      }
    }, { passive: false });

    cv.addEventListener('touchend', e => {
      this._isPanning = false;
      lastPinchDist = 0;
      if (touchDidMove) { touchDidMove = false; return; }
      if (e.changedTouches?.[0]) {
        const t = e.changedTouches[0];
        const r = cv.getBoundingClientRect();
        this._handleClick(t.clientX - r.left, t.clientY - r.top);
      }
    });
  }

  /* ─── resize ── */

  _resize() {
    const parent = this._canvas.parentElement;
    const rect = parent.getBoundingClientRect();
    const pw = rect.width;
    this._canvas.width = pw * devicePixelRatio;
    this._canvas.height = rect.height * devicePixelRatio;
    this._ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
    this._W = pw;
    this._H = rect.height;
    this._cx = pw / 2;
    this._cy = rect.height / 2;
    const maxR = Math.min(pw, rect.height) / 2 - 40;
    this._innerR = maxR * 0.18;
    this._outerR = maxR * 0.92;
    this._draw();
  }

  /* ─── drawing ── */

  _draw() {
    const ctx = this._ctx;
    const W = this._W, H = this._H;
    const cx = this._cx, cy = this._cy;
    const zoom = this._zoom;
    const innerR = this._innerR, outerR = this._outerR;

    ctx.clearRect(0, 0, W, H);

    // Read theme from document root (source of truth, not the bridged copy)
    const style = getComputedStyle(document.documentElement);
    const bgColor = style.getPropertyValue('--bg').trim() || '#0a0a0f';
    const textColor = style.getPropertyValue('--text').trim() || '#e8e6e3';
    const mutedColor = style.getPropertyValue('--text-muted').trim() || '#6e6d6a';
    const faintColor = style.getPropertyValue('--text-faint').trim() || '#3a3a4a';

    ctx.fillStyle = bgColor;
    ctx.fillRect(0, 0, W, H);

    if (!this._seed) {
      ctx.font = '13px system-ui';
      ctx.fillStyle = faintColor;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('search for a track to seed the sunburst', cx, cy);
      return;
    }

    ctx.save();
    ctx.translate(cx + this._panX, cy + this._panY);
    ctx.scale(zoom, zoom);
    ctx.translate(-cx, -cy);

    const ringWidth = (outerR - innerR) / RINGS.length;

    // Ring backgrounds
    for (let r = 0; r < RINGS.length; r++) {
      const rInner = innerR + r * ringWidth;
      const rOuter = rInner + ringWidth;
      const alpha = 0.025 - r * 0.004;
      ctx.beginPath();
      ctx.arc(cx, cy, rOuter, 0, Math.PI * 2);
      ctx.arc(cx, cy, rInner, 0, Math.PI * 2, true);
      ctx.fillStyle = `rgba(255,255,255,${Math.max(0.005, alpha)})`;
      ctx.fill();
      ctx.beginPath();
      ctx.arc(cx, cy, rOuter, 0, Math.PI * 2);
      ctx.strokeStyle = 'rgba(255,255,255,0.03)';
      ctx.lineWidth = 0.5;
      ctx.stroke();
    }

    // Wedges
    for (let aw = 0; aw < this._activeWedges.length; aw++) {
      const wedge = this._activeWedges[aw];
      const c = wedge.color;

      // Separator
      const x1 = cx + Math.cos(wedge.startAngle) * innerR;
      const y1 = cy + Math.sin(wedge.startAngle) * innerR;
      const x2 = cx + Math.cos(wedge.startAngle) * outerR;
      const y2 = cy + Math.sin(wedge.startAngle) * outerR;
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2);
      ctx.strokeStyle = rgb(c, 0.1); ctx.lineWidth = 0.5; ctx.stroke();

      // Wedge fill
      ctx.beginPath(); ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, outerR, wedge.startAngle, wedge.endAngle);
      ctx.closePath();
      ctx.fillStyle = rgb(c, 0.01 + wedge.score * 0.03);
      ctx.fill();

      if (this._selectedWedge === aw) {
        ctx.beginPath(); ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, outerR, wedge.startAngle, wedge.endAngle);
        ctx.closePath();
        ctx.fillStyle = rgb(c, 0.06);
        ctx.fill();
      }

      // Score bar
      ctx.beginPath();
      ctx.arc(cx, cy, innerR + 2, wedge.startAngle, wedge.endAngle);
      ctx.strokeStyle = rgb(c, 0.35);
      ctx.lineWidth = 3 + wedge.score * 6;
      ctx.lineCap = 'butt'; ctx.stroke();

      // Label
      const midAngle = (wedge.startAngle + wedge.endAngle) / 2;
      const lx = cx + Math.cos(midAngle) * (outerR + 14);
      const ly = cy + Math.sin(midAngle) * (outerR + 14);
      const normMid = ((midAngle % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
      const flip = normMid > Math.PI / 2 && normMid < 3 * Math.PI / 2;
      const isSel = this._selectedWedge === aw;

      ctx.save();
      ctx.translate(lx, ly);
      ctx.scale(1 / zoom, 1 / zoom);
      ctx.rotate(flip ? midAngle + Math.PI : midAngle);
      ctx.textAlign = flip ? 'right' : 'left';
      ctx.textBaseline = 'middle';
      ctx.font = (isSel ? '500 ' : '') + '10px system-ui';
      ctx.fillStyle = rgb(c, isSel ? 0.9 : 0.6);
      ctx.fillText(`${wedge.label} ${Math.round(wedge.score * 100)}%`, 0, 0);
      ctx.restore();
    }

    // Track dots
    const showAllLabels = zoom >= 2.5;
    const showSomeLabels = zoom >= 1.5;

    for (let i = 0; i < this._burst.length; i++) {
      const item = this._burst[i];
      const ringStart = innerR + item.ringIdx * ringWidth;
      const r = ringStart + (1 - item.simNorm) * ringWidth * 0.8 + ringWidth * 0.1;
      const bx = cx + Math.cos(item.angle) * r;
      const by = cy + Math.sin(item.angle) * r;
      const sp = this._toScreen(bx, by);
      item._sx = sp.x; item._sy = sp.y;

      const wc = this._activeWedges[item.wedgeSlot].color;
      const isHov = this._hoveredItem === i;
      const isPlaying = this._playingUrl && item.track.url === this._playingUrl;
      const isWedgeSel = this._selectedWedge === item.wedgeSlot;
      const dimmed = (this._hoveredItem >= 0 && !isHov && !isPlaying) || (this._selectedWedge >= 0 && !isWedgeSel);
      const distFade = 1 - (item.ringIdx / RINGS.length) * 0.5;
      const alpha = dimmed ? 0.06 : (isHov || isPlaying ? 1 : (isWedgeSel ? 0.7 : 0.4 * distFade));
      const dotR = isHov ? 5 : (isPlaying ? 6 : 2.5 + item.sharedStrength * 2);

      if (isPlaying) {
        // Playing indicator: pulsing ring
        ctx.beginPath(); ctx.arc(bx, by, dotR + 8, 0, Math.PI * 2);
        ctx.fillStyle = rgb(wc, 0.15); ctx.fill();
        ctx.beginPath(); ctx.arc(bx, by, dotR + 4, 0, Math.PI * 2);
        ctx.strokeStyle = rgb(wc, 0.5); ctx.lineWidth = 1.5 / zoom; ctx.stroke();
      }

      if (isHov) {
        ctx.beginPath(); ctx.arc(bx, by, dotR + 6, 0, Math.PI * 2);
        ctx.fillStyle = rgb(wc, 0.12); ctx.fill();
        ctx.beginPath(); ctx.moveTo(cx, cy); ctx.lineTo(bx, by);
        ctx.strokeStyle = rgb(wc, 0.15); ctx.lineWidth = 1 / zoom;
        ctx.setLineDash([3 / zoom, 4 / zoom]); ctx.stroke(); ctx.setLineDash([]);
      }

      ctx.beginPath(); ctx.arc(bx, by, dotR, 0, Math.PI * 2);
      ctx.fillStyle = rgb(wc, alpha); ctx.fill();

      const showLabel = isHov || isPlaying || (showAllLabels && !dimmed) || (showSomeLabels && item.ringIdx <= 1 && !dimmed);
      if (showLabel) {
        ctx.save();
        ctx.translate(bx, by);
        ctx.scale(1 / zoom, 1 / zoom);
        ctx.font = (isHov ? '500 ' : '') + '10px system-ui';
        ctx.fillStyle = isHov ? textColor : rgb(wc, 0.7);
        ctx.textAlign = bx > cx ? 'left' : 'right';
        ctx.textBaseline = 'bottom';
        const off = bx > cx ? 8 : -8;
        ctx.fillText(truncate(item.track.title || 'Untitled', 28), off, -4);
        ctx.font = '9px system-ui';
        ctx.fillStyle = isHov ? mutedColor : rgb(wc, 0.4);
        ctx.fillText(`${item.track.artist} \u00b7 ${(item.sim * 100).toFixed(0)}%`, off, 9);
        ctx.restore();
      }
    }

    // Center: seed info
    ctx.beginPath(); ctx.arc(cx, cy, innerR, 0, Math.PI * 2);
    ctx.fillStyle = bgColor; ctx.fill();
    ctx.strokeStyle = 'rgba(255,255,255,0.06)'; ctx.lineWidth = 1.5 / zoom; ctx.stroke();

    ctx.save();
    ctx.translate(cx, cy);
    ctx.scale(1 / zoom, 1 / zoom);
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = '500 12px system-ui'; ctx.fillStyle = textColor;
    ctx.fillText(truncate(this._seed.title || 'Untitled', 22), 0, -14);
    ctx.font = '10px system-ui'; ctx.fillStyle = mutedColor;
    ctx.fillText(this._seed.artist || '', 0, 2);

    const seedDims = [];
    WEDGES.forEach(w => {
      const val = this._seed[w.key] || 0;
      if (val > 0.2) seedDims.push({ label: w.label, val, color: w.color });
    });
    seedDims.sort((a, b) => b.val - a.val);
    const topDims = seedDims.slice(0, 3);
    if (topDims.length) {
      ctx.font = '8px system-ui';
      ctx.fillStyle = rgb(topDims[0].color, 0.6);
      ctx.fillText(topDims.map(d => d.label).join(' \u00b7 '), 0, 16);
    }
    ctx.font = '8px system-ui'; ctx.fillStyle = faintColor;
    ctx.fillText(this._burst.length + ' similar tracks', 0, 28);
    ctx.restore();

    ctx.restore();

    if (zoom !== 1) {
      ctx.font = '10px system-ui'; ctx.fillStyle = faintColor;
      ctx.textAlign = 'left'; ctx.textBaseline = 'top';
      ctx.fillText(zoom.toFixed(1) + 'x', 12, 12);
    }
  }
}

customElements.define('sonic-sunburst', SonicSunburst);
