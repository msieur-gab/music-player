/**
 * TrackStore — singleton shared data service for all track data.
 *
 * Fetches /api/tracks once, flattens cls_json, resolves cover URLs
 * from /api/library album data. View addons and core components
 * share the same data — no duplicate fetches.
 *
 * Usage:
 *   import { trackStore } from '../services/track-store.js';
 *   await trackStore.load();
 *   const tracks = trackStore.getAll();
 *   const results = trackStore.search('sakamoto');
 */

class TrackStore {
  constructor() {
    this._tracks = [];
    this._coverMap = {};   // "artist/album" → cover URL
    this._loaded = false;
    this._loading = null;  // dedup concurrent load() calls
  }

  /** Load tracks + covers. Safe to call multiple times — deduplicates. */
  async load() {
    if (this._loaded) return;
    if (this._loading) return this._loading;

    this._loading = this._doLoad();
    await this._loading;
    this._loading = null;
  }

  async _doLoad() {
    try {
      // Fetch tracks and library in parallel
      const [tracksRes, libraryRes] = await Promise.all([
        fetch('/api/tracks?per_page=10000').then(r => r.json()),
        fetch('/api/library').then(r => r.json()),
      ]);

      // Build cover map from library
      const albums = Array.isArray(libraryRes) ? libraryRes : [];
      for (const album of albums) {
        if (album.cover) {
          this._coverMap[`${album.artist}/${album.album}`] = album.cover;
        }
      }

      // Flatten cls_json and attach covers + url
      const rows = tracksRes.tracks || tracksRes;
      this._tracks = rows.map(t => {
        const cls = typeof t.cls_json === 'string'
          ? JSON.parse(t.cls_json)
          : (t.cls_json || {});

        const cover = this._coverMap[`${t.artist}/${t.album}`] || null;
        const url = `/music/${(t.file || '').split('/').map(s => encodeURIComponent(s)).join('/')}`;

        return { ...t, ...cls, cover, url };
      });

      this._loaded = true;
    } catch (e) {
      console.error('TrackStore: load failed', e);
    }
  }

  /** Force reload (after analyze or download). */
  async refresh() {
    this._loaded = false;
    this._loading = null;
    await this.load();
  }

  /** All tracks with flattened cls + cover + url. */
  getAll() {
    return this._tracks;
  }

  /** Find track by track_id. */
  getById(trackId) {
    return this._tracks.find(t => t.track_id === trackId) || null;
  }

  /** Search tracks by title/artist/album. */
  search(query, limit = 20) {
    if (!query || query.length < 2) return [];
    const q = query.toLowerCase();
    const results = [];
    for (const t of this._tracks) {
      const hay = `${t.title || ''} ${t.artist || ''} ${t.album || ''}`.toLowerCase();
      if (hay.includes(q)) {
        results.push(t);
        if (results.length >= limit) break;
      }
    }
    return results;
  }

  /** Resolve cover URL for an artist/album pair. */
  getCover(artist, album) {
    return this._coverMap[`${artist}/${album}`] || null;
  }

  get loaded() { return this._loaded; }
  get count() { return this._tracks.length; }
}

export const trackStore = new TrackStore();
