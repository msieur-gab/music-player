"""Audio feature extraction using librosa with multi-point sampling.

Per track -- 15 scalar features + 5 vector features (66 dims total):
  Scalars: duration, tempo, key, mode, rms_mean (dB), rms_max, rms_variance,
           dynamic_range, centroid_mean (Hz), flatness_mean, spectral_flux,
           onset_strength, beat_strength, vocal_proxy, zcr_mean
  Vectors: mfcc_mean (13), mfcc_std (13), contrast_mean (7),
           chroma_mean (12), tonnetz_mean (6) -- stored as JSON

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

    # Single load: up to 90s from 5% in, covers all 3 sample points + tempo/key
    load_offset = max(0, duration * 0.05)
    load_duration = min(90, duration - load_offset)
    try:
        y_full, sr = librosa.load(
            filepath, sr=22050, offset=load_offset, duration=load_duration, mono=True
        )
    except Exception:
        return None

    if len(y_full) < sr:
        return None

    actual_loaded = len(y_full) / sr

    segments = _slice_segments(y_full, sr, actual_loaded)
    if not segments:
        return None

    seg_feats = []
    for y_seg in segments:
        sf = _segment_features(y_seg, sr)
        if sf:
            seg_feats.append(sf)

    if not seg_feats:
        return None

    result = {"duration": duration}

    for key in ("centroid_mean", "flatness_mean", "spectral_flux",
                "onset_strength", "beat_strength", "vocal_proxy", "zcr_mean"):
        result[key] = float(np.mean([f[key] for f in seg_feats]))

    rms_linear_vals = [f["rms_linear"] for f in seg_feats]
    avg_rms_linear = float(np.mean(rms_linear_vals))
    result["rms_mean"] = float(20 * np.log10(avg_rms_linear + 1e-10))

    rms_db_vals = [20 * np.log10(v + 1e-10) for v in rms_linear_vals]
    result["rms_variance"] = float(np.var(rms_db_vals)) if len(rms_db_vals) > 1 else 0.0

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

    mfcc_vecs = [np.array(f["mfcc_mean"]) for f in seg_feats]
    result["mfcc_mean"] = np.mean(mfcc_vecs, axis=0).tolist()

    mfcc_std_vecs = [np.array(f["mfcc_std"]) for f in seg_feats]
    result["mfcc_std"] = np.mean(mfcc_std_vecs, axis=0).tolist()

    contrast_vecs = [np.array(f["contrast_mean"]) for f in seg_feats]
    result["contrast_mean"] = np.mean(contrast_vecs, axis=0).tolist()

    chroma_vecs = [np.array(f["chroma_mean"]) for f in seg_feats]
    result["chroma_mean"] = np.mean(chroma_vecs, axis=0).tolist()

    tonnetz_vecs = [np.array(f["tonnetz_mean"]) for f in seg_feats]
    result["tonnetz_mean"] = np.mean(tonnetz_vecs, axis=0).tolist()

    try:
        mid = len(y_full) // 2
        half_window = min(30 * sr, mid)
        y_tempo = y_full[mid - half_window:mid + half_window]
        tempo, _ = librosa.beat.beat_track(y=y_tempo, sr=sr)
        result["tempo"] = float(np.atleast_1d(tempo)[0])
        key, mode = _extract_key_mode(y_tempo, sr)
        result["key"] = key
        result["mode"] = mode
    except Exception as e:
        log.warning("tempo/key extraction failed for %s: %s", filepath, e)
        result["tempo"] = 0.0
        result["key"] = 0
        result["mode"] = 1

    return result


def _slice_segments(y, sr, loaded_dur, seg_dur=10.0):
    """Slice 3 segments at 15%, 50%, 85% of the loaded audio buffer."""
    seg_samples = int(seg_dur * sr)

    if loaded_dur < 15:
        return [y]

    segments = []
    for pct in (0.15, 0.50, 0.85):
        center = int(loaded_dur * pct * sr)
        start = max(0, center - seg_samples // 2)
        end = start + seg_samples
        if end > len(y):
            start = max(0, len(y) - seg_samples)
            end = len(y)
        seg = y[start:end]
        if len(seg) >= sr:
            segments.append(seg)

    return segments


def _segment_features(y, sr):
    """Extract features from a single audio segment.

    Computes STFT once and reuses it for all spectral features.
    """
    try:
        S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
        S_power = S ** 2

        rms = np.sqrt(np.mean(S_power, axis=0))
        rms_linear = float(np.mean(rms))
        rms_db_frames = (20 * np.log10(rms + 1e-10)).tolist()

        centroid = librosa.feature.spectral_centroid(S=S, sr=sr)[0]
        centroid_mean = float(np.mean(centroid))

        flatness = librosa.feature.spectral_flatness(S=S)[0]
        flatness_mean = float(np.mean(flatness))

        if S.shape[1] > 1:
            diff = np.diff(S, axis=1)
            flux_per_frame = np.sqrt(np.sum(diff ** 2, axis=0))
            spectral_flux = float(np.mean(flux_per_frame))
        else:
            spectral_flux = 0.0

        S_db = librosa.power_to_db(S_power)
        onset_env = librosa.onset.onset_strength(S=S_db, sr=sr)
        onset_strength = float(np.mean(onset_env))

        beat_strength = float(np.percentile(onset_env, 75))

        H, _ = librosa.decompose.hpss(S)
        h_energy = float(np.sum(H ** 2))
        total_energy = float(np.sum(S_power))
        harmonic_ratio = h_energy / total_energy if total_energy > 1e-10 else 0.0
        h_flatness = float(np.mean(librosa.feature.spectral_flatness(S=H)[0]))
        vocal_proxy = harmonic_ratio * (1.0 - h_flatness)

        mel_S = librosa.feature.melspectrogram(S=S_power, sr=sr)
        mfcc = librosa.feature.mfcc(S=librosa.power_to_db(mel_S), n_mfcc=13)
        mfcc_mean = np.mean(mfcc, axis=1).tolist()
        mfcc_std = np.std(mfcc, axis=1).tolist()

        contrast = librosa.feature.spectral_contrast(S=S, sr=sr)
        contrast_mean = np.mean(contrast, axis=1).tolist()

        chroma = librosa.feature.chroma_stft(S=S_power, sr=sr)
        chroma_mean = np.mean(chroma, axis=1).tolist()

        tonnetz = librosa.feature.tonnetz(chroma=chroma)
        tonnetz_mean = np.mean(tonnetz, axis=1).tolist()

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
            "chroma_mean": chroma_mean,
            "tonnetz_mean": tonnetz_mean,
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
