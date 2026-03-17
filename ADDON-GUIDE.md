# MusiCast Addon Development Guide

Build view addons that let users explore their music library in new ways.
Your addon is a canvas — the app handles everything else.

---

## What You Build vs What the App Provides

| Concern | Your addon | The app |
|---------|-----------|---------|
| Visualization | Canvas, SVG, WebGL — your choice | Provides the feed area |
| Discovery / filtering | Your algorithms, your interaction | Provides track data via TrackStore |
| Track list | Emit `addon-playlist` event | Renders in album-detail panel |
| Playback | Emit `addon-play` event | PlaybackController handles local + cast |
| Theme | Read CSS vars from `:root` | Injects vars + notifies on toggle |
| Cover art | Included in track data | Resolved by TrackStore from library |

**Rule**: your addon is the visualization only. No playlist sidebar, no player bar, no audio element.

---

## Addon Structure

```
addons/
  your-addon/
    manifest.json
    ui/
      your-addon.js     ← web component (shadow DOM)
      styles.css        ← optional, imported by your component
```

### manifest.json

```json
{
  "id": "your-addon",
  "name": "Your Addon Name",
  "version": "1.0.0",
  "type": "view",
  "autoload": false,
  "description": "One-line description shown in the addon manager",
  "ui": {
    "component": "your-addon",
    "entry": "ui/your-addon.js",
    "trigger": {
      "slot": "rail",
      "label": "Tooltip text",
      "icon": "<svg viewBox=\"0 0 24 24\">...</svg>"
    }
  }
}
```

- `type: "view"` — renders in the main feed area as a navigation tab
- `autoload: false` — users enable via the addon manager (jigsaw icon)
- `trigger.slot: "rail"` — adds a tab button to the left navigation rail
- `trigger.icon` — inline SVG, 24x24 viewBox, stroke-based (matches app style)

### Backend Addons

Backend addons add Python API routes. See `addons/downloader/` and `addons/chromecast/` for examples. They use `type: "backend"`, declare `deps` for pip packages, and expose a `register(ctx)` function that returns routes.

---

## Web Component Template

```js
const tpl = document.createElement('template');
tpl.innerHTML = `
<style>
:host {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
  font-family: var(--font);
  -webkit-user-select: none;
  user-select: none;
}
/* Your styles here — use var(--token) for all colors */
</style>

<div class="your-layout">
  <canvas id="cv"></canvas>
</div>
`;

class YourAddon extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.shadowRoot.appendChild(tpl.content.cloneNode(true));
  }

  connectedCallback() {
    this._loadTracks();
    this._setupInteraction();

    // Redraw on theme change
    new MutationObserver(() => requestAnimationFrame(() => this._draw()))
      .observe(document.documentElement, {
        attributes: true,
        attributeFilter: ['data-theme']
      });
  }

  async _loadTracks() {
    // Use shared TrackStore (loaded by main app)
    const mod = await import('/js/services/track-store.js').catch(() => null);
    if (mod?.trackStore) {
      await mod.trackStore.load();
      this._tracks = mod.trackStore.getAll();
    } else {
      // Fallback: direct fetch (SDK test mode)
      const r = await fetch('/api/tracks?per_page=10000');
      const data = await r.json();
      this._tracks = (data.tracks || data).map(t => {
        const cls = typeof t.cls_json === 'string'
          ? JSON.parse(t.cls_json) : (t.cls_json || {});
        return { ...t, ...cls };
      });
    }
  }

  // ... your visualization + interaction logic ...
}

customElements.define('your-addon', YourAddon);
```

---

## Events — The Contract

### Events You Emit (addon → app)

#### `addon-playlist`
Show a track list in the app's detail panel. Emit when the user's interaction produces a selection (seed, filter, path).

```js
this.dispatchEvent(new CustomEvent('addon-playlist', {
  bubbles: true, composed: true,
  detail: {
    label: 'Similar to Merry Christmas Mr. Lawrence',
    desc: 'Ryuichi Sakamoto · Contemplative',
    tracks: [
      {
        file: 'Artist/Album/01 - Title.m4a',
        title: 'Title',
        artist: 'Artist',
        album: 'Album',
        cover: '/music/Artist/Album/cover.jpg',  // or null
        url: '/music/Artist/Album/01%20-%20Title.m4a',
      },
      // ...
    ],
  },
}));
```

#### `addon-play`
Start playback immediately. Emit when the user clicks a specific track.

```js
this.dispatchEvent(new CustomEvent('addon-play', {
  bubbles: true, composed: true,
  detail: {
    tracks: [ /* same format as addon-playlist */ ],
    index: 3,  // which track to start playing
  },
}));
```

### Events You Receive (app → addon, optional)

#### `highlight-track` (future)
The app will notify which track is currently playing so you can highlight it in your visualization.

```js
// Not yet implemented — planned for next iteration
this.addEventListener('highlight-track', (e) => {
  const url = e.detail.url;
  // highlight the matching track in your visualization
});
```

---

## Track Data Shape

Tracks from TrackStore have all fields flattened:

```js
{
  // Identity
  track_id: 'Artist::Album::Title',
  artist: 'Ryuichi Sakamoto',
  album: '12',
  title: 'Merry Christmas Mr. Lawrence',
  file: 'Ryuichi Sakamoto/12/04 - Merry Christmas Mr. Lawrence.m4a',

  // Resolved by TrackStore
  url: '/music/Ryuichi%20Sakamoto/12/04%20-%20Merry%20Christmas%20Mr.%20Lawrence.m4a',
  cover: '/music/Ryuichi%20Sakamoto/12/cover.jpg',

  // Audio features (25 scalars)
  duration: 317.09, tempo: 95.70, key: 0, mode: 1,
  rms_mean: 13.93, centroid_mean: 1396.48, // ... etc

  // Classifier outputs (0-1, the main currency)
  arousal: 0.38, valence: 0.57,
  happy: 0.54, sad: 0.46, relaxed: 0.58,
  aggressive: 0.42, danceable: 0.56, party: 0.50,
  energetic: 0.40, still: 0.60,
  hypnotic: 0.60, varied: 0.40,
  instrumental: 0.44, vocal: 0.56,
  brilliant: 0.50, warm: 0.50,
  radiant: 0.63, somber: 0.37,
  contemplative: 0.55, restless: 0.45,

  // Optional
  genre: ['jazz', 'contemporary jazz'],
}
```

### Classifier Keys for Visualization

These are the 20 human-readable scores (all 0-1) you'll use most:

| Key | Meaning | Opposite |
|-----|---------|----------|
| `arousal` | Perceived urgency/activation | low = calm |
| `valence` | Perceived positivity | low = dark/negative |
| `happy` | Happiness/joy | — |
| `sad` | Sadness/melancholy | — |
| `relaxed` | Calm/restful | — |
| `aggressive` | Harshness/intensity | — |
| `danceable` | Want-to-move quality | — |
| `party` | Club/party energy | — |
| `energetic` | Kinetic energy | `still` |
| `hypnotic` | Repetitive/trance quality | `varied` |
| `instrumental` | Absence of vocals | `vocal` |
| `brilliant` | Spectral brightness (timbre) | `warm` |
| `radiant` | Atmospheric brightness (mood) | `somber` |
| `contemplative` | Reflective depth | `restless` |

---

## Theme Tokens

Use CSS custom properties for all colors. The app injects them into your element and updates on theme toggle. Canvas drawing should read from `document.documentElement`:

```js
_draw() {
  const style = getComputedStyle(document.documentElement);
  const bg = style.getPropertyValue('--bg').trim();
  const text = style.getPropertyValue('--text').trim();
  const accent = style.getPropertyValue('--accent').trim();
  // ...
}
```

### Available Tokens

| Token | Light | Dark | Usage |
|-------|-------|------|-------|
| `--bg` | `#f7f7f5` | `#121212` | Main background |
| `--bg-raised` | `#ffffff` | `#1e1e1e` | Cards, panels |
| `--bg-hover` | `#eeeeec` | `#2a2a2a` | Hover state |
| `--border` | `#ddd` | `#333` | Borders, dividers |
| `--text` | `#1a1a1a` | `#e0e0e0` | Primary text |
| `--text-muted` | `#666` | `#999` | Secondary text |
| `--text-faint` | `#999` | `#555` | Tertiary text |
| `--accent` | `#e8621a` | `#f0802a` | Brand orange |
| `--accent-light` | `rgba(232,98,26,0.08)` | `rgba(240,128,42,0.1)` | Accent bg |
| `--radius` | `8px` | `8px` | Border radius |

---

## SDK Test Harness

For developing addons without the full MusiCast app, use the test harness:

```
addons/sdk/
  test-harness.html    ← drop-in test page
  mock-tracks.json     ← sample track data with cls scores
```

### test-harness.html

Provides:
- A minimal app shell (nav rail with your addon tab + a few core tabs)
- A working `album-detail` panel that opens on `addon-playlist`
- A `now-playing` bar wired to PlaybackController
- Theme toggle (light/dark)
- TrackStore loaded with mock data (or connected to a live server)
- Sample music files for playback testing (CC-licensed)

### Usage

```bash
# Option 1: Test against the live MusiCast server (needs analyzed library)
cd music-player
python3 server.py
# Open http://localhost:8000/addons/sdk/test-harness.html?addon=your-addon

# Option 2: Test with mock data only (no server needed)
# Serve the addons/sdk/ directory with any static server
npx serve addons/sdk
# Open http://localhost:3000/test-harness.html?addon=your-addon&mock=true
```

### Mock Track Data

`mock-tracks.json` contains ~50 sample tracks with realistic classifier outputs spanning all quadrants of the arousal/valence space. No audio files — playback is simulated in mock mode.

---

## Checklist Before Shipping

- [ ] Web component with shadow DOM
- [ ] Uses CSS vars for all colors (no hardcoded hex in canvas)
- [ ] Reads tracks from TrackStore (with direct-fetch fallback)
- [ ] Emits `addon-playlist` for track lists (no built-in sidebar)
- [ ] Emits `addon-play` for direct playback (no built-in audio)
- [ ] Redraws canvas on theme change (MutationObserver on `data-theme`)
- [ ] `manifest.json` with `type: "view"`, trigger icon, description
- [ ] Works in both light and dark themes
- [ ] Touch interaction works (pinch zoom, pan, tap)
- [ ] Tested with SDK harness or live server

---

## Reference: Existing Addons

| Addon | Type | What it does |
|-------|------|-------------|
| `chromecast` | backend | Cast to Chromecast devices |
| `downloader` | backend | Download from YouTube Music |
| `sonic-sunburst` | view | Seed a track → similarity rings with emotional wedges |

36 prototype view addons are available in `~/soniq-player/` — all candidates for migration using this guide.
