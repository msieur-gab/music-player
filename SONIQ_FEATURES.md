# Soniq Audio Features — What They Measure and How They're Used

## Scalar Features (15)

### Rhythm & Tempo

| Feature | What it captures | Example |
|---------|-----------------|---------|
| **tempo** | BPM — how fast the pulse is | 60 = slow ballad, 140 = driving |
| **onset_strength** | How hard notes/hits attack | Soft piano = low, sharp drums = high |
| **beat_strength** | How prominent the rhythmic pulse is | Ambient pad = low, funk groove = high |

Used in: Sleep (wants low), Energy (wants high), Focus (wants moderate)

### Loudness & Dynamics

| Feature | What it captures | Example |
|---------|-----------------|---------|
| **rms_mean** | Average loudness across the track | Whisper-quiet vs wall-of-sound |
| **rms_max** | Loudest peak moment | Tracks with big climaxes score high |
| **rms_variance** | How much the loudness changes over time | Steady drone = low, build-and-drop = high |
| **dynamic_range** | Gap between quietest and loudest (dB) | Compressed pop = small, orchestral = large |

Used in: Sleep/Recovery (wants quiet, steady), Energy (wants loud), Melancholy (moderate variance — emotional swells)

### Timbre & Tone Color

| Feature | What it captures | Example |
|---------|-----------------|---------|
| **centroid_mean** | Spectral brightness — where the energy sits in the frequency spectrum | Dark bass = low Hz, bright cymbals = high Hz |
| **flatness_mean** | Noise vs tone (0 = pure tone, 1 = white noise) | Piano chord = low, distorted texture = high |
| **spectral_flux** | How fast the frequency content changes frame-to-frame | Sustained pad = low, busy drums = high |
| **zcr_mean** | Zero-crossing rate — how often the waveform crosses silence | Clean bass = low, noisy/percussive = high |

Used in: Mysterious (wants dark, noisy), Focus (wants bright, changing), Calm (wants warm, steady)

### Vocal & Duration

| Feature | What it captures | Example |
|---------|-----------------|---------|
| **vocal_proxy** | Estimate of vocal presence (mid-frequency energy ratio) | Instrumental = low, vocal-heavy = high |
| **duration** | Track length in seconds | Used for playlist duration display |

Used in: Sleep/Recovery (wants low vocal), Joy (tolerates vocal)

---

## Vector Features (33 dimensions)

### MFCC Mean (13 dimensions)

**What:** Mel-Frequency Cepstral Coefficients — the timbral fingerprint of a track. Captures *what the track sounds like* in terms of instrument texture, room character, and harmonic content.

**How it works:** The audio spectrum is mapped onto the mel scale (how humans perceive pitch), then compressed into 13 coefficients that describe the overall spectral shape.

**Used in:** `find_similar()` — two tracks with close MFCC means sound alike (e.g. solo piano vs solo piano, dense orchestra vs dense orchestra).

### MFCC Std (13 dimensions)

**What:** How much the timbre varies over time. A track with low MFCC std sounds the same throughout; high std means the texture changes a lot.

**Used in:** `find_similar()` — distinguishes a steady drone from a track that evolves through different textures, even if their average timbre is similar.

### Spectral Contrast (7 dimensions)

**What:** The difference between peaks and valleys in the spectrum across 7 frequency bands. Captures harmonic richness — how much tonal content stands out from the noise floor.

**Used in:** `find_similar()` — separates clean harmonic music (jazz piano) from dense textured music (electronic layers), even when average brightness is similar.

---

## How Features Drive Recommendations

### Zone Playlists

Each zone (Sleep, Energy, Focus, etc.) has a **target vector** of 10 normalized scalar features. Every track is scored against each target using **inverse Euclidean distance**:

```
score = 1 / (1 + distance_from_target)
```

Closer to the target = higher score. Only tracks scoring above 0.50 make it into a zone playlist.

The 10 features used for zone matching:
`tempo`, `rms_mean`, `dynamic_range`, `centroid_mean`, `flatness_mean`, `spectral_flux`, `onset_strength`, `beat_strength`, `rms_variance`, `vocal_proxy`

### Find Similar

When you click "find similar" on a track, it builds a **43-dimension vector** combining all three feature groups:

- 10 scalar features (min-max normalized)
- 13 MFCC means (z-score normalized)
- 13 MFCC stds (z-score normalized)
- 7 spectral contrast (z-score normalized)

All components are normalized to the same scale so no single group dominates. Tracks are ranked by inverse Euclidean distance — the seed track scores 1.0, and the closest matches appear next.

This means "find similar" considers **everything**: rhythm, loudness, brightness, timbre, texture, and harmonic structure — not just one dimension.
