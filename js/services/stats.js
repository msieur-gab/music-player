/**
 * Play tracking via IndexedDB — per-listener.
 * Single store, one record per unique (listener + track).
 * Upserts on every play — increments count, updates timestamp.
 */

import { getListenerId } from './listener.js';

const DB_NAME = 'musicast';
const DB_VERSION = 2;
const STORE = 'tracks';

let _db = null;

function openDB() {
  if (_db) return Promise.resolve(_db);
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      // v1 → v2: add listener_id to existing records, add compound index
      if (e.oldVersion < 1) {
        const store = db.createObjectStore(STORE, { keyPath: 'key' });
        store.createIndex('lastPlayed', 'lastPlayed');
        store.createIndex('playCount', 'playCount');
        store.createIndex('listener', 'listener_id');
      }
      if (e.oldVersion < 2 && e.oldVersion >= 1) {
        // Add listener index to existing store
        const store = e.target.transaction.objectStore(STORE);
        if (!store.indexNames.contains('listener')) {
          store.createIndex('listener', 'listener_id');
        }
      }
    };
    req.onsuccess = () => { _db = req.result; resolve(_db); };
    req.onerror = () => reject(req.error);
  });
}

function trackKey(track) {
  const lid = getListenerId() || 'guest';
  return `${lid}::${track.artist}::${track.album}::${track.title}`;
}

export async function recordPlay(track) {
  if (!track || !track.artist || !track.title) return;
  const db = await openDB();
  const tx = db.transaction(STORE, 'readwrite');
  const store = tx.objectStore(STORE);
  const key = trackKey(track);
  const lid = getListenerId() || 'guest';

  return new Promise((resolve) => {
    const get = store.get(key);
    get.onsuccess = () => {
      const rec = get.result || {
        key,
        listener_id: lid,
        artist: track.artist,
        album: track.album,
        title: track.title,
        cover: track.cover,
        playCount: 0,
      };
      rec.playCount++;
      rec.lastPlayed = Date.now();
      if (track.cover) rec.cover = track.cover;
      store.put(rec);
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => resolve(); // don't break playback over stats
  });
}

async function _getAll() {
  const db = await openDB();
  const tx = db.transaction(STORE, 'readonly');
  const store = tx.objectStore(STORE);
  const lid = getListenerId() || 'guest';

  return new Promise((resolve) => {
    const req = store.getAll();
    req.onsuccess = () => {
      // Filter to current listener (also includes legacy records without listener_id)
      const all = req.result.filter(r =>
        r.listener_id === lid || (!r.listener_id && lid === 'guest')
      );
      resolve(all);
    };
    req.onerror = () => resolve([]);
  });
}

export async function getRecentlyPlayed(limit = 8) {
  const all = await _getAll();
  all.sort((a, b) => (b.lastPlayed || 0) - (a.lastPlayed || 0));
  return all.slice(0, limit);
}

export async function getMostPlayed(limit = 8) {
  const all = await _getAll();
  all.sort((a, b) => b.playCount - a.playCount);
  return all.slice(0, limit);
}

export async function getMostPlayedArtists(limit = 6) {
  const all = await _getAll();
  const byArtist = {};
  for (const t of all) {
    if (!byArtist[t.artist]) {
      byArtist[t.artist] = { artist: t.artist, cover: t.cover, playCount: 0, _max: 0 };
    }
    byArtist[t.artist].playCount += t.playCount;
    if (t.playCount > byArtist[t.artist]._max) {
      byArtist[t.artist].cover = t.cover;
      byArtist[t.artist]._max = t.playCount;
    }
  }
  const artists = Object.values(byArtist)
    .map(({ _max, ...rest }) => rest)
    .sort((a, b) => b.playCount - a.playCount);
  return artists.slice(0, limit);
}
