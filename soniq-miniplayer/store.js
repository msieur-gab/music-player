/**
 * IndexedDB store for Soniq MiniPlayer.
 * Stores tracks (blob + metadata) with playlist grouping.
 */

const DB_NAME = 'soniq-miniplayer';
const DB_VERSION = 2;
const TRACKS = 'tracks';
const PLAYLISTS = 'playlists';

let _db = null;

export async function openDB() {
  if (_db) return _db;
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const db = req.result;
      if (!db.objectStoreNames.contains(TRACKS)) {
        const store = db.createObjectStore(TRACKS, { keyPath: 'id', autoIncrement: true });
        store.createIndex('album', 'album', { unique: false });
        store.createIndex('playlist', 'playlist', { unique: false });
      } else {
        // Upgrade from v1: add playlist index
        const tx = e.target.transaction;
        const store = tx.objectStore(TRACKS);
        if (!store.indexNames.contains('playlist')) {
          store.createIndex('playlist', 'playlist', { unique: false });
        }
      }
      if (!db.objectStoreNames.contains(PLAYLISTS)) {
        db.createObjectStore(PLAYLISTS, { keyPath: 'id' });
      }
    };
    req.onsuccess = () => { _db = req.result; resolve(_db); };
    req.onerror = () => reject(req.error);
  });
}

// ── Tracks ──

export async function addTrack(record) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(TRACKS, 'readwrite');
    const req = tx.objectStore(TRACKS).add(record);
    req.onsuccess = () => resolve(req.result);
    tx.onerror = () => reject(tx.error);
  });
}

export async function getAllTracks() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(TRACKS, 'readonly');
    const req = tx.objectStore(TRACKS).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function getTrack(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(TRACKS, 'readonly');
    const req = tx.objectStore(TRACKS).get(id);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function deleteTrack(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(TRACKS, 'readwrite');
    tx.objectStore(TRACKS).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

// ── Playlists ──

export async function addPlaylist(record) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(PLAYLISTS, 'readwrite');
    tx.objectStore(PLAYLISTS).put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

export async function getAllPlaylists() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(PLAYLISTS, 'readonly');
    const req = tx.objectStore(PLAYLISTS).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function deletePlaylist(id) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction([PLAYLISTS, TRACKS], 'readwrite');
    tx.objectStore(PLAYLISTS).delete(id);
    // Also delete all tracks in this playlist
    const store = tx.objectStore(TRACKS);
    const idx = store.index('playlist');
    const cursor = idx.openCursor(IDBKeyRange.only(id));
    cursor.onsuccess = () => {
      const c = cursor.result;
      if (c) { c.delete(); c.continue(); }
    };
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
