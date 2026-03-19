/**
 * Favorites service — per-listener track bookmarking.
 * Caches favorite IDs as a Set for instant UI lookups.
 */

import { getListenerId } from './listener.js';

let _ids = new Set();
let _loaded = false;

export async function loadFavorites() {
  const lid = getListenerId();
  if (!lid) {
    _ids = new Set();
    _loaded = true;
    return;
  }

  try {
    const r = await fetch(`/api/favorites/ids?listener=${encodeURIComponent(lid)}`);
    const ids = await r.json();
    _ids = new Set(ids);
  } catch {
    _ids = new Set();
  }
  _loaded = true;
}

export function isFavorite(trackId) {
  return _ids.has(trackId);
}

export async function toggleFavorite(trackId) {
  const lid = getListenerId();
  if (!lid) return false;

  const wasFav = _ids.has(trackId);
  const method = wasFav ? 'DELETE' : 'POST';

  // Optimistic update
  if (wasFav) _ids.delete(trackId);
  else _ids.add(trackId);

  try {
    const r = await fetch('/api/favorites', {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ listener_id: lid, track_id: trackId }),
    });
    if (!r.ok) {
      // Rollback on failure
      if (wasFav) _ids.add(trackId);
      else _ids.delete(trackId);
    }
  } catch {
    // Rollback on error
    if (wasFav) _ids.add(trackId);
    else _ids.delete(trackId);
  }

  return !wasFav; // new state
}

export function getFavoriteIds() {
  return _ids;
}

// Reload cache when listener changes
document.addEventListener('listener-change', () => {
  loadFavorites().then(() => {
    document.dispatchEvent(new CustomEvent('favorites-loaded'));
  });
});
