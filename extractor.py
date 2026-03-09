#!/usr/bin/env python3
"""Audio feature extraction using librosa with multi-point sampling.

Per track — 14 scalar features + 4 vector features (45 dims total):
  Scalars: duration, tempo, key, mode, rms_mean (dB), rms_max, rms_variance,
           dynamic_range, centroid_mean (Hz), flatness_mean, spectral_flux,
           onset_strength, beat_strength, vocal_proxy, zcr_mean
  Vectors: mfcc_mean (13), mfcc_std (13), contrast_mean (7) — stored as JSON

Multi-point sampling: 3 x 10s segments at 15%, 50%, 85% of track duration.
Total audio analyzed per track: ~30s (vs full-track = faster, representative).
"""

import logging
import numpy as np
import librosa

log = logging.getLogger(__name__)


def extract_track_features(filepath):
    """Extract all features from an audio file. Returns dict or None on failure."""
    try:
        duration = librosa.get_duration(path=filepath)
    except Exception:
        return None

    if duration < 3:
        return None

    # Load segments for multi-point sampling
    segments = _load_segments(filepath, duration)
    if not segments:
        return None

    # Per-segment features, then aggregate
    seg_feats = []
    for y, sr in segments:
        sf = _segment_features(y, sr)
        if sf:
            seg_feats.append(sf)

    if not seg_feats:
        return None

    result = {"duration": duration}

    # Average scalar features across segments
    for key in ("centroid_mean", "flatness_mean", "spectral_flux",
                "onset_strength", "beat_strength", "vocal_proxy", "zcr_mean"):
        result[key] = float(np.mean([f[key] for f in seg_feats]))

    # RMS: average linear values, then convert to dB for storage
    rms_linear_vals = [f["rms_linear"] for f in seg_feats]
    avg_rms_linear = float(np.mean(rms_linear_vals))
    result["rms_mean"] = float(20 * np.log10(avg_rms_linear + 1e-10))

    # RMS variance: computed from per-segment dB values
    rms_db_vals = [20 * np.log10(v + 1e-10) for v in rms_linear_vals]
    result["rms_variance"] = float(np.var(rms_db_vals)) if len(rms_db_vals) > 1 else 0.0

    # Dynamic range: p95 - p5 of per-frame RMS (dB) across all segments
    all_rms_db = []
    for f in seg_feats:
        all_rms_db.extend(f["_rms_db_frames"])
    if all_rms_db:
        arr = np.array(all_rms_db)
        p95 = float(np.percentile(arr, 95))
        result["dynamic_range"] = p95 - float(np.percentile(arr, 5))
        result["rms_max"] = p95
    else:
        result["dynamic_range"] = 0.0
        result["rms_max"] = result["rms_mean"]

    # MFCC: average mean + std vectors across segments
    mfcc_vecs = [np.array(f["mfcc_mean"]) for f in seg_feats]
    result["mfcc_mean"] = np.mean(mfcc_vecs, axis=0).tolist()

    mfcc_std_vecs = [np.array(f["mfcc_std"]) for f in seg_feats]
    result["mfcc_std"] = np.mean(mfcc_std_vecs, axis=0).tolist()

    # Spectral contrast: average 7-band vectors across segments
    contrast_vecs = [np.array(f["contrast_mean"]) for f in seg_feats]
    result["contrast_mean"] = np.mean(contrast_vecs, axis=0).tolist()

    # Tempo + key/mode from 60s excerpt starting at 30% (catches slow-build tracks)
    try:
        offset = duration * 0.3 if duration > 90 else 0
        y_long, sr = librosa.load(
            filepath, sr=22050, offset=offset, duration=60, mono=True
        )
        tempo, _ = librosa.beat.beat_track(y=y_long, sr=sr)
        result["tempo"] = float(np.atleast_1d(tempo)[0])
        key, mode = _extract_key_mode(y_long, sr)
        result["key"] = key
        result["mode"] = mode
    except Exception as e:
        log.warning("tempo/key extraction failed for %s: %s", filepath, e)
        result["tempo"] = 0.0
        result["key"] = 0
        result["mode"] = 1

    return result


def _load_segments(filepath, duration, seg_dur=10.0):
    """Load 3 segments at 15%, 50%, 85%. Falls back to whole track if short."""
    segments = []

    if duration < 15:
        try:
            y, sr = librosa.load(filepath, sr=22050, mono=True)
            if len(y) >= sr:
                segments.append((y, sr))
        except Exception:
            pass
        return segments

    for pct in (0.15, 0.50, 0.85):
        offset = max(0, duration * pct - seg_dur / 2)
        if offset + seg_dur > duration:
            offset = max(0, duration - seg_dur)
        try:
            y, sr = librosa.load(
                filepath, sr=22050, offset=offset, duration=seg_dur, mono=True
            )
            if len(y) >= sr:
                segments.append((y, sr))
        except Exception:
            continue

    return segments


def _segment_features(y, sr):
    """Extract features from a single audio segment."""
    try:
        # RMS energy (linear)
        rms = librosa.feature.rms(y=y)[0]
        rms_linear = float(np.mean(rms))
        rms_db_frames = librosa.amplitude_to_db(rms, ref=1.0).tolist()

        # Spectral centroid (Hz)
        centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
        centroid_mean = float(np.mean(centroid))

        # Spectral flatness (0-1, higher = noisier)
        flatness = librosa.feature.spectral_flatness(y=y)[0]
        flatness_mean = float(np.mean(flatness))

        # Spectral flux (mean L2 norm of frame-to-frame spectral change)
        S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
        if S.shape[1] > 1:
            diff = np.diff(S, axis=1)
            flux_per_frame = np.sqrt(np.sum(diff ** 2, axis=0))
            spectral_flux = float(np.mean(flux_per_frame))
        else:
            spectral_flux = 0.0

        # Onset strength
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_strength = float(np.mean(onset_env))

        # Beat strength: p75 of onset envelope (robust on short segments
        # where beat_track can't lock onto a pulse reliably)
        beat_strength = float(np.percentile(onset_env, 75))

        # Vocal proxy via HPSS — harmonic ratio dampened by harmonic flatness.
        # Pure harmonic instruments (piano, sax) score high on h_energy/total
        # but also have low spectral flatness. Multiplying by (1 - flatness)
        # penalizes purely tonal content, keeping vocal-like content higher.
        harmonic, _ = librosa.effects.hpss(y)
        h_energy = float(np.sum(harmonic ** 2))
        total_energy = float(np.sum(y ** 2))
        harmonic_ratio = h_energy / total_energy if total_energy > 1e-10 else 0.0
        h_flatness = float(np.mean(librosa.feature.spectral_flatness(y=harmonic)[0]))
        vocal_proxy = harmonic_ratio * (1.0 - h_flatness)

        # MFCC (13 coefficients — mean + std over time)
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_mean = np.mean(mfcc, axis=1).tolist()
        mfcc_std = np.std(mfcc, axis=1).tolist()

        # Spectral contrast (7 bands — piggybacks on STFT already computed)
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        contrast_mean = np.mean(contrast, axis=1).tolist()

        # Zero-crossing rate
        zcr_mean = float(np.mean(librosa.feature.zero_crossing_rate(y)[0]))

        return {
            "rms_linear": rms_linear,
            "centroid_mean": centroid_mean,
            "flatness_mean": flatness_mean,
            "spectral_flux": spectral_flux,
            "onset_strength": onset_strength,
            "beat_strength": beat_strength,
            "vocal_proxy": vocal_proxy,
            "mfcc_mean": mfcc_mean,
            "mfcc_std": mfcc_std,
            "contrast_mean": contrast_mean,
            "zcr_mean": zcr_mean,
            "_rms_db_frames": rms_db_frames,
        }
    except Exception as e:
        log.warning("segment feature extraction failed: %s", e)
        return None


def _extract_key_mode(y, sr):
    """Detect key (0-11, C=0) and mode (0=minor, 1=major) via Krumhansl-Schmuckler."""
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
    chroma_mean = np.mean(chroma, axis=1)

    # Krumhansl-Schmuckler key profiles
    major = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09,
                      2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
    minor = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53,
                      2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

    best_corr = -2.0
    best_key = 0
    best_mode = 1

    for shift in range(12):
        rotated = np.roll(chroma_mean, -shift)
        maj_corr = float(np.corrcoef(rotated, major)[0, 1])
        min_corr = float(np.corrcoef(rotated, minor)[0, 1])

        if maj_corr > best_corr:
            best_corr = maj_corr
            best_key = shift
            best_mode = 1
        if min_corr > best_corr:
            best_corr = min_corr
            best_key = shift
            best_mode = 0

    return best_key, best_mode
