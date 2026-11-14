"""Speaker diarization, role classification, and overlap detection.

Neural pipeline (un-gated local weights, CUDA-accelerated when available):
- Speech gating: Silero VAD (MIT, bundled in wheel)
- Frame powerset segmentation & simultaneous-overlap detection:
  ``onnx-community/pyannote-segmentation-3.0`` (MIT, 7-class powerset ONNX)
- Speaker embeddings: ``speechbrain/spkrec-ecapa-voxceleb`` (Apache-2.0)
- Adaptive clustering: duration-weighted cosine agglomerative clustering
  without assuming a fixed speaker count.
- Multi-modal role classification (``PRESENTER`` / ``DOCUMENTARY`` / ``UNKNOWN``)
  combining visual video-playback churn from ``ffmpeg`` frame diffs with
  temporal recurrence and overlap cues (no general-purpose LLM).

Synthetic/non-speech fallback: when Silero VAD finds zero human speech
(e.g. pure synthetic harmonic test tones) or ``DSO_DIARIZER=acoustic``,
falls back to pitch/spectral/MFCC acoustic clustering so offline unit tests
remain fast and deterministic without producing any WAV files on disk.
"""
from __future__ import annotations

import os
import subprocess
import threading
import wave
from pathlib import Path
from typing import Any

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist

_SAMPLE_RATE = 16000
_FRAME_HZ = 100
_VIDEO_FPS = 2
_VIDEO_W = 160
_VIDEO_H = 90
_SEG_REPO = "onnx-community/pyannote-segmentation-3.0"
_SEG_FILENAME = "onnx/model.onnx"
_EMB_REPO = "speechbrain/spkrec-ecapa-voxceleb"

_ROLE_TITLES = {
    "PRESENTER": "Presenter",
    "DOCUMENTARY": "Documentary",
    "UNKNOWN": "Unknown",
}

_MODEL_LOCK = threading.Lock()
_MODEL_CACHE: dict[str, Any] = {}


def _read_wav_mono_16k(wav_path: Path) -> tuple[int, np.ndarray]:
    with wave.open(str(wav_path), "rb") as wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        nframes = wf.getnframes()
        raw = wf.readframes(nframes)
    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if nch > 1:
        samples = samples.reshape(-1, nch).mean(axis=1)
    return sr, samples


def _load_neural_models() -> tuple[Any, Any, Any, str]:
    """Lazily load Silero VAD, Pyannote segmentation ONNX, and SpeechBrain ECAPA."""
    with _MODEL_LOCK:
        if "ready" in _MODEL_CACHE:
            return (
                _MODEL_CACHE["vad"],
                _MODEL_CACHE["seg_sess"],
                _MODEL_CACHE["ecapa"],
                _MODEL_CACHE["device"],
            )

        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        import onnxruntime as ort
        import torch
        from huggingface_hub import hf_hub_download
        from silero_vad import load_silero_vad
        from speechbrain.inference.speaker import EncoderClassifier
        from speechbrain.utils.fetching import LocalStrategy

        vad_model = load_silero_vad(onnx=True)
        try:
            seg_path = hf_hub_download(_SEG_REPO, _SEG_FILENAME, local_files_only=True)
        except Exception:
            seg_path = hf_hub_download(_SEG_REPO, _SEG_FILENAME)

        sess_opts = ort.SessionOptions()
        sess_opts.log_severity_level = 3
        seg_sess = ort.InferenceSession(
            seg_path, sess_options=sess_opts, providers=["CPUExecutionProvider"]
        )

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        cache_dir = Path.home() / ".cache" / "huggingface" / "speechbrain_ecapa_voxceleb"
        ecapa = EncoderClassifier.from_hparams(
            source=_EMB_REPO,
            savedir=str(cache_dir),
            run_opts={"device": device},
            local_strategy=LocalStrategy.COPY,
        )

        _MODEL_CACHE.update(
            vad=vad_model,
            seg_sess=seg_sess,
            ecapa=ecapa,
            device=device,
            ready=True,
        )
        return vad_model, seg_sess, ecapa, device


def extract_playback_windows(video_path: Path | None) -> list[tuple[float, float]]:
    """Detect sustained full-frame video/media playback intervals via 2 fps gray diffs.

    Masks out the right/bottom edge strip where conference PiP webcam thumbnails sit
    so presenter webcam motion on static slides does not mimic documentary playback.
    """
    if video_path is None or not Path(video_path).is_file():
        return []
    proc = subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-i",
            str(video_path),
            "-vf",
            f"fps={_VIDEO_FPS},scale={_VIDEO_W}:{_VIDEO_H},format=gray",
            "-f",
            "rawvideo",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0:
        return []
    frame_bytes = _VIDEO_W * _VIDEO_H
    n_frames = len(proc.stdout) // frame_bytes
    if n_frames < 4:
        return []

    arr = (
        np.frombuffer(proc.stdout[: n_frames * frame_bytes], dtype=np.uint8)
        .reshape(n_frames, _VIDEO_H, _VIDEO_W)
        .astype(np.float32)
    )
    core_diff = np.abs(arr[1:] - arr[:-1])[:, :76, :120]
    changed_frac = (core_diff > 12.0).mean(axis=(1, 2))
    n_ticks = len(changed_frac)

    active = np.zeros(n_ticks, dtype=bool)
    hi = np.zeros(n_ticks, dtype=bool)
    lo = np.zeros(n_ticks, dtype=bool)
    half_w = 5  # +/- 2.5s smoothing window at 2 fps
    wide_w = 9  # +/- 4.5s envelope window for interview shots inside documentaries
    for i in range(n_ticks):
        win = changed_frac[max(0, i - half_w) : min(n_ticks, i + half_w + 1)]
        l_win = changed_frac[max(0, i - wide_w) : i + 1]
        r_win = changed_frac[i : min(n_ticks, i + wide_w + 1)]
        w_win = changed_frac[max(0, i - wide_w) : min(n_ticks, i + wide_w + 1)]
        med = float(np.median(win))
        if med >= 0.070 and float((win > 0.08).mean()) >= 0.50:
            hi[i] = True
        if med >= 0.026 or (
            float(np.mean(w_win)) >= 0.045
            and int((w_win > 0.02).sum()) >= 4
            and int((l_win > 0.015).sum()) >= 1
            and int((r_win > 0.015).sum()) >= 1
        ):
            lo[i] = True

    # Bridge brief low-motion interview/title spans <= 9.0s inside candidate playback envelopes.
    on_lo = np.where(lo)[0]
    for k in range(len(on_lo) - 1):
        if int(on_lo[k + 1] - on_lo[k]) <= 18:
            lo[on_lo[k] : on_lo[k + 1] + 1] = True

    # Keep hysteresis envelopes that contain sustained high-confidence video motion.
    i = 0
    while i < n_ticks:
        if not lo[i]:
            i += 1
            continue
        j = i
        while j < n_ticks and lo[j]:
            j += 1
        if int(hi[i:j].sum()) >= 4:
            active[i:j] = True
        i = j

    # Bridge gaps <= 8.0s between adjacent playback blocks.
    on_idx = np.where(active)[0]
    for k in range(len(on_idx) - 1):
        if int(on_idx[k + 1] - on_idx[k]) <= 16:
            active[on_idx[k] : on_idx[k + 1] + 1] = True

    min_ticks = 24 if n_ticks >= 240 else 4  # >= 12.0s on full recordings, >= 2.0s on short clips
    windows: list[tuple[float, float]] = []
    i = 0
    while i < n_ticks:
        if not active[i]:
            i += 1
            continue
        j = i
        while j < n_ticks and active[j]:
            j += 1
        if j - i >= min_ticks:
            windows.append((round(i / _VIDEO_FPS, 3), round((j + 1) / _VIDEO_FPS, 3)))
        i = j
    return windows


# ---------------------------------------------------------------------------
# Acoustic harmonic fallback (used when no real speech exists or neural off)
# ---------------------------------------------------------------------------

def _mfcc_dct(n_filters: int, n_coeffs: int) -> np.ndarray:
    n = np.arange(n_filters)[None, :]
    k = np.arange(1, n_coeffs + 1)[:, None]
    return np.sqrt(2.0 / n_filters) * np.cos(np.pi * k * (2 * n + 1) / (2 * n_filters))


def _mel_filterbank(sr: int, n_fft: int, n_filters: int = 24) -> np.ndarray:
    def hz_to_mel(hz: np.ndarray) -> np.ndarray:
        return 2595.0 * np.log10(1.0 + hz / 700.0)

    def mel_to_hz(mel: np.ndarray) -> np.ndarray:
        return 700.0 * (10.0 ** (mel / 2595.0) - 1.0)

    mels = np.linspace(hz_to_mel(np.array(80.0)), hz_to_mel(np.array(sr / 2.0)), n_filters + 2)
    bins = np.floor((n_fft + 1) * mel_to_hz(mels) / sr).astype(int)
    fb = np.zeros((n_filters, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_filters + 1):
        lo, mid, hi = bins[m - 1], bins[m], bins[m + 1]
        for k in range(lo, mid):
            if mid > lo:
                fb[m - 1, k] = (k - lo) / (mid - lo)
        for k in range(mid, hi):
            if hi > mid:
                fb[m - 1, k] = (hi - k) / (hi - mid)
    return fb


def _segment_acoustic_features(sr: int, samples: np.ndarray, t0: float, t1: float) -> np.ndarray | None:
    i0 = max(0, int(t0 * sr))
    i1 = min(len(samples), int(t1 * sr))
    seg = samples[i0:i1]
    if len(seg) < int(0.15 * sr):
        return None
    if len(seg) > 8 * sr:
        mid = len(seg) // 2
        seg = seg[mid - 4 * sr : mid + 4 * sr]
    n_fft = 512
    hop = 160
    if len(seg) < n_fft:
        seg = np.pad(seg, (0, n_fft - len(seg)))
    frames = np.lib.stride_tricks.sliding_window_view(seg, n_fft)[::hop]
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    voiced = frames[rms > max(0.01, float(np.percentile(rms, 30)))]
    if len(voiced) < 3:
        voiced = frames
    if len(voiced) > 250:
        voiced = voiced[np.linspace(0, len(voiced) - 1, 250, dtype=int)]

    win = np.hanning(n_fft).astype(np.float32)
    spec = np.abs(np.fft.rfft(voiced * win, axis=1)) + 1e-9
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sr)
    mag = spec.mean(axis=0)
    centroid = float((freqs * mag).sum() / mag.sum())

    f0s = []
    min_lag, max_lag = max(20, sr // 450), min(n_fft - 1, sr // 70)
    for fr in voiced[:80]:
        f = fr - fr.mean()
        if np.max(np.abs(f)) < 1e-4:
            continue
        ac = np.correlate(f, f, mode="full")[len(f) - 1 :]
        if ac[0] <= 0:
            continue
        ac = ac / ac[0]
        lag = int(np.argmax(ac[min_lag:max_lag])) + min_lag
        if ac[lag] > 0.35:
            f0s.append(sr / lag)
    f0 = float(np.median(f0s)) if f0s else 150.0

    fb = _mel_filterbank(sr, n_fft, 24)
    mel_e = np.log(np.maximum(1e-9, (spec * spec) @ fb.T))
    mfcc = (mel_e @ _mfcc_dct(24, 12).T).mean(axis=0)
    return np.concatenate([[np.log2(max(50.0, f0) / 120.0), np.log2(max(100.0, centroid) / 800.0)], mfcc]).astype(
        np.float32
    )


def _silhouette(dists: np.ndarray, labels: np.ndarray) -> float:
    n = len(labels)
    uniq = np.unique(labels)
    if len(uniq) < 2 or len(uniq) >= n:
        return -1.0
    scores = []
    for i in range(n):
        c = labels[i]
        same = (labels == c) & (np.arange(n) != i)
        a = float(dists[i, same].mean()) if same.any() else 0.0
        b = min(float(dists[i, labels == o].mean()) for o in uniq if o != c)
        scores.append((b - a) / max(a, b, 1e-9))
    return float(np.mean(scores))


def _diarize_acoustic(
    sr: int, samples: np.ndarray, segments: list[dict[str, Any]], max_speakers: int
) -> tuple[list[int], list[float | None], list[bool], list[float], list[float], list[list[dict[str, Any]]]]:
    n = len(segments)
    feats: list[np.ndarray] = []
    valid_idx: list[int] = []
    for i, s in enumerate(segments):
        f = _segment_acoustic_features(sr, samples, float(s["start"]), float(s["end"]))
        if f is not None:
            feats.append(f)
            valid_idx.append(i)

    if not feats:
        return (
            [0] * n,
            [None] * n,
            [False] * n,
            [0.0] * n,
            [0.0] * n,
            [[] for _ in range(n)],
        )

    mat = np.stack(feats, axis=0)
    std = mat.std(axis=0)
    floor = np.array([0.12, 0.12, 0.4] + [1.5] * max(0, mat.shape[1] - 3), dtype=np.float32)
    scale = np.maximum(std, floor[: mat.shape[1]])
    norm = (mat - mat.mean(axis=0)) / scale
    norm[:, 0] *= 2.0
    norm[:, 1] *= 1.5

    if len(norm) == 1:
        raw_labels = np.array([1])
    elif float(np.max(pdist(norm, metric="euclidean"))) < 3.5:
        raw_labels = np.ones(len(norm), dtype=int)
    else:
        Z = linkage(norm, method="ward")
        dists = np.sqrt(((norm[:, None, :] - norm[None, :, :]) ** 2).sum(axis=2))
        upper = min(max_speakers, len(norm) - 1, 16)
        best_k, best_score, best_lbls = 1, 0.24, np.ones(len(norm), dtype=int)
        for k in range(2, upper + 1):
            lbls = fcluster(Z, t=k, criterion="maxclust")
            sc = _silhouette(dists, lbls)
            if sc > best_score:
                best_k, best_score, best_lbls = k, sc, lbls
        raw_labels = best_lbls

    seg_cluster = [-1] * n
    for pos, idx in enumerate(valid_idx):
        seg_cluster[idx] = int(raw_labels[pos]) - 1

    # Assign any ultra-short segments to nearest neighbor speaker
    last = next((c for c in seg_cluster if c >= 0), 0)
    for i in range(n):
        if seg_cluster[i] < 0:
            seg_cluster[i] = last
        else:
            last = seg_cluster[i]

    confs = [None] * n
    # Honest normalized distance margin for valid feature vectors
    if len(set(seg_cluster)) >= 2 and len(valid_idx) >= 2:
        uniq_c = sorted(set(seg_cluster))
        c_vecs = {
            c: np.mean([norm[pos] for pos, idx in enumerate(valid_idx) if seg_cluster[idx] == c], axis=0)
            for c in uniq_c
        }
        for pos, idx in enumerate(valid_idx):
            ds = sorted(float(np.linalg.norm(norm[pos] - c_vecs[c])) for c in uniq_c)
            if ds[1] > 1e-6:
                confs[idx] = round(float(max(0.0, min(1.0, (ds[1] - ds[0]) / max(ds[1], 1.0)))), 4)
    elif len(set(seg_cluster)) == 1:
        for idx in valid_idx:
            confs[idx] = 1.0

    return (
        seg_cluster,
        confs,
        [False] * n,
        [0.0] * n,
        [0.0] * n,
        [[] for _ in range(n)],
    )


# ---------------------------------------------------------------------------
# Neural Diarization Helpers
# ---------------------------------------------------------------------------

def _run_pyannote_segmentation(
    samples: np.ndarray, seg_sess: Any
) -> tuple[np.ndarray, np.ndarray]:
    """Run sliding-window pyannote-segmentation-3.0 ONNX -> (p_ov, p_chg) at 100 Hz."""
    in_name = seg_sess.get_inputs()[0].name
    win_n = 10 * _SAMPLE_RATE
    step_s = 4.0 if len(samples) <= 3600 * _SAMPLE_RATE else 5.0
    step_n = int(step_s * _SAMPLE_RATE)

    starts = list(range(0, max(1, len(samples) - win_n + 1), step_n))
    if not starts or starts[-1] + win_n < len(samples):
        starts.append(max(0, len(samples) - win_n))

    n100 = int(np.ceil(len(samples) / _SAMPLE_RATE * _FRAME_HZ))
    p_ov = np.zeros(n100, dtype=np.float32)
    p_chg = np.zeros(n100, dtype=np.float32)
    wsum = np.zeros(n100, dtype=np.float32)

    powerset_map = np.array(
        [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [1, 1, 0], [1, 0, 1], [0, 1, 1]],
        dtype=np.float32,
    )
    diff_lag = 12  # ~200ms turn-transition horizon at ~58.9 Hz

    for b0 in range(0, len(starts), 64):
        sub_st = starts[b0 : b0 + 64]
        batch = np.stack(
            [
                np.pad(samples[st : st + win_n], (0, max(0, win_n - len(samples[st : st + win_n]))))[
                    None, :
                ]
                for st in sub_st
            ]
        ).astype(np.float32)
        probs = np.exp(seg_sess.run(None, {in_name: batch})[0])
        nf = probs.shape[1]
        t_src = (np.arange(nf, dtype=np.float32) + 0.5) / nf * 10.0

        for idx, st in enumerate(sub_st):
            pr = probs[idx]
            act = pr @ powerset_map
            chg = np.zeros(nf, dtype=np.float32)
            if nf > 2 * diff_lag:
                diff = np.abs(act[diff_lag:] - act[:-diff_lag]).sum(axis=-1) * 0.5
                chg[diff_lag // 2 : diff_lag // 2 + len(diff)] = diff
            t0 = st / _SAMPLE_RATE
            g0 = max(0, int(np.floor(t0 * _FRAME_HZ)))
            g1 = min(n100, int(np.ceil((t0 + 10.0) * _FRAME_HZ)))
            if g1 <= g0:
                continue
            # Interpolate ~58.9 Hz powerset outputs onto every 100 Hz bin so overlap/change curves have zero holes.
            t_dst = np.arange(g0, g1, dtype=np.float32) / _FRAME_HZ - t0
            ew_win = (np.sin(np.pi * np.clip(t_dst, 0.0, 10.0) / 10.0) ** 2 + 0.05).astype(np.float32)
            ov_win = np.interp(t_dst, t_src, pr[:, 4:7].sum(axis=-1)).astype(np.float32)
            chg_win = np.interp(t_dst, t_src, chg).astype(np.float32)
            p_ov[g0:g1] += ew_win * ov_win
            p_chg[g0:g1] += ew_win * chg_win
            wsum[g0:g1] += ew_win

    valid = wsum > 0
    p_ov[valid] /= wsum[valid]
    p_chg[valid] /= wsum[valid]
    return p_ov, p_chg


def _encode_batch_slice(
    wavs: list[np.ndarray], idxs: list[int], ecapa: Any, device: str
) -> np.ndarray:
    import torch

    ml = max(1, max(len(wavs[i]) for i in idxs))
    wt = torch.zeros(len(idxs), ml, device=device)
    lt = torch.zeros(len(idxs), device=device)
    for k, idx in enumerate(idxs):
        w = wavs[idx]
        if len(w) > 0:
            wt[k, : len(w)] = torch.from_numpy(w).to(device)
            lt[k] = len(w) / ml
        else:
            lt[k] = 1.0 / ml
    with torch.no_grad():
        out = ecapa.encode_batch(wt, lt).squeeze(1).cpu().numpy()
    del wt, lt
    return out / (np.linalg.norm(out, axis=-1, keepdims=True) + 1e-8)


def _encode_ecapa_batch(wavs: list[np.ndarray], ecapa: Any, device: str) -> np.ndarray:
    """Length-sorted VRAM-safe batched 192-dim L2-normalized ECAPA-TDNN embeddings."""
    import torch

    n = len(wavs)
    if n == 0:
        return np.zeros((0, 192), dtype=np.float32)

    # Descending length order allocates max conv/workspace blocks first so shorter batches reuse them
    # without monotonic caching-allocator fragmentation across >1,000 segments.
    order = sorted(range(n), key=lambda i: len(wavs[i]), reverse=True)
    embs = np.zeros((n, 192), dtype=np.float32)
    pos = 0
    while pos < n:
        longest_next = len(wavs[order[pos]])
        bs = 8 if longest_next > 6 * _SAMPLE_RATE else 16
        idxs = order[pos : pos + bs]
        try:
            out = _encode_batch_slice(wavs, idxs, ecapa, device)
            for k, idx in enumerate(idxs):
                embs[idx] = out[k]
        except RuntimeError as exc:
            if not (device.startswith("cuda") and "out of memory" in str(exc).lower()):
                raise
            try:
                torch.cuda.empty_cache()
            except Exception:
                pass
            # Retry item-by-item on CUDA first (~80 MB peak); fall back to CPU only if GPU stays full.
            for idx in idxs:
                try:
                    embs[idx] = _encode_batch_slice(wavs, [idx], ecapa, device)[0]
                except RuntimeError as exc2:
                    if "out of memory" not in str(exc2).lower():
                        raise
                    try:
                        torch.cuda.empty_cache()
                    except Exception:
                        pass
                    ecapa.to("cpu")
                    ecapa.device = "cpu"
                    with _MODEL_LOCK:
                        if _MODEL_CACHE.get("ecapa") is ecapa:
                            _MODEL_CACHE["device"] = "cpu"
                    embs[idx] = _encode_batch_slice(wavs, [idx], ecapa, "cpu")[0]
                    device = "cpu"
        if device.startswith("cuda") and torch.cuda.memory_reserved() > 1_000_000_000:
            torch.cuda.empty_cache()
        pos += bs
    if device.startswith("cuda"):
        try:
            torch.cuda.empty_cache()
        except Exception:
            pass
    return embs


def _slice_voiced_audio(
    samples: np.ndarray, a: float, b: float, mask_slice: np.ndarray
) -> np.ndarray:
    on = np.where(mask_slice)[0]
    if len(on) < 25:
        return samples[int(a * _SAMPLE_RATE) : int(b * _SAMPLE_RATE)]
    pieces = []
    breaks = np.where(np.diff(on) > 1)[0]
    r_starts = [0] + [int(x + 1) for x in breaks]
    r_ends = [int(x) for x in breaks] + [len(on) - 1]
    for r0, r1 in zip(r_starts, r_ends):
        s0 = int((a + on[r0] / _FRAME_HZ) * _SAMPLE_RATE)
        s1 = int((a + (on[r1] + 1) / _FRAME_HZ) * _SAMPLE_RATE)
        if s1 > s0:
            pieces.append(samples[s0:s1])
    return np.concatenate(pieces) if pieces else samples[int(a * _SAMPLE_RATE) : int(b * _SAMPLE_RATE)]


def _merge_centroids(
    vecs: dict[int, np.ndarray],
    durs: dict[int, float],
    min_sim: float,
    fold_min_dur: float = 0.0,
    fold_sim: float = 0.52,
) -> tuple[dict[int, np.ndarray], dict[int, float]]:
    """Iteratively merge close L2-normalized speaker centroids."""
    while len(vecs) > 1:
        keys = sorted(vecs.keys())
        best_pair = None
        best_sim = -1.0
        for ai in range(len(keys)):
            for bi in range(ai + 1, len(keys)):
                ka, kb = keys[ai], keys[bi]
                sim = float(vecs[ka] @ vecs[kb])
                min_d = min(durs[ka], durs[kb])
                max_d = max(durs[ka], durs[kb])
                allow = (sim >= min_sim) or (
                    fold_min_dur > 0.0 and min_d < fold_min_dur and max_d >= 4.0 and sim >= fold_sim
                )
                if allow and sim > best_sim:
                    best_sim = sim
                    best_pair = (ka, kb)
        if best_pair is None:
            break
        ka, kb = best_pair
        if durs[ka] < durs[kb]:
            ka, kb = kb, ka
        v = vecs[ka] * durs[ka] + vecs[kb] * durs[kb]
        vecs[ka] = v / (np.linalg.norm(v) + 1e-8)
        durs[ka] += durs[kb]
        del vecs[kb]
        del durs[kb]
    return vecs, durs


def _cluster_seed_embeddings(
    embs: np.ndarray,
    seg_vdur: list[float],
    seg_pure: list[bool],
    max_speakers: int,
) -> np.ndarray:
    """Cluster clean single-speaker anchor seeds with complete linkage + centroid merge."""
    from sklearn.cluster import AgglomerativeClustering

    n = len(embs)
    seed = [i for i, ok in enumerate(seg_pure) if ok]
    if not seed:
        seed = [i for i, vd in enumerate(seg_vdur) if vd >= 0.4] or list(range(n))

    if len(seed) == 1:
        return embs[seed[0] : seed[0] + 1]

    # Prefer >=2.4s pure anchor seeds so short noisy turns cannot bridge distinct presenters.
    anchors = [i for i in seed if seg_vdur[i] >= 2.4]
    if len(anchors) < 4:
        anchors = seed
        short_seeds: list[int] = []
    else:
        anchor_set = set(anchors)
        short_seeds = [i for i in seed if i not in anchor_set]

    if len(anchors) == 1:
        vecs = {0: embs[anchors[0]].copy()}
        durs = {0: max(0.25, seg_vdur[anchors[0]])}
    else:
        sl = AgglomerativeClustering(
            n_clusters=None, distance_threshold=0.52, metric="cosine", linkage="complete"
        ).fit_predict(embs[anchors])
        c_vecs: dict[int, np.ndarray] = {}
        c_durs: dict[int, float] = {}
        for k_i, si in enumerate(anchors):
            lb = int(sl[k_i])
            ds = max(0.25, seg_vdur[si])
            c_vecs[lb] = c_vecs.get(lb, np.zeros(embs.shape[1], dtype=np.float32)) + embs[si] * ds
            c_durs[lb] = c_durs.get(lb, 0.0) + ds
        vecs = {lb: v / (np.linalg.norm(v) + 1e-8) for lb, v in c_vecs.items()}
        durs = dict(c_durs)

    vecs, durs = _merge_centroids(vecs, durs, min_sim=0.58)

    # Cluster unmatched short seeds independently only when supported by >=2 turns or >=4.5s voiced speech
    # so single short presenter turns cannot spawn spurious UNKNOWN speaker IDs.
    if short_seeds:
        anchor_mat = np.stack([vecs[k] for k in sorted(vecs.keys())], axis=0)
        unmatched = [i for i in short_seeds if float((embs[i] @ anchor_mat.T).max()) < 0.48]
        if len(unmatched) == 1 and seg_vdur[unmatched[0]] >= 4.5:
            next_k = max(vecs.keys()) + 1
            vecs[next_k] = embs[unmatched[0]].copy()
            durs[next_k] = max(0.25, seg_vdur[unmatched[0]])
        elif len(unmatched) > 1:
            sl_u = AgglomerativeClustering(
                n_clusters=None, distance_threshold=0.52, metric="cosine", linkage="complete"
            ).fit_predict(embs[unmatched])
            next_k = max(vecs.keys()) + 1
            u_vecs: dict[int, np.ndarray] = {}
            u_durs: dict[int, float] = {}
            u_cnts: dict[int, int] = {}
            for k_i, si in enumerate(unmatched):
                lb = next_k + int(sl_u[k_i])
                ds = max(0.25, seg_vdur[si])
                u_vecs[lb] = u_vecs.get(lb, np.zeros(embs.shape[1], dtype=np.float32)) + embs[si] * ds
                u_durs[lb] = u_durs.get(lb, 0.0) + ds
                u_cnts[lb] = u_cnts.get(lb, 0) + 1
            for lb, v in u_vecs.items():
                if u_cnts[lb] >= 2 or u_durs[lb] >= 4.5:
                    vecs[lb] = v / (np.linalg.norm(v) + 1e-8)
                    durs[lb] = u_durs[lb]

    vecs, durs = _merge_centroids(vecs, durs, min_sim=0.58, fold_min_dur=8.0, fold_sim=0.45)

    # If still over max_speakers, fold only the smallest residual cluster into its closest match.
    while len(vecs) > max(1, max_speakers):
        keys = sorted(vecs.keys())
        smallest = min(keys, key=lambda k: durs[k])
        target = max((k for k in keys if k != smallest), key=lambda k: float(vecs[smallest] @ vecs[k]))
        v = vecs[target] * durs[target] + vecs[smallest] * durs[smallest]
        vecs[target] = v / (np.linalg.norm(v) + 1e-8)
        durs[target] += durs[smallest]
        del vecs[smallest]
        del durs[smallest]

    return np.stack([vecs[k] for k in sorted(vecs.keys())], axis=0)


def _extract_sub_turns(
    samples: np.ndarray,
    segments: list[dict[str, Any]],
    vad_mask: np.ndarray,
    p_ov: np.ndarray,
    p_chg: np.ndarray,
    centroids: np.ndarray,
    seg_cluster: list[int],
    seg_overlap: list[bool],
    ecapa: Any,
    device: str,
) -> list[list[dict[str, Any]]]:
    """Identify sub-turns inside long, turn-switching, or overlapping Whisper segments."""
    n = len(segments)
    n100 = len(vad_mask)
    cand_items: list[tuple[int, float, float, bool, np.ndarray]] = []
    sub_turns_out: list[list[dict[str, Any]]] = [[] for _ in range(n)]

    for i, s in enumerate(segments):
        a, b = float(s["start"]), float(s["end"])
        a0, b0 = max(0, int(a * _FRAME_HZ)), min(n100, int(b * _FRAME_HZ))
        if b0 <= a0:
            continue
        chg = p_chg[a0:b0]
        has_switch = (chg[50:-50].max() > 0.50) if (b0 - a0) > 150 else False
        if (b - a) < 5.0 and not has_switch and not seg_overlap[i]:
            sub_turns_out[i] = [
                {
                    "start": round(a, 3),
                    "end": round(b, 3),
                    "_cluster": seg_cluster[i],
                    "overlap": seg_overlap[i],
                }
            ]
            continue

        cuts = [0]
        last_c = 0
        for f in range(60, max(60, len(chg) - 60)):
            if (
                chg[f] > 0.45
                and chg[f] == chg[max(0, f - 25) : min(len(chg), f + 26)].max()
                and (f - last_c) >= 100
            ):
                cuts.append(f)
                last_c = f
        cuts.append(b0 - a0)

        for ci in range(len(cuts) - 1):
            ca, cb = cuts[ci], cuts[ci + 1]
            sub_vad = vad_mask[a0 + ca : a0 + cb]
            sub_ov = p_ov[a0 + ca : a0 + cb]
            on = np.where(sub_vad)[0]
            if len(on) < 35:
                continue
            # Split across silence gaps >= 0.8s so separate turns stay resolved
            breaks = np.where(np.diff(on) > 80)[0]
            for gs, ge in zip([0] + [int(x + 1) for x in breaks], [int(x) for x in breaks] + [len(on) - 1]):
                ra, rb = ca + int(on[gs]), ca + int(on[ge]) + 1
                t0, t1 = round(a + ra / _FRAME_HZ, 3), round(a + rb / _FRAME_HZ, 3)
                if t1 - t0 < 0.45:
                    continue
                clean_mask = vad_mask[a0 + ra : a0 + rb] & (p_ov[a0 + ra : a0 + rb] < 0.42)
                if int(clean_mask.sum()) < 25:
                    clean_mask = vad_mask[a0 + ra : a0 + rb]
                wav = _slice_voiced_audio(samples, t0, t1, clean_mask)[: min(12 * _SAMPLE_RATE, int((t1 - t0) * _SAMPLE_RATE))]
                is_ov = bool((p_ov[a0 + ra : a0 + rb] > 0.42).mean() >= 0.15)
                if len(wav) >= int(0.35 * _SAMPLE_RATE):
                    cand_items.append((i, t0, t1, is_ov, wav))

    if cand_items:
        sub_embs = _encode_ecapa_batch([c[4] for c in cand_items], ecapa, device)
        sub_lbls = (sub_embs @ centroids.T).argmax(axis=1)
        for pos, (seg_idx, t0, t1, is_ov, _) in enumerate(cand_items):
            cid = int(sub_lbls[pos])
            cur_list = sub_turns_out[seg_idx]
            if (
                cur_list
                and cur_list[-1]["_cluster"] == cid
                and cur_list[-1]["overlap"] == is_ov
                and t0 - cur_list[-1]["end"] <= 1.2
            ):
                cur_list[-1]["end"] = t1
            else:
                cur_list.append({"start": t0, "end": t1, "_cluster": cid, "overlap": is_ov})

    for i, s in enumerate(segments):
        if not sub_turns_out[i]:
            sub_turns_out[i] = [
                {
                    "start": round(float(s["start"]), 3),
                    "end": round(float(s["end"]), 3),
                    "_cluster": seg_cluster[i],
                    "overlap": seg_overlap[i],
                }
            ]
    return sub_turns_out


def _diarize_neural(
    samples: np.ndarray,
    segments: list[dict[str, Any]],
    max_speakers: int,
) -> tuple[
    list[int],
    list[float | None],
    list[bool],
    list[float],
    list[float],
    list[list[dict[str, Any]]],
    np.ndarray,
    np.ndarray,
    list[float],
    list[bool],
] | None:
    """Run neural VAD + pyannote-segmentation + ECAPA-TDNN clustering.

    Returns ``None`` if Silero VAD finds zero speech so caller can fall back cleanly.
    """
    import torch
    from silero_vad import get_speech_timestamps

    vad_model, seg_sess, ecapa, device = _load_neural_models()
    n = len(segments)
    n100 = int(np.ceil(len(samples) / _SAMPLE_RATE * _FRAME_HZ))

    vad_ts = get_speech_timestamps(
        torch.from_numpy(samples),
        vad_model,
        threshold=0.28,
        sampling_rate=_SAMPLE_RATE,
        return_seconds=True,
        min_speech_duration_ms=200,
        min_silence_duration_ms=150,
    )
    vad_mask = np.zeros(n100, dtype=bool)
    for item in vad_ts:
        vad_mask[int(item["start"] * _FRAME_HZ) : min(n100, int(np.ceil(item["end"] * _FRAME_HZ)))] = True

    if int(vad_mask.sum()) == 0:
        return None

    p_ov, p_chg = _run_pyannote_segmentation(samples, seg_sess)

    # Precompute 10 Hz (100ms) RMS envelope for silence-gap and music/soundtrack detection.
    hop10 = _SAMPLE_RATE // 10
    n10 = len(samples) // hop10
    if n10 > 0:
        rms_10 = np.sqrt(np.mean(samples[: n10 * hop10].reshape(n10, hop10) ** 2, axis=1))
        vad_10 = vad_mask[: n10 * 10].reshape(n10, 10).any(axis=1)
    else:
        rms_10 = np.zeros(1, dtype=np.float32)
        vad_10 = np.zeros(1, dtype=bool)

    seg_wavs: list[np.ndarray] = []
    seg_vdur: list[float] = []
    seg_vratio: list[float] = []
    seg_pure: list[bool] = []
    seg_ov: list[bool] = []
    seg_ov_sec: list[float] = []
    seg_ov_ratio: list[float] = []
    seg_media: list[bool] = []
    seg_switch: list[bool] = []

    for s in segments:
        a, b = float(s["start"]), float(s["end"])
        dur = max(0.1, b - a)
        a0, b0 = max(0, int(a * _FRAME_HZ)), min(n100, int(b * _FRAME_HZ))
        raw_vf = int(vad_mask[a0:b0].sum()) if b0 > a0 else 0
        raw_vr = (raw_vf / _FRAME_HZ) / dur

        a_eff, b_eff = a, b
        # When a long Whisper segment (>=25s) bridges across a true acoustic silence span (>=12s)
        # before the actual spoken turn at the end (e.g. s4 223.5-431s where lobby ends in 20s of
        # silence before Jesper speaks at 425-431s), slice the active trailing speech sub-turn.
        if dur >= 25.0 and n10 > 0:
            r0, r1 = max(0, int(a * 10)), min(n10, int(b * 10))
            if r1 - r0 >= 250:
                silent_10 = (~vad_10[r0:r1]) & (rms_10[r0:r1] < 0.008)
                runs: list[tuple[int, int]] = []
                ri = 0
                while ri < len(silent_10):
                    if not silent_10[ri]:
                        ri += 1
                        continue
                    rj = ri
                    while rj < len(silent_10) and silent_10[rj]:
                        rj += 1
                    if rj - ri >= 120:  # >= 12.0s of true acoustic silence
                        runs.append((ri, rj))
                    ri = rj
                if runs:
                    last_s0, last_s1 = runs[-1]
                    tail_a = a + last_s1 / 10.0
                    tail_a0 = max(a0, int(tail_a * _FRAME_HZ))
                    tail_vd = int(vad_mask[tail_a0:b0].sum()) / _FRAME_HZ if b0 > tail_a0 else 0.0
                    tail_r0 = r0 + last_s1
                    tail_nv = ~vad_10[tail_r0:r1]
                    tail_bg = float(np.median(rms_10[tail_r0:r1][tail_nv])) if int(tail_nv.sum()) >= 2 else 0.0
                    if tail_vd >= 1.0 and (b - tail_a) <= 30.0 and tail_bg < 0.015:
                        a_eff = tail_a
                    else:
                        first_s0, first_s1 = runs[0]
                        head_b = a + first_s0 / 10.0
                        head_b0 = min(b0, int(head_b * _FRAME_HZ))
                        head_vd = int(vad_mask[a0:head_b0].sum()) / _FRAME_HZ if head_b0 > a0 else 0.0
                        post_vd = int(vad_mask[ max(a0, int((a + first_s1 / 10.0) * _FRAME_HZ)) : b0].sum()) / _FRAME_HZ
                        post_r0 = r0 + first_s1
                        post_bg = float(np.median(rms_10[post_r0:r1])) if r1 > post_r0 else 0.0
                        if head_vd >= 2.0 and (head_b - a) <= 25.0 and post_vd < 0.8 and post_bg < 0.015:
                            b_eff = head_b

        ea0, eb0 = max(0, int(a_eff * _FRAME_HZ)), min(n100, int(b_eff * _FRAME_HZ))
        eff_dur = max(0.1, b_eff - a_eff)
        if eb0 > ea0:
            ov_sec = float((p_ov[ea0:eb0] > 0.42).sum()) / _FRAME_HZ
            ov_rat = ov_sec / eff_dur
            clean_mask = vad_mask[ea0:eb0] & (p_ov[ea0:eb0] < 0.42)
            if int(clean_mask.sum()) < 25:
                clean_mask = vad_mask[ea0:eb0]
            voiced_frames = int(vad_mask[ea0:eb0].sum())
            has_switch = (float(p_chg[ea0 + 50 : eb0 - 50].max()) > 0.60) if (eb0 - ea0) > 150 else False
        else:
            ov_sec, ov_rat, voiced_frames, has_switch = 0.0, 0.0, 0, False
            clean_mask = np.zeros(0, dtype=bool)

        er0, er1 = max(0, int(a_eff * 10)), min(n10, int(b_eff * 10))
        if er1 > er0 and n10 > 0:
            sub_rms = rms_10[er0:er1]
            sub_nv = ~vad_10[er0:er1]
            bg_rms = float(np.median(sub_rms[sub_nv])) if int(sub_nv.sum()) >= 3 else 0.0
            act_frac = float((sub_rms > 0.015).mean())
        else:
            bg_rms, act_frac = 0.0, 0.0

        wav = _slice_voiced_audio(samples, a_eff, b_eff, clean_mask)[: 12 * _SAMPLE_RATE]
        vd = voiced_frames / _FRAME_HZ
        vr = vd / eff_dur
        is_media = (bg_rms >= 0.040 and act_frac >= 0.85) or (
            dur >= 25.0 and raw_vr < 0.22 and bg_rms >= 0.035
        )
        if is_media:
            is_ov = False
            ov_sec = 0.0
            ov_rat = 0.0
            pure = False
        else:
            is_ov = (ov_sec >= 0.45) or (ov_rat >= 0.12 and ov_sec >= 0.35)
            pure = (vd >= 1.6) and (vr >= 0.25 or vd >= 4.0) and (not has_switch) and (not is_ov)

        seg_wavs.append(wav)
        seg_vdur.append(vd)
        seg_vratio.append(vr)
        seg_pure.append(pure)
        seg_ov.append(is_ov)
        seg_ov_sec.append(ov_sec)
        seg_ov_ratio.append(ov_rat)
        seg_media.append(is_media)
        seg_switch.append(has_switch)

    embs = _encode_ecapa_batch(seg_wavs, ecapa, device)
    centroids = _cluster_seed_embeddings(embs, seg_vdur, seg_pure, max_speakers)
    sims = embs @ centroids.T
    seg_cluster = [int(x) for x in sims.argmax(axis=1)]
    k_count = centroids.shape[0]

    # Temporal continuity smoothing for presenter turns & tiny noise-cluster folding.
    if k_count > 1 and n >= 3:
        c_vdur: dict[int, float] = {}
        for idx, cid in enumerate(seg_cluster):
            if not seg_media[idx]:
                c_vdur[cid] = c_vdur.get(cid, 0.0) + seg_vdur[idx]

        # Pass 1: 1-segment dropout flanked by the same major speaker (>=25s voiced).
        for i in range(1, n - 1):
            if seg_media[i] or seg_switch[i]:
                continue
            prev_c, next_c = seg_cluster[i - 1], seg_cluster[i + 1]
            if prev_c == next_c and seg_cluster[i] != prev_c and c_vdur.get(prev_c, 0.0) >= 25.0:
                if float(sims[i, prev_c]) >= 0.28 or seg_vdur[i] < 1.8:
                    seg_cluster[i] = prev_c

        # Pass 2: 2-segment short dropout flanked by the same major speaker.
        for i in range(1, n - 2):
            if seg_media[i] or seg_media[i + 1] or seg_switch[i] or seg_switch[i + 1]:
                continue
            if seg_vdur[i] < 3.5 and seg_vdur[i + 1] < 3.5:
                prev_c, next_c = seg_cluster[i - 1], seg_cluster[i + 2]
                if (
                    prev_c == next_c
                    and c_vdur.get(prev_c, 0.0) >= 25.0
                    and float(sims[i, prev_c]) >= 0.28
                    and float(sims[i + 1, prev_c]) >= 0.28
                ):
                    seg_cluster[i] = prev_c
                    seg_cluster[i + 1] = prev_c

        # Pass 3: fold tiny 1-turn non-media noise clusters into nearest supported speaker.
        c_cnt: dict[int, int] = {}
        c_vdur2: dict[int, float] = {}
        for idx, cid in enumerate(seg_cluster):
            if not seg_media[idx]:
                c_cnt[cid] = c_cnt.get(cid, 0) + 1
                c_vdur2[cid] = c_vdur2.get(cid, 0.0) + seg_vdur[idx]
        keep_c = {cid for cid, d in c_vdur2.items() if c_cnt.get(cid, 0) >= 2 and d >= 8.0}
        if not keep_c:
            keep_c = {cid for cid, d in c_vdur2.items() if d >= 5.0 or c_cnt.get(cid, 0) >= 2}
        if keep_c:
            for i in range(n):
                cid = seg_cluster[i]
                if seg_media[i] or cid in keep_c:
                    continue
                adj_cands = []
                if i > 0 and seg_cluster[i - 1] in keep_c and c_vdur2.get(seg_cluster[i - 1], 0.0) >= 25.0:
                    adj_cands.append(seg_cluster[i - 1])
                if i + 1 < n and seg_cluster[i + 1] in keep_c and c_vdur2.get(seg_cluster[i + 1], 0.0) >= 25.0:
                    adj_cands.append(seg_cluster[i + 1])
                reassigned = False
                for ac in adj_cands:
                    if float(sims[i, ac]) >= 0.25 or seg_vdur[i] < 2.5:
                        seg_cluster[i] = ac
                        reassigned = True
                        break
                if not reassigned:
                    best_c = max(keep_c, key=lambda kc: float(sims[i, kc]))
                    if float(sims[i, best_c]) >= 0.26 or not adj_cands:
                        seg_cluster[i] = best_c
                    else:
                        seg_cluster[i] = adj_cands[0]

    confs: list[float | None] = []
    for i in range(n):
        if seg_vdur[i] < 0.4 or (seg_vratio[i] < 0.15 and seg_vdur[i] < 0.8):
            confs.append(None)
            continue
        row = np.sort(sims[i])[::-1]
        top1 = float(row[0])
        if top1 < 0.25:
            confs.append(None)
        elif k_count == 1:
            confs.append(round(top1, 4))
        else:
            margin = float(row[0] - row[1])
            confs.append(round(margin, 4) if margin >= 0.03 else None)

    sub_turns = _extract_sub_turns(
        samples, segments, vad_mask, p_ov, p_chg, centroids, seg_cluster, seg_ov, ecapa, device
    )
    return seg_cluster, confs, seg_ov, seg_ov_sec, seg_ov_ratio, sub_turns, p_ov, sims, seg_vdur, seg_media


# ---------------------------------------------------------------------------
# Multi-Modal Role Classification & Overlap Partner Resolution
# ---------------------------------------------------------------------------

def _playback_overlap_ratio(a: float, b: float, windows: list[tuple[float, float]]) -> float:
    dur = max(0.1, b - a)
    ov = 0.0
    for w0, w1 in windows:
        if w1 <= a:
            continue
        if w0 >= b:
            break
        ov += max(0.0, min(b, w1) - max(a, w0))
    return min(1.0, ov / dur)


def _classify_speaker_roles(
    segments: list[dict[str, Any]],
    seg_spks: list[str],
    confs: list[float | None],
    seg_ov_sec: list[float],
    seg_ov_flag: list[bool],
    playback_windows: list[tuple[float, float]],
    seg_vdur: list[float] | None = None,
    seg_media: list[bool] | None = None,
    role_overrides: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, dict[str, Any]]]:
    """Classify each speaker ID as PRESENTER, DOCUMENTARY, or UNKNOWN (no LLMs)."""
    stats: dict[str, dict[str, Any]] = {}
    total_static_dur = 0.0
    total_conf_static_dur = 0.0
    total_speech_dur = 0.0
    rec_start = min((float(s["start"]) for s in segments), default=0.0)
    rec_end = max((float(s["end"]) for s in segments), default=0.0)

    for i, s in enumerate(segments):
        sp = seg_spks[i]
        a, b = float(s["start"]), float(s["end"])
        raw_d = max(0.0, b - a)
        # Measure role cues from actual voiced speech duration when VAD is available so long
        # silence/break-spanning Whisper segments do not inflate static_seconds / static_share.
        d = min(raw_d, max(0.0, float(seg_vdur[i]))) if seg_vdur is not None else raw_d
        v_rat = _playback_overlap_ratio(a, b, playback_windows) if playback_windows else 0.0
        is_med = bool(seg_media[i]) if seg_media is not None and i < len(seg_media) else False
        st = stats.setdefault(
            sp,
            {
                "dur": 0.0,
                "raw_dur": 0.0,
                "vid_dur": 0.0,
                "static_dur": 0.0,
                "conf_static_dur": 0.0,
                "clean_static_dur": 0.0,
                "conf_static_segs": 0,
                "seg_count": 0,
                "ov_secs": 0.0,
                "ov_segs": 0,
                "static_times": [],
                "t_min": a,
                "t_max": b,
            },
        )
        st["dur"] += d
        st["raw_dur"] += raw_d
        total_speech_dur += d
        st["seg_count"] += 1
        st["t_min"] = min(st["t_min"], a)
        st["t_max"] = max(st["t_max"], b)
        st["ov_secs"] += seg_ov_sec[i]
        if seg_ov_flag[i]:
            st["ov_segs"] += 1
        if v_rat >= 0.45 or is_med:
            st["vid_dur"] += max(d, 0.25) if is_med and d < 0.25 else d
        else:
            st["static_dur"] += d
            total_static_dur += d
            if confs[i] is not None:
                st["conf_static_dur"] += d
                total_conf_static_dur += d
                if not seg_ov_flag[i]:
                    st["clean_static_dur"] += d
                st["conf_static_segs"] += 1
                st["static_times"].append((a, b))

    rec_span = max(0.1, rec_end - rec_start)
    pb_coverage = (
        _playback_overlap_ratio(rec_start, rec_end, playback_windows) if playback_windows else 0.0
    )
    # Continuous full-screen camera / podium talks lack static slide windows globally.
    is_live_camera_feed = (
        rec_span >= 30.0
        and pb_coverage >= 0.70
        and total_static_dur <= 0.15 * max(0.001, total_speech_dur)
    )

    roles: dict[str, str] = {}
    cues_by_spk: dict[str, dict[str, Any]] = {}
    share_denom = max(0.001, total_conf_static_dur if total_conf_static_dur > 0.0 else total_static_dur)
    for sp, st in stats.items():
        dur = max(0.001, st["dur"])
        vid_ratio = min(1.0, st["vid_dur"] / dur)
        static_dur = st["static_dur"]
        conf_static_dur = st["conf_static_dur"]
        clean_static_dur = st["clean_static_dur"]
        active_dur = st["vid_dur"] + conf_static_dur
        spoken_vid_ratio = (st["vid_dur"] / active_dur) if active_dur >= 2.0 else vid_ratio
        static_share = conf_static_dur / share_denom
        speech_share = st["dur"] / max(0.001, total_speech_dur)
        blocks = 0
        last_end = -1e9
        for sa, sb in sorted(st["static_times"]):
            if sa - last_end > 20.0:
                blocks += 1
            last_end = max(last_end, sb)

        dominant_speaker = speech_share >= 0.60 and st["dur"] >= 90.0 and st["seg_count"] >= 10
        if role_overrides and sp in role_overrides:
            role = role_overrides[sp]
        elif is_live_camera_feed:
            if (len(stats) == 1 and st["dur"] >= 5.0) or (
                speech_share >= 0.35 and st["dur"] >= 30.0 and st["seg_count"] >= 4
            ):
                role = "PRESENTER"
            else:
                role = "UNKNOWN"
        elif not dominant_speaker and (
            (spoken_vid_ratio >= 0.50 and blocks <= 1 and conf_static_dur < 15.0)
            or (spoken_vid_ratio >= 0.68 and conf_static_dur < 25.0 and static_share < 0.025)
        ):
            role = "DOCUMENTARY"
        elif (
            (
                blocks >= 2
                and conf_static_dur >= 15.0
                and spoken_vid_ratio < 0.60
                and static_share >= 0.025
                and (static_share >= 0.04 or clean_static_dur >= 25.0)
            )
            or (
                conf_static_dur >= 55.0
                and st["conf_static_segs"] >= 5
                and static_share >= 0.025
                and spoken_vid_ratio < 0.45
            )
            or (
                static_share >= 0.25
                and conf_static_dur >= 20.0
                and st["conf_static_segs"] >= 4
                and spoken_vid_ratio < 0.45
            )
            or dominant_speaker
        ):
            role = "PRESENTER"
        else:
            role = "UNKNOWN"

        roles[sp] = role
        cues_by_spk[sp] = {
            "static_seconds": round(static_dur, 2),
            "video_seconds": round(st["vid_dur"], 2),
            "static_blocks": blocks,
            "static_share": round(static_share, 4),
            "active_span_seconds": round(max(0.0, st["t_max"] - st["t_min"]), 2),
            "video_churn_ratio": round(vid_ratio, 4),
            "overlap_seconds": round(st["ov_secs"], 2),
            "overlap_segment_count": st["ov_segs"],
            "segment_count": st["seg_count"],
            "seconds_spoken": round(st["raw_dur"], 2),
        }
    return roles, cues_by_spk


def _resolve_overlap_speakers(
    idx: int,
    segments: list[dict[str, Any]],
    seg_spks: list[str],
    sub_turns: list[dict[str, Any]],
    cluster_to_spk: dict[int, str],
    p_ov: np.ndarray | None,
) -> list[str]:
    """Identify the distinct speaker IDs involved in an overlapped segment honestly."""
    primary = seg_spks[idx]
    a, b = float(segments[idx]["start"]), float(segments[idx]["end"])
    local_spks = {
        seg_spks[j]
        for j, s_j in enumerate(segments)
        if float(s_j["end"]) >= a - 90.0 and float(s_j["start"]) <= b + 90.0
    }
    by_dur: dict[str, float] = {}
    for st in sub_turns:
        sp = cluster_to_spk.get(st["_cluster"], primary)
        if sp != primary and sp not in local_spks:
            continue
        by_dur[sp] = by_dur.get(sp, 0.0) + max(0.0, st["end"] - st["start"])
    ranked = [sp for sp, _ in sorted(by_dur.items(), key=lambda kv: -kv[1])]
    if primary not in ranked:
        ranked.insert(0, primary)
    if len(ranked) >= 2:
        return ranked[:2]

    # Check if an adjacent turn speaker crosses into the edge of the overlapped region.
    if p_ov is not None and len(p_ov) > 0:
        a0, b0 = max(0, int(a * _FRAME_HZ)), min(len(p_ov), int(b * _FRAME_HZ))
        ov_idx = np.where(p_ov[a0:b0] > 0.42)[0]
        if len(ov_idx) > 0:
            ov_start = a + int(ov_idx[0]) / _FRAME_HZ
            ov_end = a + int(ov_idx[-1]) / _FRAME_HZ
            if idx > 0 and seg_spks[idx - 1] != primary and (ov_start - float(segments[idx - 1]["end"])) <= 1.5:
                return [primary, seg_spks[idx - 1]]
            if idx + 1 < len(segments) and seg_spks[idx + 1] != primary and (float(segments[idx + 1]["start"]) - ov_end) <= 1.5:
                return [primary, seg_spks[idx + 1]]
    return [primary]


# ---------------------------------------------------------------------------
# Public Entrypoints
# ---------------------------------------------------------------------------

def summarize_speakers(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for s in segments:
        sp = s.get("speaker")
        if not sp:
            continue
        if sp not in stats:
            stats[sp] = {"speaker": sp, "segment_count": 0, "seconds_spoken": 0.0}
            order.append(sp)
        stats[sp]["segment_count"] += 1
        stats[sp]["seconds_spoken"] += max(0.0, float(s.get("end", 0.0)) - float(s.get("start", 0.0)))
    return [
        {**stats[sp], "seconds_spoken": round(stats[sp]["seconds_spoken"], 2)}
        for sp in order
    ]


def diarize_segments(
    sr: int,
    samples: np.ndarray,
    segments: list[dict[str, Any]],
    max_speakers: int = 64,
    *,
    include_roles: bool = False,
    video_path: Path | None = None,
    playback_windows: list[tuple[float, float]] | None = None,
    return_details: bool = False,
) -> list[str] | tuple[list[str], dict[str, Any]]:
    """Assign speaker labels across segments with role-priority numbering when include_roles=True."""
    if not segments:
        return ([], {"speakers": [], "diarization": []}) if return_details else []

    seg_vdur: list[float] | None = None
    seg_media: list[bool] = [False] * len(segments)
    if len(segments) == 1:
        seg_cluster = [0]
        confs: list[float | None] = [1.0]
        seg_ov = [False]
        seg_ov_sec = [0.0]
        seg_ov_ratio = [0.0]
        sub_turns_raw = [
            [{"start": round(float(segments[0]["start"]), 3), "end": round(float(segments[0]["end"]), 3), "_cluster": 0, "overlap": False}]
        ]
        p_ov = None
    else:
        neural_res = None
        if os.environ.get("DSO_DIARIZER") != "acoustic":
            try:
                neural_res = _diarize_neural(samples, segments, max_speakers)
            except ImportError:
                neural_res = None

        if neural_res is not None:
            if len(neural_res) >= 10:
                seg_cluster, confs, seg_ov, seg_ov_sec, seg_ov_ratio, sub_turns_raw, p_ov, _, seg_vdur, seg_media = neural_res[:10]
            elif len(neural_res) == 9:
                seg_cluster, confs, seg_ov, seg_ov_sec, seg_ov_ratio, sub_turns_raw, p_ov, _, seg_vdur = neural_res
            else:
                seg_cluster, confs, seg_ov, seg_ov_sec, seg_ov_ratio, sub_turns_raw, p_ov, _ = neural_res
        else:
            seg_cluster, confs, seg_ov, seg_ov_sec, seg_ov_ratio, sub_turns_raw = _diarize_acoustic(
                sr, samples, segments, max_speakers
            )
            p_ov = None

    if not include_roles:
        remap: dict[int, str] = {}
        next_id = 1
        seg_spks: list[str] = []
        for cid in seg_cluster:
            if cid not in remap:
                remap[cid] = f"Speaker {next_id}"
                next_id += 1
            seg_spks.append(remap[cid])
        if not return_details:
            return seg_spks
        diar_rows = [
            {
                "segment_id": s.get("id", f"s{i + 1}"),
                "speaker_id": seg_spks[i],
                "speaker_category": "UNKNOWN",
                "speaker_confidence": confs[i],
                "overlap": seg_ov[i],
                "overlap_seconds": round(seg_ov_sec[i], 3),
                "overlap_ratio": round(seg_ov_ratio[i], 4),
                "overlap_speakers": _resolve_overlap_speakers(
                    i, segments, seg_spks, sub_turns_raw[i], remap, p_ov
                )
                if seg_ov[i]
                else [],
                "sub_turns": [
                    {
                        "start": st["start"],
                        "end": st["end"],
                        "speaker_id": remap.get(st["_cluster"], seg_spks[i]),
                        "role": "UNKNOWN",
                        "overlap": st["overlap"],
                    }
                    for st in sub_turns_raw[i]
                ],
            }
            for i, s in enumerate(segments)
        ]
        tmp_segs = [{**s, "speaker": sp} for s, sp in zip(segments, seg_spks)]
        return seg_spks, {"speakers": summarize_speakers(tmp_segs), "diarization": diar_rows}

    pb_wins = playback_windows if playback_windows is not None else extract_playback_windows(video_path)

    # Detach long low-VAD music/soundtrack-dominated spans (e.g. 89s brand video with 3s edge speech)
    # from presenter clusters before role classification.
    seg_cluster = list(seg_cluster)
    media_cid = max(seg_cluster, default=0) + 1
    for i, s in enumerate(segments):
        a, b = float(s["start"]), float(s["end"])
        dur = max(0.1, b - a)
        vd = seg_vdur[i] if seg_vdur is not None else dur
        if seg_media[i] and dur >= 25.0 and (vd / dur) < 0.22:
            seg_cluster[i] = media_cid
            seg_ov[i] = False
            seg_ov_sec[i] = 0.0
            seg_ov_ratio[i] = 0.0

    raw_spks = [f"_c{cid}" for cid in seg_cluster]
    raw_roles, _ = _classify_speaker_roles(
        segments, raw_spks, confs, seg_ov_sec, seg_ov, pb_wins, seg_vdur=seg_vdur, seg_media=seg_media
    )

    # Any non-presenter segment flagged as continuous music/soundtrack belongs to Documentary Audio.
    for i in range(len(segments)):
        if raw_roles.get(raw_spks[i]) in ("PRESENTER", "DOCUMENTARY"):
            continue
        if seg_media[i]:
            seg_cluster[i] = media_cid
            raw_spks[i] = f"_c{media_cid}"
            raw_roles[raw_spks[i]] = "DOCUMENTARY"

    # Role-priority speaker numbering:
    # 1. PRESENTER clusters -> Speaker 1, Speaker 2, ... in chronological order of first appearance.
    # 2. DOCUMENTARY clusters -> single canonical "Documentary Audio" speaker entry.
    # 3. UNKNOWN (audience/Q&A) clusters -> Speaker N+1, ... after presenters.
    cluster_order = list(dict.fromkeys(seg_cluster))
    remap = {}
    final_roles: dict[str, str] = {}
    next_id = 1
    for cid in cluster_order:
        if raw_roles.get(f"_c{cid}") == "PRESENTER":
            sp_name = f"Speaker {next_id}"
            next_id += 1
            remap[cid] = sp_name
            final_roles[sp_name] = "PRESENTER"
    for rk, rv in raw_roles.items():
        if rv == "DOCUMENTARY" and rk.startswith("_c"):
            remap[int(rk[2:])] = "Documentary Audio"
            final_roles["Documentary Audio"] = "DOCUMENTARY"
    for cid in cluster_order:
        if cid not in remap:
            sp_name = f"Speaker {next_id}"
            next_id += 1
            remap[cid] = sp_name
            final_roles[sp_name] = "UNKNOWN"

    seg_spks = [remap[cid] for cid in seg_cluster]
    roles, cues_by_spk = _classify_speaker_roles(
        segments,
        seg_spks,
        confs,
        seg_ov_sec,
        seg_ov,
        pb_wins,
        seg_vdur=seg_vdur,
        seg_media=seg_media,
        role_overrides=final_roles,
    )

    labels_out: list[str] = []
    diar_rows = []
    for i, s in enumerate(segments):
        sp = seg_spks[i]
        role = roles[sp]
        title = _ROLE_TITLES[role]
        ov_spks = (
            _resolve_overlap_speakers(i, segments, seg_spks, sub_turns_raw[i], remap, p_ov)
            if seg_ov[i]
            else []
        )
        if seg_ov[i]:
            if len(ov_spks) >= 2:
                label = f"{ov_spks[0]} + {ov_spks[1]} (Overlap)"
            else:
                label = f"{sp} ({title}, Overlap)"
        else:
            label = f"{sp} ({title})"
        labels_out.append(label)

        diar_rows.append(
            {
                "segment_id": s.get("id", f"s{i + 1}"),
                "speaker_id": sp,
                "speaker_category": role,
                "speaker_confidence": confs[i],
                "overlap": seg_ov[i],
                "overlap_seconds": round(seg_ov_sec[i], 3),
                "overlap_ratio": round(seg_ov_ratio[i], 4),
                "overlap_speakers": ov_spks,
                "sub_turns": [
                    {
                        "start": st["start"],
                        "end": st["end"],
                        "speaker_id": remap.get(st["_cluster"], sp),
                        "role": roles.get(remap.get(st["_cluster"], sp), "UNKNOWN"),
                        "overlap": st["overlap"],
                    }
                    for st in sub_turns_raw[i]
                ],
            }
        )

    def _spk_sort_key(sp_name: str) -> tuple[int, int, str]:
        r = roles.get(sp_name, "UNKNOWN")
        r_rank = 0 if r == "PRESENTER" else (1 if r == "UNKNOWN" else 2)
        num = int(sp_name.split()[-1]) if sp_name.startswith("Speaker ") and sp_name.split()[-1].isdigit() else 9999
        return (r_rank, num, sp_name)

    speaker_order = sorted(dict.fromkeys(seg_spks), key=_spk_sort_key)
    speakers_summary = []
    for sp in speaker_order:
        role = roles[sp]
        cues = cues_by_spk[sp]
        speakers_summary.append(
            {
                "speaker": f"{sp} ({_ROLE_TITLES[role]})",
                "speaker_id": sp,
                "role": role,
                "segment_count": cues["segment_count"],
                "seconds_spoken": cues["seconds_spoken"],
                "video_churn_ratio": cues["video_churn_ratio"],
                "overlap_seconds": cues["overlap_seconds"],
                "overlap_segment_count": cues["overlap_segment_count"],
                "role_cues": {
                    "static_seconds": cues["static_seconds"],
                    "video_seconds": cues["video_seconds"],
                    "static_blocks": cues["static_blocks"],
                    "static_share": cues["static_share"],
                    "active_span_seconds": cues["active_span_seconds"],
                },
            }
        )

    details = {"speakers": speakers_summary, "diarization": diar_rows}
    return (labels_out, details) if return_details else labels_out


def diarize_wav(
    wav_path: Path,
    segments: list[dict[str, Any]],
    max_speakers: int = 64,
    *,
    video_path: Path | None = None,
    include_roles: bool = False,
    playback_windows: list[tuple[float, float]] | None = None,
) -> dict[str, Any]:
    """Mutate segments[i]['speaker'] with detected text labels; creates no audio files."""
    if not segments:
        return {"speakers": [], "diarization": []}
    sr, samples = _read_wav_mono_16k(wav_path)
    labels, details = diarize_segments(
        sr,
        samples,
        segments,
        max_speakers=max_speakers,
        include_roles=include_roles,
        video_path=video_path,
        playback_windows=playback_windows,
        return_details=True,
    )
    for seg, lbl in zip(segments, labels):
        seg["speaker"] = lbl
    return details
