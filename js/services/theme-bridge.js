/**
 * Theme bridge — injects host CSS variables into addon shadow roots.
 *
 * Shadow DOM isolates CSS, so addon components don't inherit :root vars.
 * This module reads the computed theme tokens and sets them on addon elements.
 *
 * Usage:
 *   import { applyTheme, onThemeChange } from '../services/theme-bridge.js';
 *   applyTheme(addonElement);
 *   onThemeChange(() => applyTheme(addonElement));
 */

const TOKEN_KEYS = [
  '--bg', '--bg-raised', '--bg-hover', '--bg-active',
  '--border',
  '--text', '--text-muted', '--text-faint',
  '--accent', '--accent-light', '--accent-text',
  '--shadow-sm', '--shadow-md', '--shadow-lg',
  '--radius', '--radius-lg',
  '--font', '--font-mono',
  '--transition',
  '--player-bg', '--player-text', '--player-muted', '--player-accent',
];

/** Read current theme tokens from document root. */
function _readTokens() {
  const style = getComputedStyle(document.documentElement);
  const tokens = {};
  for (const key of TOKEN_KEYS) {
    const val = style.getPropertyValue(key).trim();
    if (val) tokens[key] = val;
  }
  return tokens;
}

/** Apply current theme tokens to an element (sets CSS custom properties). */
export function applyTheme(element) {
  const tokens = _readTokens();
  for (const [key, val] of Object.entries(tokens)) {
    element.style.setProperty(key, val);
  }
}

/** Apply theme to multiple elements. */
export function applyThemeAll(elements) {
  const tokens = _readTokens();
  for (const el of elements) {
    for (const [key, val] of Object.entries(tokens)) {
      el.style.setProperty(key, val);
    }
  }
}

/** Register a callback for theme changes. Uses MutationObserver on data-theme. */
const _listeners = new Set();
let _observerStarted = false;

export function onThemeChange(callback) {
  _listeners.add(callback);

  if (!_observerStarted) {
    _observerStarted = true;
    const observer = new MutationObserver(() => {
      // Small delay to let CSS recompute
      requestAnimationFrame(() => {
        for (const fn of _listeners) fn();
      });
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
  }

  return () => _listeners.delete(callback);
}
