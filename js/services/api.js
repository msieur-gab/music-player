import { getListenerId } from './listener.js';

const BASE = '';

/** Headers with listener identity for per-listener state scoping. */
export function listenerHeaders() {
  const lid = getListenerId();
  const h = { 'Content-Type': 'application/json' };
  if (lid) h['X-Listener-Id'] = lid;
  return h;
}

export async function fetchLibrary() {
  const r = await fetch(`${BASE}/api/library`);
  return r.json();
}

export async function fetchDevices() {
  const r = await fetch(`${BASE}/api/devices`, { headers: listenerHeaders() });
  return r.json();
}

export async function fetchStatus() {
  const r = await fetch(`${BASE}/api/status`, { headers: listenerHeaders() });
  return r.json();
}

export async function castTrack(deviceId, track, queue = null, queueIndex = 0, baseUrl = null) {
  const r = await fetch(`${BASE}/api/cast`, {
    method: 'POST',
    headers: listenerHeaders(),
    body: JSON.stringify({ deviceId, track, queue, queueIndex, baseUrl }),
  });
  return r.json();
}

export async function fetchConfig() {
  const r = await fetch(`${BASE}/api/config`);
  return r.json();
}

export async function updateConfig(data) {
  const r = await fetch(`${BASE}/api/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return r.json();
}

export async function browseFolders(path = '') {
  const q = path ? `?path=${encodeURIComponent(path)}` : '';
  const r = await fetch(`${BASE}/api/browse${q}`);
  return r.json();
}

export async function controlPlayback(action, value = null) {
  const r = await fetch(`${BASE}/api/control`, {
    method: 'POST',
    headers: listenerHeaders(),
    body: JSON.stringify({ action, value }),
  });
  return r.json();
}

export async function startDownload(url) {
  const r = await fetch(`${BASE}/api/download`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  return r.json();
}

export function streamJob(id) {
  return new EventSource(`${BASE}/api/download/${id}`);
}

export async function startAnalysis() {
  const r = await fetch(`${BASE}/api/analyze`, { method: 'POST' });
  return r.json();
}

export function streamAnalysis(id) {
  return new EventSource(`${BASE}/api/analyze/${id}`);
}

export async function fetchSimilar(artist, album, title, limit = 10) {
  const key = `${artist}::${album}::${title}`;
  const r = await fetch(`${BASE}/api/similar?key=${encodeURIComponent(key)}&limit=${limit}`);
  return r.json();
}

export async function fetchZones() {
  const r = await fetch(`${BASE}/api/zones`);
  return r.json();
}

export async function fetchPlaylist(zone, limit = 25) {
  const r = await fetch(`${BASE}/api/playlist?zone=${encodeURIComponent(zone)}&limit=${limit}`);
  return r.json();
}

export async function fetchSavedPlaylists() {
  const r = await fetch(`${BASE}/api/playlists`, { headers: listenerHeaders() });
  return r.json();
}

export async function fetchSavedPlaylist(id) {
  const r = await fetch(`${BASE}/api/playlists/${id}`, { headers: listenerHeaders() });
  return r.json();
}

export async function savePlaylistApi(name, zone, tracks) {
  const r = await fetch(`${BASE}/api/playlists`, {
    method: 'POST',
    headers: listenerHeaders(),
    body: JSON.stringify({ name, zone, tracks }),
  });
  return r.json();
}

export async function deleteSavedPlaylist(id) {
  const r = await fetch(`${BASE}/api/playlists/${id}`, { method: 'DELETE', headers: listenerHeaders() });
  return r.json();
}
