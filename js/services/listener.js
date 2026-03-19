/**
 * Active listener state management.
 * Persists in sessionStorage — cleared when tab closes.
 * Every app open shows the gate; one tap and you're in.
 */

const STORAGE_KEY = 'musicast-listener';

let _active = null;

function _load() {
  if (_active) return _active;
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (raw) _active = JSON.parse(raw);
  } catch { /* corrupted */ }
  return _active;
}

export function getActiveListener() {
  return _load();
}

export function getListenerId() {
  const l = _load();
  return l?.id || null;
}

export function setActiveListener(listener) {
  _active = listener;
  if (listener) {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(listener));
  } else {
    sessionStorage.removeItem(STORAGE_KEY);
  }
  document.dispatchEvent(new CustomEvent('listener-change', { detail: listener }));
}

export function clearListener() {
  _active = null;
  sessionStorage.removeItem(STORAGE_KEY);
  document.dispatchEvent(new CustomEvent('listener-change', { detail: null }));
}
