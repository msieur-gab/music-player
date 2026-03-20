/**
 * Soniq Takeaway — phone download page.
 * Fetches tracks from local server, bundles as ZIP, saves to device,
 * then links to Soniq MiniPlayer PWA for playback.
 */

let tracks = [];
let basketId = null;
let serverOrigin = '';
let downloadedBlobs = new Map(); // index → Blob

const $ = id => document.getElementById(id);
const statusEl = $('status');
const progressBar = $('progress-bar');
const progressFill = $('progress-fill');
const trackListEl = $('track-list');
const basketInfo = $('basket-info');
const saveBtn = $('save-btn');
const playerLink = $('player-link');


// ── Init ──

async function init() {
  const params = new URLSearchParams(location.search);
  basketId = params.get('basket');
  if (!basketId) {
    statusEl.textContent = 'No basket ID in URL';
    statusEl.className = 'error';
    return;
  }

  serverOrigin = location.origin;

  statusEl.textContent = 'Loading basket...';
  try {
    const r = await fetch(`${serverOrigin}/api/takeaway/basket/${basketId}`);
    if (!r.ok) throw new Error('Basket not found or expired');
    const data = await r.json();
    tracks = data.tracks;
  } catch (e) {
    statusEl.textContent = e.message;
    statusEl.className = 'error';
    return;
  }

  basketInfo.textContent = `${tracks.length} track${tracks.length !== 1 ? 's' : ''}`;
  renderTracks();
  downloadAll();
}


// ── Track list ──

function renderTracks() {
  trackListEl.innerHTML = tracks.map((t, i) => `
    <div class="track" data-idx="${i}">
      <div class="track-num">${i + 1}</div>
      <div class="track-info">
        <div class="track-title">${esc(t.title || t.file)}</div>
        <div class="track-artist">${esc(t.artist || '')}${t.album ? ' — ' + esc(t.album) : ''}</div>
      </div>
      <div class="track-status" id="ts-${i}">...</div>
    </div>
  `).join('');
}


// ── Download all tracks from LAN server ──

async function downloadAll() {
  statusEl.textContent = 'Downloading tracks...';
  statusEl.className = 'downloading';
  progressBar.classList.add('active');

  let done = 0;
  let failed = 0;

  for (let i = 0; i < tracks.length; i++) {
    const t = tracks[i];
    const tsEl = document.getElementById(`ts-${i}`);

    if (tsEl) {
      tsEl.textContent = 'downloading...';
      tsEl.className = 'track-status dl';
    }

    try {
      const fileParts = t.file.split('/').map(s => encodeURIComponent(s)).join('/');
      const url = `${serverOrigin}/api/takeaway/track/${basketId}/${fileParts}`;
      const r = await fetch(url);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const blob = await r.blob();
      downloadedBlobs.set(i, blob);

      if (tsEl) {
        tsEl.textContent = 'ready';
        tsEl.className = 'track-status cached';
      }
    } catch (e) {
      failed++;
      if (tsEl) {
        tsEl.textContent = 'failed';
        tsEl.className = 'track-status';
      }
    }

    done++;
    progressFill.style.width = Math.round((done / tracks.length) * 100) + '%';
  }

  progressBar.classList.remove('active');

  if (failed === tracks.length) {
    statusEl.textContent = 'All downloads failed';
    statusEl.className = 'error';
    return;
  }

  const readyCount = tracks.length - failed;
  statusEl.textContent = `${readyCount} track${readyCount > 1 ? 's' : ''} ready`;
  statusEl.className = 'ready';

  saveBtn.classList.remove('hidden');
  saveBtn.disabled = false;
  playerLink.classList.remove('hidden');

  saveBtn.addEventListener('click', saveAsZip);
}


// ── Build ZIP and save ──

async function saveAsZip() {
  saveBtn.disabled = true;
  saveBtn.innerHTML = '<span class="spinner"></span> Building ZIP...';

  const files = [];
  for (let i = 0; i < tracks.length; i++) {
    const blob = downloadedBlobs.get(i);
    if (!blob) continue;
    const fileName = tracks[i].file.split('/').pop() || `track-${i + 1}.m4a`;
    const data = new Uint8Array(await blob.arrayBuffer());
    files.push({ name: fileName, data });
  }

  const zipBlob = buildZip(files);

  // Derive ZIP name from album or first track
  const album = tracks[0]?.album || tracks[0]?.artist || 'takeaway';
  const zipName = `${album.replace(/[^a-zA-Z0-9_\- ]/g, '')}.zip`;

  triggerDownload(zipBlob, zipName);

  saveBtn.innerHTML = `
    <svg viewBox="0 0 24 24" style="width:18px;height:18px;stroke:#fff;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round"><polyline points="20 6 9 17 4 12"/></svg>
    ZIP saved — check Downloads
  `;
  statusEl.textContent = 'Unzip, then import tracks in Soniq MiniPlayer';
  statusEl.className = 'ready';
}


// ── Minimal ZIP builder (store method, no compression) ──

function buildZip(files) {
  const entries = [];
  let offset = 0;

  // Local file headers + data
  const parts = [];
  for (const f of files) {
    const nameBytes = new TextEncoder().encode(f.name);
    const header = new ArrayBuffer(30);
    const hv = new DataView(header);
    hv.setUint32(0, 0x04034b50, true);   // local file header sig
    hv.setUint16(4, 20, true);            // version needed
    hv.setUint16(6, 0, true);             // flags
    hv.setUint16(8, 0, true);             // compression: store
    hv.setUint16(10, 0, true);            // mod time
    hv.setUint16(12, 0, true);            // mod date
    hv.setUint32(14, crc32(f.data), true); // crc-32
    hv.setUint32(18, f.data.length, true); // compressed size
    hv.setUint32(22, f.data.length, true); // uncompressed size
    hv.setUint16(26, nameBytes.length, true); // name length
    hv.setUint16(28, 0, true);            // extra length

    entries.push({ nameBytes, data: f.data, offset });
    parts.push(new Uint8Array(header), nameBytes, f.data);
    offset += 30 + nameBytes.length + f.data.length;
  }

  // Central directory
  const centralStart = offset;
  for (const e of entries) {
    const ch = new ArrayBuffer(46);
    const cv = new DataView(ch);
    cv.setUint32(0, 0x02014b50, true);    // central dir sig
    cv.setUint16(4, 20, true);            // version made by
    cv.setUint16(6, 20, true);            // version needed
    cv.setUint16(8, 0, true);             // flags
    cv.setUint16(10, 0, true);            // compression
    cv.setUint16(12, 0, true);            // mod time
    cv.setUint16(14, 0, true);            // mod date
    cv.setUint32(16, crc32(e.data), true);
    cv.setUint32(20, e.data.length, true);
    cv.setUint32(24, e.data.length, true);
    cv.setUint16(28, e.nameBytes.length, true);
    cv.setUint16(30, 0, true);            // extra length
    cv.setUint16(32, 0, true);            // comment length
    cv.setUint16(34, 0, true);            // disk start
    cv.setUint16(36, 0, true);            // internal attrs
    cv.setUint32(38, 0, true);            // external attrs
    cv.setUint32(42, e.offset, true);     // local header offset

    parts.push(new Uint8Array(ch), e.nameBytes);
    offset += 46 + e.nameBytes.length;
  }

  // End of central directory
  const ecd = new ArrayBuffer(22);
  const ev = new DataView(ecd);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(4, 0, true);               // disk number
  ev.setUint16(6, 0, true);               // central dir disk
  ev.setUint16(8, entries.length, true);   // entries on disk
  ev.setUint16(10, entries.length, true);  // total entries
  ev.setUint32(12, offset - centralStart, true); // central dir size
  ev.setUint32(16, centralStart, true);    // central dir offset
  ev.setUint16(20, 0, true);              // comment length
  parts.push(new Uint8Array(ecd));

  return new Blob(parts, { type: 'application/zip' });
}

// CRC-32 lookup table
const _crcTable = (() => {
  const t = new Uint32Array(256);
  for (let n = 0; n < 256; n++) {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1;
    t[n] = c;
  }
  return t;
})();

function crc32(data) {
  let crc = 0xFFFFFFFF;
  for (let i = 0; i < data.length; i++) crc = _crcTable[(crc ^ data[i]) & 0xFF] ^ (crc >>> 8);
  return (crc ^ 0xFFFFFFFF) >>> 0;
}

function triggerDownload(blob, fileName) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = fileName;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 10000);
}

function esc(s) {
  const el = document.createElement('span');
  el.textContent = s;
  return el.innerHTML;
}


// ── Start ──
init();
