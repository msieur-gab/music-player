import { readM4ATags } from './m4a-tags.js';
import { openDB, addTrack, getAllTracks, getTrack, deleteTrack, addPlaylist, getAllPlaylists, deletePlaylist } from './store.js';

// ── State ──
let library = [];
let albums = new Map();
let playlists = [];
let queue = [];
let queueIndex = -1;
const audio = new Audio();
let isPlaying = false;

const $ = s => document.querySelector(s);

// ── Init ──
async function init() {
  await openDB();
  await refreshLibrary();
  setupPlayer();
  setupImport();
  $('#detail-back').addEventListener('click', closeDetail);
  setupInstall();
  setupSW();
}
init().catch(e => console.error('init failed:', e));


// ── Library ──

async function refreshLibrary() {
  library = await getAllTracks();
  playlists = await getAllPlaylists();
  for (const t of library) {
    if (t.coverBlob && !t.coverUrl) t.coverUrl = URL.createObjectURL(t.coverBlob);
  }
  buildAlbums();
  renderGrid();
}

function buildAlbums() {
  albums = new Map();
  for (const t of library) {
    const key = (t.album || '').trim() || 'Unknown Album';
    if (!albums.has(key)) albums.set(key, { artist: (t.artist || '').trim(), album: key, coverUrl: null, tracks: [] });
    const a = albums.get(key);
    a.tracks.push(t);
    if (!a.coverUrl && t.coverUrl) a.coverUrl = t.coverUrl;
  }
}

function renderGrid() {
  const grid = $('#album-grid');
  if (!albums.size && !playlists.length) { grid.innerHTML = ''; $('#empty').hidden = false; return; }
  $('#empty').hidden = true;

  let html = '';

  // Playlists section
  if (playlists.length) {
    html += '<div class="section-title">Playlists</div><div class="playlist-list">';
    for (const pl of playlists) {
      const trackCount = library.filter(t => t.playlist === pl.id).length;
      const coverTrack = library.find(t => t.playlist === pl.id && t.coverUrl);
      const cover = coverTrack
        ? `<img class="pl-cover" src="${coverTrack.coverUrl}" alt="">`
        : `<div class="pl-cover ph"><svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg></div>`;
      html += `<div class="playlist-item" data-pl="${esc(pl.id)}">
        ${cover}
        <div class="pl-info">
          <div class="pl-name">${esc(pl.name)}</div>
          <div class="pl-meta">${trackCount} track${trackCount !== 1 ? 's' : ''}</div>
        </div>
        <button class="pl-delete" data-pl="${esc(pl.id)}" title="Delete">&times;</button>
      </div>`;
    }
    html += '</div>';
  }

  // Albums section
  if (albums.size) {
    if (playlists.length) html += '<div class="section-title">Albums</div>';
    html += '<div class="album-grid-inner">';
    for (const [key, a] of albums) {
      const cover = a.coverUrl
        ? `<img class="grid-cover" src="${a.coverUrl}" alt="">`
        : `<div class="grid-cover ph"><svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg></div>`;
      html += `<div class="grid-item" data-key="${esc(key)}">${cover}<div class="grid-title">${esc(a.album)}</div><div class="grid-artist">${esc(a.artist)}</div></div>`;
    }
    html += '</div>';
  }

  grid.innerHTML = html;

  // Events: albums
  grid.querySelectorAll('.grid-item').forEach(el =>
    el.addEventListener('click', () => openDetail(el.dataset.key))
  );

  // Events: playlists
  grid.querySelectorAll('.playlist-item').forEach(el => {
    el.addEventListener('click', e => {
      if (e.target.closest('.pl-delete')) return;
      openPlaylistDetail(el.dataset.pl);
    });
  });

  grid.querySelectorAll('.pl-delete').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      await deletePlaylist(btn.dataset.pl);
      await refreshLibrary();
    });
  });
}


// ── Album detail ──

function openDetail(key) {
  const a = albums.get(key);
  if (!a) return;

  const ci = $('#detail-cover'), cp = $('#detail-cover-ph');
  if (a.coverUrl) { ci.src = a.coverUrl; ci.hidden = false; cp.hidden = true; }
  else { ci.hidden = true; cp.hidden = false; }

  $('#detail-title').textContent = a.album;
  $('#detail-artist').textContent = a.artist;
  $('#detail-count').textContent = `${a.tracks.length} track${a.tracks.length > 1 ? 's' : ''}`;

  renderDetailTracks(a.tracks, key);
  $('#album-grid').hidden = true;
  $('#album-detail').hidden = false;
}

// ── Playlist detail ──

function openPlaylistDetail(plId) {
  const pl = playlists.find(p => p.id === plId);
  if (!pl) return;

  const tracks = library.filter(t => t.playlist === plId);
  const coverTrack = tracks.find(t => t.coverUrl);

  const ci = $('#detail-cover'), cp = $('#detail-cover-ph');
  if (coverTrack?.coverUrl) { ci.src = coverTrack.coverUrl; ci.hidden = false; cp.hidden = true; }
  else { ci.hidden = true; cp.hidden = false; }

  $('#detail-title').textContent = pl.name;
  $('#detail-artist').textContent = `${tracks.length} track${tracks.length > 1 ? 's' : ''}`;
  $('#detail-count').textContent = '';

  renderDetailTracks(tracks, null, plId);
  $('#album-grid').hidden = true;
  $('#album-detail').hidden = false;
}

function renderDetailTracks(tracks, albumKey, plId) {
  const ids = tracks.map(t => t.id);
  $('#detail-tracks').innerHTML = tracks.map((t, i) =>
    `<li class="track-row${t.id === queue[queueIndex] ? ' active' : ''}" data-id="${t.id}">
      <span class="track-num">${i + 1}</span>
      <div class="track-detail-info">
        <span class="track-title">${esc(t.title || t.fileName || 'Untitled')}</span>
        ${t.artist ? `<span class="track-artist-sub">${esc(t.artist)}</span>` : ''}
      </div>
      <button class="delete-btn" data-id="${t.id}">&times;</button>
    </li>`
  ).join('');

  $('#detail-tracks').querySelectorAll('.track-row').forEach(row => {
    row.addEventListener('click', e => {
      if (e.target.closest('.delete-btn')) return;
      playQueue(ids, ids.indexOf(parseInt(row.dataset.id)));
    });
  });

  $('#detail-tracks').querySelectorAll('.delete-btn').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      await deleteTrack(parseInt(btn.dataset.id));
      await refreshLibrary();
      if (albumKey && !albums.has(albumKey)) closeDetail();
      else if (albumKey) openDetail(albumKey);
      else if (plId) {
        const remaining = library.filter(t => t.playlist === plId);
        if (!remaining.length) closeDetail();
        else openPlaylistDetail(plId);
      }
    });
  });
}

function closeDetail() {
  $('#album-detail').hidden = true;
  $('#album-grid').hidden = false;
}


// ── Import (m4a files + ZIP) ──

function setupImport() {
  const input = $('#file-input');
  const btn = $('#import-btn');
  const progress = $('#import-progress');

  input.addEventListener('change', async () => {
    const selected = [...input.files];
    if (!selected.length) return;

    btn.classList.add('disabled');
    progress.hidden = false;
    progress.textContent = 'Processing...';

    try {
      const zips = selected.filter(f => f.name.toLowerCase().endsWith('.zip'));
      const audioFiles = selected.filter(f => !f.name.toLowerCase().endsWith('.zip'));

      for (const z of zips) {
        progress.textContent = `Extracting ${z.name}...`;
        const extracted = await extractZip(z);
        audioFiles.push(...extracted);
      }

      if (!audioFiles.length) {
        progress.textContent = 'No audio files found';
        setTimeout(() => { progress.hidden = true; }, 2000);
        btn.classList.remove('disabled');
        input.value = '';
        return;
      }

      // Build dedup set from existing library: "title||artist||album"
      const existing = new Set(
        library.map(t => `${(t.title||'').trim()}||${(t.artist||'').trim()}||${(t.album||'').trim()}`)
      );

      // Create a playlist for this import batch
      const now = new Date();
      const plId = `pl-${Date.now()}`;
      const zipName = zips.length === 1 ? zips[0].name.replace(/\.zip$/i, '') : null;
      const plName = zipName || `Import ${now.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })} ${now.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}`;

      let imported = 0;
      let skipped = 0;

      for (let i = 0; i < audioFiles.length; i++) {
        const f = audioFiles[i];
        progress.textContent = `Importing ${i + 1}/${audioFiles.length}...`;

        let tags = { title: '', artist: '', album: '', cover: null };
        try { tags = await readM4ATags(f); } catch (e) {}

        const title = tags.title || (f.name || '').replace(/\.\w+$/, '').replace(/^\d+\s*-\s*/, '') || 'Untitled';
        const artist = tags.artist || 'Unknown Artist';
        const album = tags.album || 'Unknown Album';
        const dedupKey = `${title.trim()}||${artist.trim()}||${album.trim()}`;

        if (existing.has(dedupKey)) {
          skipped++;
          continue;
        }
        existing.add(dedupKey);

        await addTrack({
          fileName: f.name || `track-${i + 1}.m4a`,
          title, artist, album,
          blob: f,
          coverBlob: tags.cover || null,
          playlist: plId,
        });
        imported++;
      }

      if (imported > 0) {
        await addPlaylist({ id: plId, name: plName, created: now.toISOString() });
      }

      const msg = skipped
        ? `${imported} imported, ${skipped} skipped (already in library)`
        : `${imported} tracks imported`;
      progress.textContent = msg;
      await refreshLibrary();
    } catch (e) {
      progress.textContent = `Error: ${e.message}`;
      console.error('Import error:', e);
    }

    setTimeout(() => { progress.hidden = true; }, 2000);
    btn.classList.remove('disabled');
    input.value = '';
  });
}

async function extractZip(file) {
  const buf = await file.arrayBuffer();
  const v = new DataView(buf);
  const results = [];
  let o = 0;
  while (o < buf.byteLength - 4) {
    if (v.getUint32(o, true) !== 0x04034b50) break;
    const nameLen = v.getUint16(o + 26, true);
    const extraLen = v.getUint16(o + 28, true);
    const compSize = v.getUint32(o + 18, true);
    const name = new TextDecoder().decode(new Uint8Array(buf, o + 30, nameLen));
    const dataStart = o + 30 + nameLen + extraLen;
    const lower = name.toLowerCase();
    if (lower.endsWith('.m4a') || lower.endsWith('.mp3') || lower.endsWith('.mp4')) {
      const blob = new Blob([new Uint8Array(buf, dataStart, compSize)], { type: 'audio/mp4' });
      results.push(new File([blob], name.split('/').pop(), { type: 'audio/mp4' }));
    }
    o = dataStart + compSize;
  }
  return results;
}


// ── Player ──

function setupPlayer() {
  audio.addEventListener('timeupdate', () => {
    if (!audio.duration) return;
    $('#seek').value = (audio.currentTime / audio.duration) * 1000;
    $('#time-current').textContent = fmtTime(audio.currentTime);
    if ('mediaSession' in navigator && 'setPositionState' in navigator.mediaSession) {
      try { navigator.mediaSession.setPositionState({ duration: audio.duration, playbackRate: 1, position: audio.currentTime }); } catch (e) {}
    }
  });

  audio.addEventListener('loadedmetadata', () => { $('#time-total').textContent = fmtTime(audio.duration); });
  audio.addEventListener('ended', () => { if (queueIndex < queue.length - 1) playAt(queueIndex + 1); else { isPlaying = false; updatePlayBtn(); } });
  audio.addEventListener('play', () => { isPlaying = true; updatePlayBtn(); });
  audio.addEventListener('pause', () => { isPlaying = false; updatePlayBtn(); });

  $('#seek').addEventListener('input', e => { if (audio.duration) audio.currentTime = (e.target.value / 1000) * audio.duration; });
  $('#play-btn').addEventListener('click', () => {
    if (queueIndex < 0 && library.length) playQueue(library.map(t => t.id), 0);
    else if (audio.paused) audio.play();
    else audio.pause();
  });
  $('#prev-btn').addEventListener('click', () => { if (audio.currentTime > 3) audio.currentTime = 0; else if (queueIndex > 0) playAt(queueIndex - 1); });
  $('#next-btn').addEventListener('click', () => { if (queueIndex < queue.length - 1) playAt(queueIndex + 1); });

  $('#player-cover-wrap').addEventListener('click', () => {
    if (queueIndex < 0) return;
    const t = library.find(t => t.id === queue[queueIndex]);
    if (t) { const k = (t.album || '').trim() || 'Unknown Album'; if (albums.has(k)) openDetail(k); }
  });
}

function playQueue(ids, idx) { queue = ids; playAt(Math.max(0, idx)); }

async function playAt(idx) {
  queueIndex = idx;
  const track = await getTrack(queue[idx]);
  if (!track) return;

  $('#player-title').textContent = track.title || track.fileName || 'Untitled';
  $('#player-artist').textContent = track.artist || '';
  $('#player').classList.add('active');

  const ci = $('#player-cover'), cp = $('#player-cover-ph');
  if (track.coverBlob) { ci.src = URL.createObjectURL(track.coverBlob); ci.hidden = false; cp.hidden = true; }
  else { ci.hidden = true; cp.hidden = false; }

  audio.src = URL.createObjectURL(track.blob);
  audio.play();

  document.querySelectorAll('.track-row').forEach(r => r.classList.toggle('active', parseInt(r.dataset.id) === queue[idx]));

  if ('mediaSession' in navigator) {
    const art = [];
    if (track.coverBlob) art.push({ src: URL.createObjectURL(track.coverBlob), type: track.coverBlob.type });
    navigator.mediaSession.metadata = new MediaMetadata({ title: track.title || '', artist: track.artist || '', album: track.album || '', artwork: art });
    navigator.mediaSession.setActionHandler('previoustrack', () => { if (queueIndex > 0) playAt(queueIndex - 1); });
    navigator.mediaSession.setActionHandler('nexttrack', () => { if (queueIndex < queue.length - 1) playAt(queueIndex + 1); });
    navigator.mediaSession.setActionHandler('play', () => audio.play());
    navigator.mediaSession.setActionHandler('pause', () => audio.pause());
    navigator.mediaSession.setActionHandler('seekto', e => { if (e.seekTime != null) audio.currentTime = e.seekTime; });
  }
}

function updatePlayBtn() {
  $('#play-icon').innerHTML = isPlaying
    ? '<rect x="7" y="6" width="3" height="12" rx="1"/><rect x="14" y="6" width="3" height="12" rx="1"/>'
    : '<polygon points="10,8 16,12 10,16"/>';
}


// ── Install ──

function setupInstall() {
  if (window.matchMedia('(display-mode: standalone)').matches) return;
  if (/iPad|iPhone|iPod/.test(navigator.userAgent)) {
    setTimeout(() => showBanner('Install: tap <b>Share</b> then <b>Add to Home Screen</b>'), 2000);
    return;
  }
  window.addEventListener('beforeinstallprompt', e => {
    e.preventDefault();
    showBanner('Install Soniq MiniPlayer for offline playback', async () => { e.prompt(); await e.userChoice; });
  });
}

function showBanner(msg, onAction) {
  if (document.getElementById('install-banner')) return;
  const d = document.createElement('div');
  d.id = 'install-banner';
  d.className = 'install-banner';
  d.innerHTML = `<div class="install-msg">${msg}</div><div class="install-actions">${onAction ? '<button class="install-btn" id="ib-ok">Install</button>' : ''}<button class="install-dismiss" id="ib-no">Dismiss</button></div>`;
  document.body.appendChild(d);
  requestAnimationFrame(() => d.classList.add('show'));
  if (onAction) d.querySelector('#ib-ok').addEventListener('click', () => { d.remove(); onAction(); });
  d.querySelector('#ib-no').addEventListener('click', () => d.remove());
}


// ── Service Worker ──

function setupSW() {
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register('./sw.js').catch(e => console.warn('SW register:', e));
}


// ── Helpers ──

function fmtTime(s) {
  if (!s || !isFinite(s)) return '0:00';
  return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`;
}

function esc(s) { const e = document.createElement('span'); e.textContent = s || ''; return e.innerHTML; }
