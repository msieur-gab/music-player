import { Library } from './components/library.js';
import { Tracklist } from './components/tracklist.js';
import { Player } from './components/player.js';
import { Downloader } from './components/downloader.js';
import { Cast } from './components/cast.js';
import { formatTime } from './utils/format.js';

const gridEl = document.getElementById('card-grid');
const library = new Library(
  gridEl,
  document.getElementById('nav-tabs'),
  document.getElementById('search-input')
);
const tracklist = new Tracklist(document.getElementById('tracklist'), gridEl);
const player = new Player(document.getElementById('player'));

// On ChromeOS/Crostini, location.origin is the container IP (100.115.92.x)
// which Chromecast can't reach. We need the Chromebook's WiFi LAN IP.
// ChromeOS port-forwards host:8000 → container:8000 automatically.
// Persist the LAN IP in localStorage so user only sets it once.
function getCastHost() {
  const saved = localStorage.getItem('cast-lan-ip');
  if (saved) return `http://${saved}:${location.port}`;

  // If we're already on a LAN IP (not Crostini), use it directly
  if (!location.hostname.startsWith('100.115.') && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
    return location.origin;
  }

  // Prompt once for the LAN IP
  const ip = prompt(
    'Chromecast needs your Chromebook WiFi IP to stream audio.\n' +
    'Find it in: ChromeOS Settings > Network > WiFi > your network\n\n' +
    'Enter your WiFi IP (e.g. 192.168.86.38):'
  );
  if (ip && ip.trim()) {
    localStorage.setItem('cast-lan-ip', ip.trim());
    return `http://${ip.trim()}:${location.port}`;
  }
  return location.origin;
}

const castHost = getCastHost();
const cast = new Cast(castHost);

// UI elements for direct control during casting
const seekBar = document.getElementById('seek-bar');
const currentTimeEl = document.getElementById('current-time');
const durationEl = document.getElementById('duration');
const btnPlay = document.getElementById('btn-play');
const volumeEl = document.getElementById('volume');

// Pause/resume local audio when casting starts/stops
cast.onCastingChanged = (isCasting) => {
  if (isCasting) {
    player.audio.pause();
    btnPlay.textContent = '⏸';
  } else if (player.currentIndex >= 0) {
    player.audio.play();
  }
};

// Update seek bar and time display from Chromecast status
cast.onStatusUpdate = (status) => {
  if (player._seeking) return;
  const pct = status.duration ? (status.currentTime / status.duration) * 100 : 0;
  seekBar.value = isFinite(pct) ? pct : 0;
  currentTimeEl.textContent = formatTime(status.currentTime);
  durationEl.textContent = formatTime(status.duration);

  if (status.playerState === 'PLAYING') {
    btnPlay.textContent = '⏸';
  } else if (status.playerState === 'PAUSED') {
    btnPlay.textContent = '▶';
  }
};

// Intercept play/pause button — route to Cast when casting
btnPlay.addEventListener('click', (e) => {
  if (cast.isCasting) {
    e.stopImmediatePropagation();
    cast.togglePlay();
  }
}, true);

// Intercept seek bar — route to Cast when casting
seekBar.addEventListener('change', (e) => {
  if (cast.isCasting) {
    e.stopImmediatePropagation();
    const status = cast.getStatus();
    if (status && status.duration) {
      const time = (parseFloat(seekBar.value) / 100) * status.duration;
      cast.seek(time);
    }
    player._seeking = false;
  }
}, true);

// Intercept volume — route to Cast when casting
volumeEl.addEventListener('input', (e) => {
  if (cast.isCasting) {
    e.stopImmediatePropagation();
    cast.setVolume(parseFloat(volumeEl.value));
  }
}, true);

// Wire library card click → tracklist
document.addEventListener('album-selected', (e) => {
  tracklist.show(e.detail);
});

// Wire tracklist → player
document.addEventListener('track-selected', (e) => {
  const { artist, album, tracks, index } = e.detail;
  player.loadAlbum(artist, album, tracks, index);
});

// Wire player → tracklist highlight + cast/media session
document.addEventListener('track-change', (e) => {
  tracklist.highlightTrack(e.detail.index);

  const track = player.playlist[e.detail.index];
  if (!track) return;

  const match = track.file.match(/^\d+\s*-\s*(.+)\.mp3$/i);
  const title = match ? match[1] : track.file;
  const coverUrl = `/music/${encodeURIComponent(track.artist)}/${encodeURIComponent(track.album)}/cover.jpg`;

  cast.setTrack({
    title,
    artist: track.artist,
    album: track.album,
    coverUrl,
    mediaUrl: track.url,
    duration: player.audio.duration || 0,
  }, {
    onPlay: () => player.togglePlay(),
    onPause: () => player.togglePlay(),
    onNext: () => player.next(),
    onPrev: () => player.prev(),
    onSeek: (time) => { player.audio.currentTime = time; },
  });

  // If casting, mute local playback — Chromecast handles the audio
  if (cast.isCasting) {
    player.audio.pause();
  }
});

// Update media session state (only when not casting)
player.audio.addEventListener('play', () => {
  if (!cast.isCasting) cast.updatePlaybackState('playing');
});
player.audio.addEventListener('pause', () => {
  if (!cast.isCasting) cast.updatePlaybackState('paused');
});
player.audio.addEventListener('timeupdate', () => {
  if (!cast.isCasting) cast.updatePosition(player.audio.currentTime, player.audio.duration);
});

// Wire downloader → refresh library on completion
new Downloader(
  document.getElementById('download-form'),
  document.getElementById('download-status'),
  () => library.load()
);

// Initial load
library.load();
