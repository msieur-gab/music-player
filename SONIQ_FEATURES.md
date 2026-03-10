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

## Vector Features (51 dimensions)

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

### Chroma (12 dimensions) — added in v0.2

**What:** Energy distribution across the 12 pitch classes (C, C#, D, D#, E, F, F#, G, G#, A, A#, B). This is the harmonic fingerprint of a track — which notes dominate the music.

**How it works:** The audio spectrum is folded into a single octave, so all C notes (C2, C3, C4...) are summed into one bin. The result is a 12-dimensional vector showing how much energy each pitch class carries across the whole track.

**Why it was added:** Research shows chroma features are the #1 predictor for **valence** (happy vs sad). Our v0.1 features covered arousal well (tempo, energy, dynamics) but had a blind spot for emotional tone. Meta-analyses show arousal prediction reaches r=0.81 from audio features, but valence only r=0.67 — and chroma is what closes that gap.

**What it captures that we couldn't before:**
- **Major vs minor tonality** — a C major track lights up C, E, G; C minor lights up C, Eb, G
- **Key signature** — which pitch classes dominate tells you the key
- **Harmonic complexity** — simple triads vs dense jazz voicings show different chroma profiles
- **Consonance vs dissonance** — resolved harmony vs tense clusters

**Used in:** Zone playlists (Joy wants major/bright chroma, Melancholy wants minor/dark), `find_similar()` (matches harmonic character), mood classification.

### Tonnetz (6 dimensions) — added in v0.2

**What:** Tonal centroid features that map pitch relationships onto a geometric space of musical intervals. The 6 dimensions represent: fifths (C→G), minor thirds (C→Eb), and major thirds (C→E), each as x/y coordinates.

**How it works:** Derived from chroma features, tonnetz projects harmony onto a network where harmonically related notes are close together. A track rich in perfect fifths and major thirds will have a different tonnetz signature than one built on minor seconds and tritones.

**Why it was added:** While chroma tells you *which notes are present*, tonnetz tells you *how those notes relate to each other*. Research on music emotion recognition shows that harmonic relationships (consonance, tension, resolution) are a stronger predictor of emotional quality than raw pitch content alone. Tonnetz captures this relational structure in just 6 compact dimensions.

**What it captures that chroma alone can't:**
- **Harmonic tension** — tritones and minor seconds vs perfect fifths
- **Tonal stability** — whether the harmony feels resolved or restless
- **Interval patterns** — the character of chord progressions, not just individual chords

**Used in:** `find_similar()` (matches harmonic feel), mood/valence prediction, distinguishing tracks that use the same notes but in very different harmonic contexts.

---

## Research Basis

These feature choices are informed by published research in music information retrieval (MIR):

### What the science says

- **Arousal (energy/intensity) is well-captured by our scalar features.** Tempo, RMS energy, spectral centroid, onset strength, and spectral flux are the strongest predictors. Meta-analysis: r=0.81 from audio alone.

- **Valence (happy/sad) requires harmonic features.** MFCCs contribute to valence detection but chroma and tonnetz are critical. Valence prediction from audio alone reaches r=0.67 — the gap is partly because tonal/harmonic content is harder to extract than energy.

- **MFCCs are the gold standard for timbre similarity** but contribute almost nothing to arousal prediction. Only the first MFCC coefficient showed statistical significance for arousal; the rest are pure timbre.

- **Spectral contrast is particularly effective for genre classification** — it captures rhythmic and harmonic patterns that distinguish musical styles.

- **For context playlists (sleep, focus, energy):** tempo + RMS energy + onset strength alone get 70-80% of the way. The remaining 20-30% comes from dynamics and spectral features.

- **Feature weighting by task matters.** Research strongly supports using different weights depending on the goal:

| Feature Group | Mood/Emotion | Timbre Similarity | Activity Playlist |
|---------------|-------------|-------------------|-------------------|
| Tempo, RMS, onset | High (arousal) | Medium | Very High |
| MFCCs | High (valence) | Very High | Medium |
| Spectral contrast | Medium-High | High | Medium |
| Chroma | High (valence) | Medium | Medium |
| Tonnetz | High (valence) | Medium | Low |
| Spectral flux, flatness | Medium | Medium | High |
| Dynamic range, variance | Medium | Low | High |

### Distance metrics

- **Cosine similarity** is the industry standard for general music recommendation (used by Spotify). It ignores magnitude and focuses on feature "shape."
- **Euclidean distance** is better when absolute levels matter (e.g. matching energy intensity for workout playlists).
- **Mahalanobis distance** accounts for feature correlations (e.g. MFCC dimensions are correlated) — theoretically optimal but computationally heavier.

Our system uses **inverse Euclidean distance** for zone scoring (where absolute feature levels matter) and **z-score normalized Euclidean** for similarity search (where balanced comparison matters).

### Known limitations

- **Temporal structure is lost.** We store means/stds, which discard how features evolve over time. A track that builds from quiet to loud looks the same as one that stays medium.
- **No lyrics analysis.** Research shows lyrics contribute ~20% to emotion recognition.
- **Valence ceiling.** Even with chroma and tonnetz, audio-only valence prediction plateaus around r=0.67. Full accuracy requires multimodal approaches (audio + lyrics + metadata).
- **Deep embeddings outperform handcrafted features** for most tasks, but require GPU inference and large models. Our approach trades some accuracy for portability and interpretability.

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

When you click "find similar" on a track, it builds a **61-dimension vector** combining all five feature groups:

- 10 scalar features (min-max normalized)
- 13 MFCC means (z-score normalized)
- 13 MFCC stds (z-score normalized)
- 7 spectral contrast (z-score normalized)
- 12 chroma (z-score normalized)
- 6 tonnetz (z-score normalized)

All components are normalized to the same scale so no single group dominates. Tracks are ranked by inverse Euclidean distance — the seed track scores 1.0, and the closest matches appear next.

This means "find similar" considers **everything**: rhythm, loudness, brightness, timbre, texture, harmonic content, and tonal relationships — not just one dimension.

### Composite Dimensions (Sonic Filter & Sonic Radar)

Eight human-friendly dimensions derived from the raw Soniq features. These power the
Sonic Filter sliders and the Sonic Radar artist profiles. Each composite combines
multiple raw features with weights — this is the "consumer layer" on top of the
raw extraction, similar to how Spotify exposes Energy/Danceability/etc. but we go
further with Texture, Dynamics, and Stillness (which Spotify doesn't have).

**Feature → Composite mapping:**

Every raw scalar feature is used in at least one composite (except `key`, which is
categorical and used in the 61-dim similarity vector instead). Features can appear
in multiple composites — e.g. `onset_strength` contributes to Energy, Danceability,
and Stillness (inverted). The `invert` column means "high raw value → low composite
value" — for example, high `onset_strength` means low Stillness.

| Soniq Feature    | Energy | Acousticness | Danceability | Valence | Instrumental | Texture | Dynamics | Stillness |
|------------------|--------|--------------|--------------|---------|--------------|---------|----------|-----------|
| `tempo`          |        |              | 0.6          |         |              |         |          |           |
| `rms_mean`       | 1.0    |              |              | 0.4     |              |         |          |           |
| `rms_max`        |        |              |              |         |              |         | 0.4      |           |
| `rms_variance`   |        |              |              |         |              |         | 0.8      |           |
| `dynamic_range`  | 0.4    |              |              |         |              |         | 1.2      |           |
| `centroid_mean`  |        | 0.8 inv      |              | 0.6     |              |         |          |           |
| `flatness_mean`  |        | 1.0 inv      |              |         |              | 1.0     |          |           |
| `spectral_flux`  |        |              |              |         |              | 0.6     |          | 0.8 inv   |
| `onset_strength` | 0.8    |              | 0.4          |         |              |         |          | 1.0 inv   |
| `beat_strength`  | 0.6    |              | 1.2          |         |              |         |          | 1.0 inv   |
| `vocal_proxy`    |        |              |              |         | 1.0 inv      |         |          |           |
| `zcr_mean`       |        | 0.6 inv      |              |         |              | 0.8     |          |           |
| `duration`       |        |              |              |         |              |         |          | 0.4       |
| `key`            | —      | —            | —            | —       | —            | —       | —        | —         |
| `mode`           |        |              |              | 1.0     |              |         |          |           |

- Numbers = weight in the composite formula (higher = more influence)
- `inv` = inverted (raw high → composite low)
- `—` = not used in composites (`key` is categorical, used in 61-dim similarity vector only)
- `mode` contributes to Valence: major (1) = uplifting, minor (0) = melancholic
- Valence also uses `tonnetz_mean` brightness at the backend level (not shown — vector feature)

**Composite formulas:**

```
Energy       = rms_mean×1.0 + onset×0.8 + beat×0.6 + dyn_range×0.4
Acousticness = (1-flatness)×1.0 + (1-centroid)×0.8 + (1-zcr)×0.6
Danceability = beat×1.2 + tempo×0.6 + onset×0.4
Valence      = mode×1.0 + centroid×0.6 + rms_mean×0.4 (+ tonnetz brightness×0.3 backend)
Instrumental = (1-vocal_proxy)×1.0
Texture      = flatness×1.0 + zcr×0.8 + flux×0.6
Dynamics     = dyn_range×1.2 + rms_variance×0.8 + rms_max×0.4
Stillness    = (1-onset)×1.0 + (1-beat)×1.0 + (1-flux)×0.8 + duration×0.4
```

All raw features are min-max normalized to 0–1 before weighting. Each composite
is then divided by its total weight sum to produce a 0–1 output.

**Presets for drone discovery:**

| Preset         | Energy | Acou. | Dance. | Valence | Instr. | Texture | Dynamics | Stillness |
|----------------|--------|-------|--------|---------|--------|---------|----------|-----------|
| Deep Drone     | 15     | 50    | 10     | 30      | 85     | 35      | 60       | 95        |
| Dark Ambient   | 20     | 45    | 10     | 15      | 80     | 45      | 55       | 85        |
| Textured Drone | 25     | 40    | 10     | 25      | 85     | 80      | 65       | 90        |
| Cinematic Swell| 40     | 55    | 15     | 50      | 75     | 25      | 90       | 70        |

---

## Future: Genre Enrichment via MusicBrainz

### The problem

When a library is sonically homogeneous (e.g. mostly jazz/downtempo/nu jazz), cosine
similarity scores between artists cluster around 0.99+ — the system detects real
differences but they're subtle gradients, not clear separations. Adding genre metadata
from an external source would help validate and contextualize sonic similarity.

### MusicBrainz as a genre source

MusicBrainz provides free, community-curated genre/tag data for artists via their API.
No API key required — just a `User-Agent` header and rate limiting (1 request/second).

**API endpoint:**
```
GET https://musicbrainz.org/ws/2/artist/?query=artist:{name}&fmt=json&limit=1
Header: User-Agent: Soniq/0.1 (music-player research)
```

**Response includes:**
- `tags[]` — genre tags with community vote counts (higher = more confident)
- `country` — artist origin (ISO country code)
- `id` — MusicBrainz UUID for deeper lookups

**For collaboration entries** (e.g. "Ballaké Sissoko, Vincent Segal"), query the
first artist name only — MusicBrainz doesn't index collaboration strings.

### How it could be used

1. **Sphere labels** — show genre tags alongside artist names in Sonic Sphere/Mix
   to visually validate whether sonic proximity matches genre proximity
2. **Genre-aware similarity** — blend MusicBrainz genre overlap into the similarity
   score (e.g. 70% audio features + 30% genre tag overlap) to break ties when
   cosine similarity is very close
3. **Library diversity dashboard** — aggregate genre distribution to show how
   diverse or concentrated a collection is
4. **Cross-genre discovery** — when generating mixes, flag tracks from different
   genres that still match sonically — these are the most interesting discoveries

### Library genre snapshot (March 2025, 33 artists)

```
jazz                     22 artists  ██████████████████████
downtempo                13          █████████████
nu jazz                  13          █████████████
contemporary jazz         7          ███████
acid jazz                 7          ███████
post-rock                 6          ██████
electronic                6          ██████
ambient                   5          █████
jazz fusion               5          █████
trip hop                  4          ████
electronica               4          ████
acoustic                  4          ████
instrumental hip hop      3          ███
instrumental              3          ███
spiritual jazz            2          ██
bossa nova                2          ██
funk                      2          ██
```

The concentration is clear — adding artists from underrepresented genres
(afrobeat, house, classical, hip hop, metal) would stress-test the feature
space and reveal whether sonic similarity holds across genre boundaries.

### Implementation notes

- Cache MusicBrainz responses to avoid repeated lookups (store in DB or JSON file)
- Respect rate limit: 1 request/second, batch on first run
- Filter tags with `count < 0` (community downvotes = incorrect tags)
- Consider storing top 5 tags per artist in the Soniq tag or a sidecar file
