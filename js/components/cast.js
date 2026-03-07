/**
 * Chromecast via Google Cast Web Sender SDK (Default Media Receiver)
 * + Media Session API for OS-level controls.
 *
 * On ChromeOS/Crostini, location.origin points to the container IP which
 * Chromecast devices can't reach. We need the Chromebook's actual WiFi IP.
 * ChromeOS port-forwards from the host to the container, so media URLs
 * must use the host's LAN IP.
 */

const DEFAULT_RECEIVER = 'CC1AD845';

export class Cast {
  constructor(mediaBaseUrl) {
    this._session = null;
    this._currentTrack = null;
    this._mediaBaseUrl = mediaBaseUrl;
    this.isCasting = false;
    this.onCastingChanged = null; // callback(isCasting)
    this._initCast();
  }

  _initCast() {
    window['__onGCastApiAvailable'] = (isAvailable) => {
      if (!isAvailable) {
        console.warn('[cast] Cast SDK not available');
        return;
      }
      console.log('[cast] Cast SDK ready');

      cast.framework.CastContext.getInstance().setOptions({
        receiverApplicationId: DEFAULT_RECEIVER,
        autoJoinPolicy: chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED,
      });

      cast.framework.CastContext.getInstance().addEventListener(
        cast.framework.CastContextEventType.SESSION_STATE_CHANGED,
        (e) => {
          console.log('[cast] Session state:', e.sessionState);
          if (e.sessionState === cast.framework.SessionState.SESSION_STARTED ||
              e.sessionState === cast.framework.SessionState.SESSION_RESUMED) {
            this._session = cast.framework.CastContext.getInstance().getCurrentSession();
            this.isCasting = true;
            if (this.onCastingChanged) this.onCastingChanged(true);
            if (this._currentTrack) this._loadOnCast();
          } else if (e.sessionState === cast.framework.SessionState.SESSION_ENDED) {
            this._session = null;
            this.isCasting = false;
            this._stopPolling();
            if (this.onCastingChanged) this.onCastingChanged(false);
          }
        }
      );
    };
  }

  setTrack({ title, artist, album, coverUrl, mediaUrl, duration }, callbacks) {
    this._currentTrack = { title, artist, album, coverUrl, mediaUrl };
    this._setupMediaSession({ title, artist, album, coverUrl, duration }, callbacks);
    if (this._session) this._loadOnCast();
  }

  _loadOnCast() {
    if (!this._session || !this._currentTrack) return;
    const { title, artist, album, coverUrl, mediaUrl } = this._currentTrack;

    // Build absolute URL using the configured base (LAN IP)
    const absoluteMediaUrl = this._mediaBaseUrl + mediaUrl;
    const absoluteCoverUrl = coverUrl ? this._mediaBaseUrl + coverUrl : null;

    console.log('[cast] Loading media:', absoluteMediaUrl);

    const mediaInfo = new chrome.cast.media.MediaInfo(absoluteMediaUrl, 'audio/mpeg');
    mediaInfo.metadata = new chrome.cast.media.MusicTrackMediaMetadata();
    mediaInfo.metadata.title = title;
    mediaInfo.metadata.artist = artist;
    mediaInfo.metadata.albumName = album;
    if (absoluteCoverUrl) {
      mediaInfo.metadata.images = [new chrome.cast.Image(absoluteCoverUrl)];
    }

    const request = new chrome.cast.media.LoadRequest(mediaInfo);
    request.autoplay = true;

    this._session.loadMedia(request).then(
      () => {
        console.log('[cast] Now playing:', title);
        this._startPolling();
      },
      (err) => console.error('[cast] Load error:', chrome.cast.ErrorCode[err.code] || err)
    );
  }

  _getMedia() {
    if (!this._session) return null;
    return this._session.getMediaSession();
  }

  seek(time) {
    const media = this._getMedia();
    if (!media) return;
    const request = new chrome.cast.media.SeekRequest();
    request.currentTime = time;
    media.seek(request);
  }

  setVolume(level) {
    if (!this._session) return;
    this._session.setVolume(level);
  }

  togglePlay() {
    const media = this._getMedia();
    if (!media) return;
    if (media.playerState === chrome.cast.media.PlayerState.PLAYING) {
      media.pause();
    } else {
      media.play();
    }
  }

  getStatus() {
    const media = this._getMedia();
    if (!media) return null;
    return {
      currentTime: media.getEstimatedTime(),
      duration: media.media?.duration || 0,
      playerState: media.playerState,
    };
  }

  _startPolling() {
    this._stopPolling();
    this._pollId = setInterval(() => {
      if (!this.isCasting) { this._stopPolling(); return; }
      const status = this.getStatus();
      if (status && this.onStatusUpdate) this.onStatusUpdate(status);
    }, 500);
  }

  _stopPolling() {
    if (this._pollId) { clearInterval(this._pollId); this._pollId = null; }
  }

  _setupMediaSession({ title, artist, album, coverUrl, duration }, callbacks) {
    if (!('mediaSession' in navigator)) return;

    navigator.mediaSession.metadata = new MediaMetadata({
      title, artist, album,
      artwork: coverUrl ? [{ src: coverUrl, sizes: '512x512', type: 'image/jpeg' }] : [],
    });
    navigator.mediaSession.playbackState = 'playing';

    if (callbacks) {
      navigator.mediaSession.setActionHandler('play', callbacks.onPlay || null);
      navigator.mediaSession.setActionHandler('pause', callbacks.onPause || null);
      navigator.mediaSession.setActionHandler('previoustrack', callbacks.onPrev || null);
      navigator.mediaSession.setActionHandler('nexttrack', callbacks.onNext || null);
      if (callbacks.onSeek) {
        navigator.mediaSession.setActionHandler('seekto', (d) => callbacks.onSeek(d.seekTime));
      }
    }
  }

  updatePlaybackState(state) {
    if ('mediaSession' in navigator) navigator.mediaSession.playbackState = state;
  }

  updatePosition(position, duration) {
    if ('mediaSession' in navigator && navigator.mediaSession.setPositionState) {
      navigator.mediaSession.setPositionState({
        duration: duration || 0,
        position: position || 0,
        playbackRate: 1,
      });
    }
  }
}
