/**
 * Play tracking via IndexedDB.
 * Single store, one record per unique track (artist::album::title).
 * Upserts on every play — increments count, updates timestamp.
 */

const DB_NAME = 'musicast';
const DB_VERSION = 1;
const STORE = 'tracks';

let _db = null;

function openDB() {
  if (_db) return Promise.resolve(_db);
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = e.target.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: 'key' });
        store.createIndex('lastPlayed', 'lastPlayed');
        store.createIndex('playCount', 'playCount');
      }
    };
    req.onsuccess = () => { _db = req.result; resolve(_db); };
    req.onerror = () => reject(req.error);
  });
}

function trackKey(track) {
  return `${track.artist}::${track.album}::${track.title}`;
}

export async function recordPlay(track) {
  if (!track || !track.artist || !track.title) return;
  const db = await openDB();
  const tx = db.transaction(STORE, 'readwrite');
  const store = tx.objectStore(STORE);
  const key = trackKey(track);

  return new Promise((resolve) => {
    const get = store.get(key);
    get.onsuccess = () => {
      const rec = get.result || {
        key,
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

export async function getRecentlyPlayed(limit = 8) {
  const db = await openDB();
  const tx = db.transaction(STORE, 'readonly');
  const index = tx.objectStore(STORE).index('lastPlayed');
  const results = [];

  return new Promise((resolve) => {
    const req = index.openCursor(null, 'prev');
    req.onsuccess = (e) => {
      const cursor = e.target.result;
      if (cursor && results.length < limit) {
        results.push(cursor.value);
        cursor.continue();
      } else {
        resolve(results);
      }
    };
    req.onerror = () => resolve([]);
  });
}

export async function getMostPlayed(limit = 8) {
  const db = await openDB();
  const tx = db.transaction(STORE, 'readonly');
  const store = tx.objectStore(STORE);

  return new Promise((resolve) => {
    const req = store.getAll();
    req.onsuccess = () => {
      const all = req.result;
      all.sort((a, b) => b.playCount - a.playCount);
      resolve(all.slice(0, limit));
    };
    req.onerror = () => resolve([]);
  });
}

export async function getMostPlayedArtists(limit = 6) {
  const db = await openDB();
  const tx = db.transaction(STORE, 'readonly');
  const store = tx.objectStore(STORE);

  return new Promise((resolve) => {
    const req = store.getAll();
    req.onsuccess = () => {
      const byArtist = {};
      for (const t of req.result) {
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
      resolve(artists.slice(0, limit));
    };
    req.onerror = () => resolve([]);
  });
}
