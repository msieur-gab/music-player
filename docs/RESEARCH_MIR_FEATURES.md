# MIR Feature Research — Audio Features for Emotion & Context Classification

> Research compiled 2026-03-09 for MusiCast's weighted zone scoring system.
> Sources: academic papers, Spotify validation studies, librosa documentation.

---

## Current Feature Set (48 dimensions)

| Group | Dims | Used in zones | Used in find_similar |
|-------|------|---------------|---------------------|
| Energy/rhythm scalars (tempo, rms_mean, onset_strength, beat_strength) | 4 | Yes | Yes |
| Timbre scalars (centroid, flatness, flux, zcr, dynamic_range, rms_variance, vocal_proxy) | 6 | Yes | Yes |
| Key + Mode | 2 | No (not in profile) | No |
| MFCC mean | 13 | **No** | Yes |
| MFCC std | 13 | **No** | Yes |
| Spectral contrast | 7 | **No** | Yes |
| **Chroma (not yet extracted)** | **12** | **No** | **No** |

**Gap:** Zone classification uses only 10 of 48 dimensions (21%). The 33 vector dimensions (69% of feature space) are ignored for the primary user-facing feature.

**Missing:** Chroma is computed inside `_extract_key_mode()` but collapsed to two scalars (key, mode). The full 12-dim chroma vector is discarded.

---

## What Each Feature Captures

### Scalar Features — Semantic Meaning

| Feature | Perceptual meaning | Primary emotion axis | Direction |
|---------|-------------------|---------------------|-----------|
| **tempo** | Pulse speed (60 BPM = resting heart, 140 = driving) | Arousal | Fast = high |
| **rms_mean** | Average perceived loudness | Arousal | Loud = high |
| **rms_max** | Peak loudness moment (climax intensity) | Arousal (burst) | |
| **rms_variance** | Loudness stability (low = drone, high = dynamic) | Both (arousal dynamics) | |
| **dynamic_range** | Quiet-to-loud gap (compressed pop = small, orchestral = large) | Expressive range | |
| **centroid_mean** | Brightness (low = dark/warm, high = bright/harsh) | Both (arousal + valence) | Bright = high arousal |
| **flatness_mean** | Tonality vs noise (0 = pure tone, 1 = white noise) | Valence | Tonal = positive |
| **spectral_flux** | Rate of spectral change, how "busy" the frequency content is | Arousal | High = aroused |
| **onset_strength** | Attack prominence, how percussive/transient | Arousal | Sharp = high |
| **beat_strength** | Rhythmic pulse clarity (ambient = low, funk = high) | Arousal | |
| **vocal_proxy** | Vocal presence (harmonic ratio * (1 - harmonic flatness)) | Emotional directness | |
| **zcr_mean** | Noisiness / high-frequency content proxy | Arousal (texture) | |
| **key** | Pitch class (0-11, C to B) | Contextual | |
| **mode** | Major (1) vs minor (0) | **Valence** (strongest single predictor) | Major = positive |
| **duration** | Track length | Utility only | |

### Scalar Sub-Groups

For weighting purposes, scalars divide into functional groups:

- **Energy/Rhythm** (arousal-dominant): `tempo`, `rms_mean`, `onset_strength`, `beat_strength`
- **Timbre** (character): `centroid_mean`, `flatness_mean`, `spectral_flux`, `zcr_mean`
- **Dynamics** (evolution): `dynamic_range`, `rms_variance`
- **Vocal**: `vocal_proxy`
- **Harmony** (valence): `key`, `mode` — currently unused in profiles

### MFCC Coefficients (13 dims) — Timbral Identity

| Coefficient | What it captures | Perceptual weight |
|-------------|-----------------|-------------------|
| **MFCC 0** | Overall spectral energy/loudness. Redundant with rms_mean. | Often excluded |
| **MFCC 1** | Spectral slope/tilt — brightness vs warmth. **Strongest single MFCC for arousal prediction** (R = 0.824 in regression). | Very high |
| **MFCC 2** | Spectral curvature — energy distribution extremes vs middle. Significant for **valence prediction**. | High |
| **MFCC 3** | Mid-level spectral shape. **Single most important coefficient in SHAP analysis** of music classifiers. | High |
| **MFCC 4** | Formant-like resonances — distinguishes instrument families. | High |
| **MFCC 5** | Voicing/fricative cues — breathy vs clean tonal. | Moderate |
| **MFCC 6-13** | Increasingly fine spectral detail. Pitch harmonics, rapid spectral variations. | Low individually, collective texture |

**Key finding:** MFCCs 1-4 carry disproportionate perceptual weight for mood. MFCCs 5-13 matter more for track-to-track similarity (fine fingerprinting).

**Recommended weighting:** MFCCs 1-4 at 1.5x, MFCCs 5-13 at 0.7x for zone scoring.

### MFCC Std (13 dims) — Timbral Consistency

- **High std** = track changes significantly over time (builds, drops, transitions, varied instrumentation)
- **Low std** = consistent texture throughout (drones, loops, steady ambient)

**Relative importance:** MFCC mean is 1.5-2x more important than MFCC std for mood classification. For track similarity, closer to 1:1.

Statistically significant std coefficients for valence: MFCC std 1, 2, 8, and 10.

### Spectral Contrast (7 bands) — Harmonic Structure

With librosa defaults (`fmin=200`, `n_bands=6`, `sr=22050`):

| Band | Frequency range | Perceptual quality |
|------|----------------|-------------------|
| 0 | 0–200 Hz | **Sub-bass rumble.** Felt more than heard. Weight, power. |
| 1 | 200–400 Hz | **Bass fundamentals.** Kick drum body, male vocal fundamentals. Warmth, fullness. |
| 2 | 400–800 Hz | **Lower midrange.** Instrument body, female vocal fundamentals. |
| 3 | 800–1600 Hz | **Upper midrange.** Vocal presence, instrument attack. Presence, intelligibility. |
| 4 | 1600–3200 Hz | **Presence range.** Human hearing most sensitive. Clarity, edge. |
| 5 | 3200–6400 Hz | **Brilliance.** Cymbal shimmer, breathiness. Brightness, air. |
| 6 | 6400–11025 Hz | **Upper air.** Overtones, room ambience. Openness, sparkle. |

**High contrast** = clear harmonic content above noise floor (tonal, clean).
**Low contrast** = broad-band energy (noisy, textured, dense).

**Key finding:** Spectral contrast **outperformed MFCC** as a single feature family for sentiment prediction (RMSE 2.783 vs 3.420). It deserves significant weight.

### Chroma (12 dims) — NOT YET EXTRACTED

Full pitch class energy distribution (C, C#, D, ... B). Captures:
- Complete harmonic profile (not just key/mode binary)
- Consonance vs dissonance patterns
- Chord complexity (simple major triad vs jazz voicings)
- Harmonic tension and resolution

**Why it matters:** Mode (major/minor) is the **strongest single predictor of valence**, but as a binary 0/1 it's extremely lossy. Full chroma preserves the harmonic nuance. Critical for separating:
- Joy from Anger (same arousal, opposite valence)
- Calm from Melancholy (same arousal, opposite valence)

**Caveat:** Chroma alone scored worst in sentiment evaluation (RMSE 5.482). It needs to work alongside MFCC and contrast, not replace them.

**Extraction cost:** Essentially free — `_extract_key_mode()` already computes `chroma_cqt` and throws away the mean vector. Just return it alongside key/mode.

---

## Russell's Circumplex Model — Feature Signatures

| Quadrant | Emotion | Audio signature |
|----------|---------|----------------|
| High arousal + Positive valence | **Joy, Excitement** | High tempo, high loudness, high centroid, high beat strength, major mode, high onset rate |
| High arousal + Negative valence | **Anger, Tension** | High tempo, high loudness, high centroid, high flux, high flatness (noise), minor mode |
| Low arousal + Positive valence | **Calm, Contentment** | Low tempo, moderate loudness, moderate centroid, major mode, low onset rate, low flux |
| Low arousal + Negative valence | **Sadness, Depression** | Low tempo, low loudness, low centroid, minor mode, low beat strength, high dynamic range, high MFCC variance |

**Critical insight:** Arousal is reliably predictable from audio (R up to 0.78). Valence requires harmonic/tonal features (mode, chroma) that are harder to extract. This is exactly why chroma matters — without it, the system can separate high-energy from low-energy but struggles to separate positive from negative within each energy level.

---

## Context-Specific Research

### Sleep Music (Scarratt et al. 2023, N=225,626 tracks)

| Feature | Sleep music | General music | Cohen's d |
|---------|-----------|---------------|-----------|
| Loudness | -19.78 dB | -9.6 dB | -1.25 |
| Energy | 0.23 | 0.59 | **-1.46** (largest) |
| Acousticness | 0.74 | 0.35 | 1.20 |
| Instrumentalness | 0.62 | 0.21 | 1.10 |
| Danceability | 0.42 | 0.56 | -0.64 |
| Valence | 0.25 | 0.48 | -0.93 |
| Tempo | 104.93 BPM | 120.07 BPM | -0.47 |

Optimal sleep music: 60-80 BPM, soft/smooth, simple structure, instrumental, no accented beats or percussion.

**Best single discriminator:** Loudness (r²=0.09), then energy, acousticness, instrumentalness.

**Mapping to our features:** Low `rms_mean`, low `centroid_mean`, low `spectral_flux`, low `onset_strength` and `beat_strength`, low `vocal_proxy`. Energy/rhythm scalars dominate — timbre matters less for sleep discrimination.

### Focus Music (Kikkert et al. 2022, BCI study)

- Audio-predicted focus correlated r=0.68 with brain-decoded focus (r=0.79 per-song average)
- **88% binary accuracy** (high/low focus), 0.91 AUC
- PCA on 136 features → 4 principal components explaining 95% variance; **PC1 alone: r=0.71**
- Classical and engineered soundscapes ranked best; pop and hip-hop worst
- Music with lyrics hinders cognitive performance (especially memory/reading)

**Key qualities:** Low spectral variance, moderate spectral centroid (0.4-0.5, not 0.7), no melodic surprises, constant complexity. Brain.fm targets: bandpass 45 Hz–5 kHz, beta-range modulations (12-18 Hz), no structural breaks.

### Energy/Workout Music

- **Sub-band flux in 50-100 Hz** (bass region) is the strongest correlate of groove sensation
- Periodic music with strong, regular onsets drives arousal
- Optimal running tempo: 120-140 BPM
- Spectral flux correlates with perceived intensity
- Bass presence (contrast bands 0-1) is a key signature not fully captured by scalar features alone

---

## Distance Metrics — Research Findings

### Cosine vs Euclidean

- **Cosine** is better for comparing timbral identity (MFCC direction) regardless of volume differences
- **Euclidean** is better when magnitude matters (energy, loudness should count)
- Recommendation: **hybrid** — cosine for MFCC/contrast subspaces, Euclidean for scalars

### Weighted Euclidean (practical choice without training data)

Since we don't have labeled similarity training data, weighted Euclidean is the most practical improvement. Learned Mahalanobis distance achieves 81.81% accuracy but requires ground truth.

### Feature Group Weight Ratios (from literature)

For pure similarity (MIREX evaluation):
- Timbre (MFCC): 0.95
- Rhythm: 0.04
- Tempo: 0.01

For emotion recognition, the hierarchy reverses for arousal:
- Energy features > Frequency features > Spectral features > Temporal features

This confirms that **different tasks need different weights** — similarity is timbre-dominated, arousal classification is energy-dominated.

---

## Recommended Per-Zone Weight Architecture

### Feature Groups for Weighting

| Group | Features | Dims |
|-------|----------|------|
| Energy/Rhythm | tempo, rms_mean, onset_strength, beat_strength | 4 |
| Timbre scalars | centroid_mean, flatness_mean, spectral_flux, zcr_mean, dynamic_range, rms_variance, vocal_proxy | 7 |
| MFCC mean (low) | coefficients 1-4 | 4 |
| MFCC mean (high) | coefficients 5-13 | 9 |
| MFCC std | all 13 | 13 |
| Spectral contrast | 7 bands | 7 |
| Chroma | 12 pitch classes | 12 |

### Per-Zone Weights

| Zone | Energy/Rhythm | Timbre scalars | MFCC low | MFCC high | MFCC std | Contrast | Chroma |
|------|--------------|----------------|----------|-----------|----------|----------|--------|
| **Sleep** | 3.0 | 1.5 | 1.0 | 0.5 | 0.5 | 1.0 | 0.5 |
| **Recovery** | 2.5 | 1.5 | 1.0 | 0.5 | 0.5 | 1.0 | 0.5 |
| **Energy** | 3.0 | 1.5 | 0.8 | 0.5 | 0.5 | 1.0 | 0.5 |
| **Focus** | 1.5 | 2.0 | 1.5 | 1.0 | 1.0 | 1.5 | 0.8 |
| **Creative** | 1.5 | 1.5 | 1.5 | 1.0 | 1.0 | 1.5 | 1.0 |
| **Meditation** | 2.0 | 2.0 | 1.5 | 0.8 | 0.8 | 1.5 | 0.8 |
| **Joy** | 2.5 | 1.5 | 1.0 | 0.5 | 0.5 | 1.0 | 2.0 |
| **Calm** | 2.0 | 2.0 | 1.5 | 0.8 | 0.8 | 1.5 | 1.5 |
| **Melancholy** | 1.0 | 1.5 | 2.0 | 1.0 | 1.5 | 2.0 | 2.5 |
| **Heroic** | 2.0 | 1.5 | 1.5 | 0.8 | 1.0 | 1.5 | 2.0 |
| **Mysterious** | 1.0 | 2.5 | 2.0 | 1.0 | 1.5 | 2.5 | 1.5 |
| **Stress Relief** | 2.0 | 2.0 | 1.5 | 0.8 | 0.8 | 1.5 | 1.0 |

### Rationale

- **Arousal-dominant zones** (sleep, energy, recovery): Energy/rhythm scalars weighted 3x because the primary job is filtering by energy level. A quiet track with "wrong" MFCC is still better for sleep than a loud track with "right" MFCC.
- **Valence-dependent zones** (melancholy, joy, calm): Chroma weighted 2-2.5x because valence requires harmonic information. MFCC weighted higher because timbral color carries emotional quality.
- **Texture zones** (mysterious, focus): Contrast and MFCC weighted 2-2.5x because these zones are defined by spectral character — density, brightness, clarity — which is timbral, not energetic.
- **MFCC low vs high**: Coefficients 1-4 weighted ~2x more than 5-13 for all zones (mood depends on broad spectral shape, not fine detail).
- **MFCC std**: Weighted 0.5-1.5x depending on zone. Higher for melancholy/mysterious (emotional evolution matters), lower for sleep/energy (consistency matters more than what the consistency is).

---

## Key Numbers from Literature

| Finding | Value | Source |
|---------|-------|--------|
| Arousal prediction R (from audio) | 0.824 | Eerola et al. |
| Cross-domain arousal prediction R | 0.78 | Schuller et al. 2013 |
| Spectral contrast RMSE (best single feature) | 2.783 | arxiv:2411.00195 |
| MFCC RMSE | 3.420 | arxiv:2411.00195 |
| Chroma RMSE (worst single feature) | 5.482 | arxiv:2411.00195 |
| Sleep music classification accuracy | 78.6% | Scarratt et al. 2023 |
| Sleep loudness Cohen's d | -1.25 | Scarratt et al. 2023 |
| Sleep energy Cohen's d | -1.46 | Scarratt et al. 2023 |
| Focus prediction from audio | r=0.68 frame, r=0.79 song | Kikkert et al. 2022 |
| Learned Mahalanobis accuracy | 81.81% | McFee dissertation |
| Feature importance F1 improvement | +9% (to 76.4%) | Panda et al. 2020 |
| MIREX similarity: timbre weight | 0.95 | MIREX evaluation |
| Groove-bass correlation band | 50-100 Hz | Sub-band flux study |
| Optimal sleep tempo | 60-80 BPM | Frontiers in Sleep 2025 |
| Optimal running tempo | 120-140 BPM | Exercise music studies |

---

## Implementation Plan

### Phase 1: Extract chroma + store
- Return chroma_mean (12 dims) from `_extract_key_mode()` (already computed, currently discarded)
- Add `chroma_mean_json` column to DB schema (bump to v9)
- Add chroma to Soniq tag schema (bump to v0.2)
- **Triggers re-extraction of all tracks** (one-time cost)

### Phase 2: Weighted full-vector zone scoring
- Replace 10-dim flat Euclidean with weighted multi-group distance
- Each zone profile gets a `weights` dict alongside its `target`
- Vector features (MFCC, contrast, chroma) need target vectors per zone — derive from library analysis or use research-based defaults
- Zone target vectors for MFCC/contrast/chroma: use library median of top-scoring tracks as initial targets, then refine

### Phase 3: Upgrade find_similar
- Add chroma to the similarity vector (55 dims total)
- Apply MFCC coefficient weighting (1-4 at 1.5x, 5-13 at 0.7x)
- Weight spectral contrast at 1.2x (best single sentiment predictor)

---

## Sources

- Schuller et al. 2013 — "On the Acoustics of Emotion in Audio" (Frontiers in Psychology)
- Eerola et al. — Audio features for arousal and valence detection
- Scarratt et al. 2023 — "Audio features of sleep music" (PLOS ONE, N=225,626)
- Kikkert et al. 2022 — "Audio and focus using BCI" (PMC8829886)
- Panda, Malheiro & Paiva 2020 — "Audio Features for MER: A Survey" (IEEE TAC)
- Jiang et al. 2002 — "Spectral Contrast Feature" (music type classification)
- McFee — "Learning a Metric for Music Similarity" (UCSD dissertation)
- arxiv:2408.10864 — SHAP analysis of music features
- arxiv:2411.00195 — ML Framework for audio sentiment (MFCC, contrast, chroma comparison)
- arxiv:2504.18799 — Survey on Multimodal Music Emotion Recognition (2025)
- FluCoMa — MFCC perceptual explanation
- Frontiers in Sleep 2025 — Elements of music for sleep
- Brain.fm — Focus music characteristics
- eLife — Neural synchronization and spectral flux
- Zilliz — Cosine vs Euclidean for audio features
