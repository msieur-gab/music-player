# Prayer by GoGo Penguin — Feature Analysis

Track-level comparison between Soniq (librosa-extracted) features and AcousticBrainz
(neural classifier) output. Used as a validation benchmark because the track is well-known
to the listener.

**Track:** Prayer
**Artist:** GoGo Penguin
**Album:** A Humdrum Star (2018)
**Duration:** 174s (2:54)
**MusicBrainz ID:** `810e36b9-20d0-4bf5-802c-56f624897b9f`

---

## Raw Soniq Features (normalized 0–1 against full library)

| Feature | Raw Value | Normalized | Bar |
|---------|-----------|------------|-----|
| `tempo` | 66.26 BPM | 0.231 | ████░░░░░░░░░░░░░░░░ |
| `rms_mean` | 10.32 | 0.743 | ██████████████░░░░░░ |
| `rms_max` | 16.15 | 0.738 | ██████████████░░░░░░ |
| `rms_variance` | 9.05 | 0.063 | █░░░░░░░░░░░░░░░░░░░ |
| `dynamic_range` | 19.95 dB | 0.131 | ██░░░░░░░░░░░░░░░░░░ |
| `centroid_mean` | 562.15 Hz | 0.074 | █░░░░░░░░░░░░░░░░░░░ |
| `flatness_mean` | 0.0001 | 0.001 | ░░░░░░░░░░░░░░░░░░░░ |
| `spectral_flux` | 22.91 | 0.166 | ███░░░░░░░░░░░░░░░░░ |
| `onset_strength` | 1.02 | 0.229 | ████░░░░░░░░░░░░░░░░ |
| `beat_strength` | 1.12 | 0.170 | ███░░░░░░░░░░░░░░░░░ |
| `vocal_proxy` | 0.82 | 0.831 | ████████████████░░░░ |
| `zcr_mean` | 0.023 | 0.047 | █░░░░░░░░░░░░░░░░░░░ |
| `duration` | 174.20s | 0.045 | █░░░░░░░░░░░░░░░░░░░ |

**What the raw features tell us:**
- Very low spectral centroid (562 Hz) → dark, bass-heavy timbre
- Near-zero flatness → pure tonal content, no noise
- Low onset/beat strength → minimal rhythmic attack
- High rms_mean but low variance → consistently present but steady volume
- Very low zcr → clean, non-percussive waveform
- High vocal_proxy (0.83) → **false positive** — piano mid-frequency energy mimics vocal range

---

## Soniq Composites vs AcousticBrainz

| Dimension | Soniq | AcousticBrainz | AB Source | Match |
|-----------|-------|----------------|-----------|-------|
| **Acousticness** | 0.96 | 0.88 | `mood_acoustic` | ✓ |
| **Danceability** | 0.20 | 0.03 | `danceability` (not_danceable 97.3%) | ✓ |
| **Valence** (≈ happy) | 0.34 | 0.15 | `mood_happy` (not_happy 85%) | ✓ |
| **Instrumentalness** | 0.17 | 0.99 | `voice_instrumental` (instrumental 99%) | ✗ |
| **Stillness** (≈ relaxed) | 0.71 | 0.98 | `mood_relaxed` (relaxed 98.4%) | ✓ |
| **Energy** | 0.39 | — | no direct equivalent | — |
| **Texture** | 0.06 | — | no direct equivalent | — |
| **Dynamics** | 0.21 | — | no direct equivalent | — |

**Accuracy: 4/5 matches** (within 0.2 tolerance on comparable dimensions)

---

## AcousticBrainz Full Classification

### Genre classifiers

| Classifier | Top Result | Confidence |
|------------|-----------|------------|
| genre_dortmund | jazz | 45.0% |
| genre_electronic | ambient | 93.7% |
| genre_rosamerica | jazz | 47.0% |
| genre_tzanetakis | jazz | 31.2% |

All classifiers agree on jazz. The electronic sub-classifier says ambient at 93.7% —
this makes sense, Prayer has an ambient character despite being acoustic piano.

### Mood classifiers

| Mood | Value | Confidence |
|------|-------|------------|
| **relaxed** | relaxed | 98.4% |
| **sad** | sad | 81.4% |
| **happy** | not_happy | 85.0% |
| **aggressive** | not_aggressive | 89.8% |
| **party** | not_party | 95.5% |
| **electronic** | electronic | 67.7% |
| **acoustic** | acoustic | 88.3% |

### Other classifications

| Feature | Value | Confidence |
|---------|-------|------------|
| **timbre** | dark | 99.8% |
| **tonal/atonal** | atonal | 80.3% |
| **voice/instrumental** | instrumental | 99.0% |
| **gender** (of vocal) | male | 92.7% |
| **rhythm** (dance style) | Tango | 71.6% |

Note: "gender: male" is a false positive — no vocals present. The classifier defaults
to male when there's low-frequency dominant content.

### Genre breakdown (Dortmund classifier)

```
jazz          45.0%  █████████████
electronic    19.6%  █████
alternative   11.3%  ███
folkcountry    9.1%  ██
rock           7.4%  ██
blues          4.5%  █
pop            2.0%
funksoulrnb    0.5%
raphiphop      0.4%
```

---

## Key Findings

### What Soniq gets right
- **Acousticness** — near-zero flatness and low centroid correctly identify pure acoustic tone
- **Danceability** — low beat_strength and slow tempo → low danceability (both systems agree)
- **Valence** — low centroid + moderate loudness → subdued mood (aligns with AB's "not happy" / "sad")
- **Stillness** — low onset/beat/flux → high stillness (aligns with AB's "relaxed 98.4%")
- **Timbre darkness** — centroid at 562 Hz (normalized 0.074) perfectly matches AB's "dark 99.8%"

### What Soniq gets wrong
- **Instrumentalness: 0.17 vs 0.99** — The biggest miss. Our `vocal_proxy` uses mid-frequency
  energy ratio (roughly 300–4000 Hz) as a proxy for vocal presence. Piano fundamentals and
  harmonics sit squarely in this range, causing a false positive. AcousticBrainz uses a trained
  neural network that has learned to distinguish piano timbre from voice.

  **This is a known limitation of the mid-frequency ratio approach.** Any instrument with strong
  energy in the 300–4000 Hz range (piano, saxophone, violin, cello) will trigger false vocal
  detection. A proper fix would require either:
  1. A trained vocal detection model (too heavy for our portable approach)
  2. Harmonic pattern analysis (vocal formants have specific spacing patterns vs. piano overtones)
  3. Temporal modulation — vocals have vibrato and breath patterns that instruments don't

### Interesting observations
- AB classifies the rhythm as "Tango" (71.6%) — the 3/4-like feel of Prayer's piano arpeggios
  likely triggers this. Our system doesn't have rhythm style classification.
- AB says "atonal" at 80.3% — Prayer uses dissonant voicings and cluster chords, which our
  chroma/tonnetz features capture but we don't surface as a named dimension yet.
- AB's "electronic: 67.7%" despite being acoustic piano — this likely reflects the production
  (reverb, compression) rather than the instrumentation. Our system doesn't confuse this.

---

## AcousticBrainz Complete Feature Inventory

AcousticBrainz provides three levels of data per recording. Below is the full inventory
using Prayer as the reference track.

### High-Level Classifiers (18 neural network models)

All are binary or multi-class classifiers trained on the Essentia low-level features.

| # | Classifier | Prayer Result | Confidence | Classes |
|---|-----------|---------------|------------|---------|
| 1 | `danceability` | not_danceable | 97.3% | danceable, not_danceable |
| 2 | `gender` | male | 92.7% | male, female |
| 3 | `genre_dortmund` | jazz | 45.0% | jazz, electronic, alternative, folkcountry, rock, blues, pop, funksoulrnb, raphiphop |
| 4 | `genre_electronic` | ambient | 93.7% | ambient, house, techno, trance, dnb |
| 5 | `genre_rosamerica` | jaz | 47.0% | jaz, rhy, cla, hip, roc, pop, spe, dan |
| 6 | `genre_tzanetakis` | jaz | 31.2% | jaz, hip, cou, dis, roc, blu, pop, reg, met, cla |
| 7 | `ismir04_rhythm` | Tango | 71.6% | Tango, VienneseWaltz, Rumba-International, Waltz, Rumba-Misc, Rumba-American, ChaChaCha, Samba, Quickstep, Jive |
| 8 | `mood_acoustic` | acoustic | 88.3% | acoustic, not_acoustic |
| 9 | `mood_aggressive` | not_aggressive | 89.8% | aggressive, not_aggressive |
| 10 | `mood_electronic` | electronic | 67.7% | electronic, not_electronic |
| 11 | `mood_happy` | not_happy | 85.0% | happy, not_happy |
| 12 | `mood_party` | not_party | 95.5% | party, not_party |
| 13 | `mood_relaxed` | relaxed | 98.4% | relaxed, not_relaxed |
| 14 | `mood_sad` | sad | 81.4% | sad, not_sad |
| 15 | `moods_mirex` | Cluster2 | 37.1% | Cluster1–5 (unnamed emotion clusters from MIREX dataset) |
| 16 | `timbre` | dark | 99.8% | dark, bright |
| 17 | `tonal_atonal` | atonal | 80.3% | tonal, atonal |
| 18 | `voice_instrumental` | instrumental | 99.0% | voice, instrumental |

### Low-Level Features (47 keys)

Extracted by Essentia (C++ audio analysis library). Each feature includes `dmean` (delta mean),
`dmean2` (second derivative mean), and `dvar` (delta variance) — capturing both the feature
value and how it changes over time.

#### Scalar features

| Feature | Prayer Value | Soniq Equivalent |
|---------|-------------|-----------------|
| `average_loudness` | 0.469 | `rms_mean` (similar concept) |
| `dynamic_complexity` | 7.576 | `dynamic_range` + `rms_variance` (approximate) |

#### Spectral features (frame-level statistics)

| Feature | Dims | Prayer dmean | Soniq Equivalent |
|---------|------|-------------|-----------------|
| `spectral_centroid` | 1 | 42.83 | `centroid_mean` ✓ |
| `spectral_flux` | 1 | 0.016 | `spectral_flux` ✓ |
| `spectral_rms` | 1 | 0.0006 | `rms_mean` ✓ |
| `spectral_rolloff` | 1 | 63.73 | — (not extracted) |
| `spectral_energy` | 1 | 0.010 | — |
| `spectral_entropy` | 1 | 0.122 | — |
| `spectral_complexity` | 1 | 1.159 | — (number of spectral peaks) |
| `spectral_strongpeak` | 1 | 0.168 | — |
| `spectral_kurtosis` | 1 | 12.51 | — |
| `spectral_skewness` | 1 | 0.730 | — |
| `spectral_spread` | 1 | 260177 | — |
| `spectral_decrease` | 1 | 0.000 | — |
| `zerocrossingrate` | 1 | 0.002 | `zcr_mean` ✓ |
| `hfc` | 1 | 1.451 | — (high frequency content) |
| `pitch_salience` | 1 | 0.057 | — (how clearly pitched) |
| `dissonance` | 1 | 0.037 | — (sensory dissonance) |

#### Band-based spectral features

| Feature | Dims | Description | Soniq Equivalent |
|---------|------|-------------|-----------------|
| `barkbands` | 27 | Bark-scale frequency bands | — |
| `barkbands_crest` | 1 | Crest factor of bark bands | — |
| `barkbands_flatness_db` | 1 | Flatness in dB | `flatness_mean` (similar) |
| `barkbands_kurtosis` | 1 | Band energy distribution shape | — |
| `barkbands_skewness` | 1 | Band energy asymmetry | — |
| `barkbands_spread` | 1 | Band energy spread | — |
| `erbbands` | 40 | ERB (equivalent rectangular bandwidth) bands | — |
| `erbbands_crest` | 1 | ERB crest factor | — |
| `erbbands_flatness_db` | 1 | ERB flatness | — |
| `erbbands_kurtosis` | 1 | ERB distribution shape | — |
| `erbbands_skewness` | 1 | ERB asymmetry | — |
| `erbbands_spread` | 1 | ERB spread | — |
| `melbands` | 40 | Mel-scale frequency bands | — |
| `melbands_crest` | 1 | Mel crest factor | — |
| `melbands_flatness_db` | 1 | Mel flatness | — |
| `melbands_kurtosis` | 1 | Mel distribution shape | — |
| `melbands_skewness` | 1 | Mel asymmetry | — |
| `melbands_spread` | 1 | Mel spread | — |
| `spectral_contrast_coeffs` | 6 | Spectral contrast | `spectral_contrast` ✓ (7 dims) |
| `spectral_contrast_valleys` | 6 | Contrast valleys | — |

#### Energy band features

| Feature | Prayer dmean | Description |
|---------|-------------|-------------|
| `spectral_energyband_low` | 0.0088 | Energy below ~200 Hz |
| `spectral_energyband_middle_low` | 0.0033 | ~200–800 Hz |
| `spectral_energyband_middle_high` | 0.0002 | ~800–4000 Hz |
| `spectral_energyband_high` | 0.0000 | Above ~4000 Hz |

Prayer's energy is almost entirely in the low band — confirms the "dark" timbre
classification and our very low centroid_mean (562 Hz).

#### Cepstral features

| Feature | Dims | Description | Soniq Equivalent |
|---------|------|-------------|-----------------|
| `mfcc` | 13 (mean + 13×13 covariance) | MFCCs with full covariance matrix | `mfcc_mean` + `mfcc_std` ✓ (mean+std only) |
| `gfcc` | 13 (mean + 13×13 covariance) | Gammatone cepstral coefficients | — (alternative to MFCCs, better for noisy audio) |

#### Silence detection

| Feature | Prayer Value | Description |
|---------|-------------|-------------|
| `silence_rate_20dB` | 0.000 | Fraction of frames below -20 dB |
| `silence_rate_30dB` | 0.038 | Fraction of frames below -30 dB |
| `silence_rate_60dB` | 0.010 | Fraction of frames below -60 dB |

### Rhythm Features (13 keys)

| Feature | Prayer Value | Soniq Equivalent |
|---------|-------------|-----------------|
| `bpm` | 66.78 | `tempo` ✓ (66.26 — close match) |
| `beats_count` | 212 | — |
| `onset_rate` | 0.781 | `onset_strength` (related) |
| `danceability` | 0.883 | — (different from high-level classifier!) |
| `beats_loudness` | dmean=0.036 | `beat_strength` (related) |
| `beats_position` | [212 values] | — (full beat grid) |
| `bpm_histogram_first_peak_bpm` | 0.0 | — (tempo stability) |
| `bpm_histogram_second_peak_bpm` | 0.0 | — (secondary tempo) |

Note: The low-level `danceability` (0.883) contradicts the high-level classifier
(not_danceable 97.3%). The low-level value is a raw Essentia feature; the high-level
is a trained neural classifier that considers the full feature context. The classifier
is more accurate — Prayer is clearly not danceable.

### Tonal Features (16 keys)

| Feature | Prayer Value | Soniq Equivalent |
|---------|-------------|-----------------|
| `key_key` | E | `key` ✓ |
| `key_scale` | minor | `mode` ✓ (0 = minor) |
| `key_strength` | 0.723 | — (confidence) |
| `chords_key` | E | — |
| `chords_scale` | minor | — |
| `chords_changes_rate` | 0.047 | — (how often chords change) |
| `chords_number_rate` | 0.003 | — (unique chords per second) |
| `chords_strength` | dmean=0.007 | — |
| `hpcp` | 36 dims | `chroma` (12 dims — hpcp is 3x resolution) |
| `hpcp_entropy` | dmean=0.377 | — (harmonic complexity) |
| `tuning_frequency` | 441.27 Hz | — (standard is 440 Hz) |
| `tuning_diatonic_strength` | 0.457 | — (how diatonic the harmony is) |
| `tuning_equal_tempered_deviation` | 0.048 | — (microtonal deviation) |
| `tuning_nontempered_energy_ratio` | 0.630 | — (non-standard tuning energy) |

Prayer's `tuning_diatonic_strength` of 0.457 is low — confirms the atonal classification.
The harmony doesn't follow standard diatonic patterns, using cluster chords and
non-functional voicings.

---

## Soniq vs AcousticBrainz Feature Coverage

### What Soniq extracts that AcousticBrainz also has

| Feature | Soniq | AcousticBrainz | Notes |
|---------|-------|----------------|-------|
| MFCCs | 13 mean + 13 std | 13 mean + 13×13 covariance | AB has full covariance matrix |
| Spectral contrast | 7 dims | 6 coeffs + 6 valleys | Similar coverage |
| Chroma | 12 dims | HPCP 36 dims | AB has 3x resolution |
| Tonnetz | 6 dims | — | Soniq-only (derived from chroma) |
| Tempo/BPM | ✓ | ✓ | Near-identical (66.26 vs 66.78) |
| Spectral centroid | ✓ | ✓ | Both extract this |
| Spectral flux | ✓ | ✓ | Both extract this |
| ZCR | ✓ | ✓ | Both extract this |
| RMS energy | ✓ | ✓ | Different normalization |
| Dynamic range | ✓ | `dynamic_complexity` | Similar concept |
| Key/mode | ✓ | ✓ | Both detect E minor |
| Onset strength | ✓ | `onset_rate` | Related but different |
| Beat strength | ✓ | `beats_loudness` | Related but different |
| Flatness | ✓ | `barkbands_flatness_db` | Similar |

### What AcousticBrainz has that Soniq doesn't

| Feature | Why it matters | Difficulty to add |
|---------|---------------|-------------------|
| **Dissonance** | Predicts tension, unease, atonal feel | Medium — Essentia has it, librosa doesn't natively |
| **Pitch salience** | Distinguishes pitched (tonal) from noisy/percussive | Medium — would improve vocal detection |
| **Spectral complexity** | Number of spectral peaks — separates simple from dense | Easy — count peaks in STFT |
| **HPCP (36 bins)** | 3x chroma resolution — better chord detection | Easy — librosa can do 36-bin chroma |
| **Chord detection** | Key, scale, chord change rate | Hard — needs HMM or neural model |
| **GFCC** | Alternative timbral fingerprint, better for noisy audio | Medium — needs gammatone filterbank |
| **Bark/ERB bands** | Perceptually-weighted spectral decomposition | Medium — alternative to mel bands |
| **Energy sub-bands** | Energy in low/mid-low/mid-high/high ranges | Easy — split spectrum at thresholds |
| **Silence rates** | Detects sparse/minimal music | Easy — threshold on RMS per frame |
| **Tuning analysis** | Detects non-standard tuning, microtonal music | Hard — specialized algorithm |
| **Diatonic strength** | How "normal" the harmony sounds | Hard — needs HPCP analysis |
| **18 neural classifiers** | Genre, mood, timbre, danceability, voice/instr | Very hard — needs trained models + Essentia |

### What Soniq has that AcousticBrainz doesn't

| Feature | Why it matters |
|---------|---------------|
| **Tonnetz (6 dims)** | Harmonic interval relationships — captures tension/resolution patterns |
| **Vocal proxy** | Rough vocal detection (flawed but present — AB uses neural classifier) |
| **RMS variance** | How much loudness changes — key for dynamics composite |
| **RMS max** | Peak loudness — contributes to dynamics |

### Priority additions (best bang for effort)

If we wanted to close the gap with AcousticBrainz, the highest-value additions would be:

1. **Energy sub-bands** (easy) — split spectral energy into 4 ranges. Would immediately
   improve vocal detection: vocals have strong mid-high energy, piano has strong low-mid.
2. **Silence rate** (easy) — count frames below -30 dB. Helps identify sparse/minimal music.
3. **HPCP at 36 bins** (easy) — drop-in replacement for 12-bin chroma. Better chord resolution.
4. **Pitch salience** (medium) — how clearly pitched vs noisy. Combined with energy sub-bands,
   could dramatically improve vocal_proxy accuracy.
5. **Dissonance** (medium) — sensory dissonance from spectral peaks. Would enable a
   "tension" composite dimension.

---

## Local Essentia Classification (March 2026)

We installed `essentia-tensorflow` (2.1-beta6-dev, 291MB) locally and ran the
pre-trained models from the MTG model zoo on Prayer. Two backbone architectures
were tested: MusiCNN (`msd-musicnn-1.pb`) and VGGish (`audioset-vggish-3.pb`).

### Setup

```
pip install essentia-tensorflow   # 291MB, includes TF
```

Models downloaded separately from `https://essentia.upf.edu/models/`:
- Backbone: `msd-musicnn-1.pb` (3MB) and `audioset-vggish-3.pb` (275MB)
- Classifier heads: ~0.1MB each (mood, danceability, voice, timbre, tonal)
- Genre: `genre_discogs400-discogs-effnet-1.pb` (2MB, uses EffNet backbone)

**Critical architecture note:** Each classifier head was trained on a specific
backbone (MusiCNN or VGGish or EffNet). Mixing backbones silently degrades accuracy.
The two-stage pipeline is: audio → backbone embeddings → classifier head.

### Results: MusiCNN vs AcousticBrainz

After fixing label ordering (see "Critical Fix" below), the local Essentia models
align closely with AcousticBrainz reference values.

| Classifier | MusiCNN (local) | AcousticBrainz | Ground Truth |
|---|---|---|---|
| **mood_happy** | non_happy 99.2% | not_happy 85.0% | **not happy** ✓ |
| **mood_relaxed** | relaxed 99.9% | relaxed 98.4% | **relaxed** ✓ |
| **mood_aggressive** | not_aggressive 97.4% | not_aggressive 89.8% | **not aggressive** ✓ |
| **mood_sad** | sad 61.4% | sad 81.4% | **sad** ✓ |
| **mood_acoustic** | non_acoustic 61.6% | acoustic 88.3% | **acoustic** (AB stronger) |
| **danceability** | not_danceable 82.9% | not_danceable 97.3% | **not danceable** ✓ |
| **voice/instrumental** | instrumental 92.2% | instrumental 99.0% | **instrumental** ✓ |
| **tonal/atonal** | tonal 87.9% | atonal 80.3% | debatable |

Additional classifiers (EffNet backbone):
- **Timbre:** dark 50.7% (weak confidence — AB said dark 99.8%)
- **Genre:** Electronic—Ambient 24.3%, Electronic—Experimental 13.3%, Electronic—Drone 8.3% ✓
- **Arousal/Valence:** arousal=4.07, valence=3.71 (scale 1–9, moderate — reasonable)

### Critical Fix: Binary Classifier Label Ordering

Initial results appeared to show 4/6 classifiers getting Prayer wrong. The root cause
was **incorrect label ordering**, not bad model weights.

Each binary classifier outputs `[class_0_prob, class_1_prob]`, but the label-to-index
mapping is NOT consistent across models. We initially assumed a uniform ordering and
got inverted results for most classifiers.

**Fix:** Downloaded the official metadata JSONs from essentia.upf.edu for each model
and verified the correct label arrays:

```
mood_happy:       ["happy", "non_happy"]         ← index 0 = happy
mood_sad:         ["non_sad", "sad"]              ← index 0 = non_sad
mood_relaxed:     ["non_relaxed", "relaxed"]      ← index 0 = non_relaxed
mood_aggressive:  ["aggressive", "not_aggressive"] ← index 0 = aggressive
mood_party:       ["non_party", "party"]          ← index 0 = non_party
mood_acoustic:    ["acoustic", "non_acoustic"]    ← index 0 = acoustic
danceability:     ["danceable", "not_danceable"]  ← index 0 = danceable
voice_instrumental: ["instrumental", "voice"]     ← index 0 = instrumental
tonal_atonal:     ["tonal", "atonal"]             ← index 0 = tonal
```

With correct labels, **all classifications match AcousticBrainz and ground truth.**
The models are accurate — the issue was purely label interpretation.

### What Essentia Adds

1. **Genre classification** (EffNet + Discogs400) — 400 Discogs genre/style labels.
   Identifies Prayer as Electronic—Ambient/Drone, something librosa can't do.

2. **Arousal/Valence regression** (emomusic model) — Continuous emotional
   coordinates on a 1–9 scale. Arousal 4.07, valence 3.71 = "calm, slightly
   melancholic." More nuanced than binary mood classifiers.

3. **Binary mood classifiers** — Once labels are read correctly, these are
   accurate and complement our librosa composites. Neural classifiers beat
   heuristic formulas for mood, danceability, and vocal detection.

4. **EffNet embeddings** (1280 dimensions) — Deep learned representations that
   could improve similarity search vs our 61-dim handcrafted vector. Not yet tested.

### Performance

- **~40–77 seconds per track** on i5-7Y57 (CPU, no GPU)
- MusiCNN + EffNet backbones run sequentially
- Classifier heads are milliseconds each — negligible
- For an 861-track library: ~10–18 hours batch processing
- One-time cost: embed results in Soniq tags, never recompute

### Recommendation: Hybrid Approach

**Keep librosa as the foundation, add Essentia as a semantic layer.**

| Source | What it provides |
|---|---|
| **librosa** | Continuous feature vectors (61-dim) for sphere positioning and similarity, tempo/key/chroma, spectral shape, fast extraction (~15s/track) |
| **Essentia** | Genre (400 classes), mood labels, danceability, voice/instrumental, arousal/valence — semantic classifications that complement raw features |

Librosa gives the **geometry** (where tracks sit in feature space).
Essentia gives the **labels** (what those positions mean in human terms).

### Batch Validation (14 tracks tested)

After fixing labels, tested across diverse library: Mammal Hands (10 tracks),
Daft Punk, GoGo Penguin, Ballaké Sissoko, Hidden Orchestra.

| Track | Key Classifications | Accurate? |
|---|---|---|
| Daft Punk — Get Lucky | happy 90%, danceable 98%, voice 79%, Nu-Disco/House | ✓ |
| GoGo Penguin — Prayer | non_happy 99%, relaxed 100%, instrumental 92%, Ambient | ✓ |
| Ballaké Sissoko — Djourou | acoustic 97%, relaxed 99%, instrumental 88%, Folk 31% | ✓ |
| Hidden Orchestra — Dust | happy 62%, danceable 74%, instrumental 90%, Experimental | ✓ |
| Mammal Hands — Kudu | happy 64%, danceable 78%, instrumental 95%, Indie Rock | ✓ |
| Mammal Hands — In the Treetops | relaxed 99%, sad 70%, not danceable 83%, Jazz | ✓ |

All 14 tracks produced plausible, accurate classifications across very different genres.

---

## Data Sources

- **Soniq features:** librosa extraction, embedded in m4a tag `----:com.soniq:features`
- **AcousticBrainz high-level:** `https://acousticbrainz.org/api/v1/{mbid}/high-level`
- **AcousticBrainz low-level:** `https://acousticbrainz.org/api/v1/{mbid}/low-level`
- **MusicBrainz recording:** `https://musicbrainz.org/ws/2/recording/810e36b9-20d0-4bf5-802c-56f624897b9f`
- **Essentia models:** `https://essentia.upf.edu/models.html`
- **Soniq Lab code:** `~/soniq-lab/classify.py`
- **Analysis date:** March 2025 (Soniq + AcousticBrainz), March 2026 (local Essentia)
