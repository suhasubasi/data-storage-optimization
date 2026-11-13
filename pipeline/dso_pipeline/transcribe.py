"""Local speech-to-text with faster-whisper (CTranslate2, CPU, int8). No cloud / external APIs.

Model: contracts/thresholds.json video.whisper_model (default "small") + whisper_compute_type ("int8").
Overrides (env):  DSO_WHISPER_MODEL=base|small|medium|large-v3|/path/to/ct2-model
                  DSO_WHISPER_COMPUTE=int8|int8_float32|float32
                  DSO_WHISPER_LANGUAGE=en|sv|...   (default: auto-detect)
                  DSO_WHISPER_BEAM=5               (1 = fastest)
                  DSO_WHISPER_MODEL_DIR=<dir>      (where weights are cached; default HF cache ~/.cache/huggingface)
The weights are downloaded once from Hugging Face on first use, then inference is fully offline
(set HF_HUB_OFFLINE=1 to forbid any network access once cached).

Parallel chunks (OFF by default, see transcribe_parallel below):
                  DSO_TRANSCRIBE_WORKERS=4         (1 = one single pass over the whole recording, the default)
                  DSO_TRANSCRIBE_THREADS=2         (CPU threads per worker)
                  DSO_TRANSCRIBE_OVERLAP_S=30      (extra audio read on each side of a chunk)

TEST HOOK: DSO_TRANSCRIBER=stub returns fixed fake segments WITHOUT running whisper. It exists only so
unit tests can check the wiring quickly; the manifest then says model "stub (test only, not a real transcript)".
"""
from __future__ import annotations

import os
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class TranscriptResult:
    segments: list[tuple[float, float, str]]
    language: str | None
    model_label: str


def load_wav_16k_mono(wav: Path):
    """Read the 16 kHz mono s16le WAV that video.py extracts with ffmpeg into float32 [-1, 1].

    We pass a numpy array to faster-whisper instead of a path on purpose: faster-whisper 1.2.1's own
    decoder calls PyAV with an argument PyAV >= 15 removed (metadata_errors), so path input crashes.
    """
    import numpy as np

    with wave.open(str(wav), "rb") as w:
        if w.getframerate() != 16000 or w.getnchannels() != 1 or w.getsampwidth() != 2:
            raise RuntimeError("expected 16 kHz mono 16-bit WAV")
        raw = w.readframes(w.getnframes())
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def _stub(wav: Path, duration: float, on_progress: Callable[[float], None]) -> TranscriptResult:
    d = max(duration, 0.1)
    texts = ["Welcome to the stub transcript.", "As you see here, this is the second slide.", "Thank you."]
    step = d / len(texts)
    segs = [(round(i * step, 3), round((i + 1) * step, 3), t) for i, t in enumerate(texts)]
    on_progress(1.0)
    return TranscriptResult(segs, "en", "stub (test only, not a real transcript)")


def _settings(thresholds: dict[str, Any]) -> dict[str, Any]:
    vcfg = thresholds.get("video", {})
    return {
        "model_name": os.environ.get("DSO_WHISPER_MODEL") or vcfg.get("whisper_model", "small"),
        "compute": os.environ.get("DSO_WHISPER_COMPUTE") or vcfg.get("whisper_compute_type", "int8"),
        "language": os.environ.get("DSO_WHISPER_LANGUAGE") or None,
        "beam": int(os.environ.get("DSO_WHISPER_BEAM", "5")),
        "download_root": os.environ.get("DSO_WHISPER_MODEL_DIR") or None,
    }


def _model(cfg: dict[str, Any], cpu_threads: int = 0):
    from faster_whisper import WhisperModel  # heavy import only when really needed

    return WhisperModel(cfg["model_name"], device="cpu", compute_type=cfg["compute"],
                        download_root=cfg["download_root"], cpu_threads=cpu_threads)


def _run(model, audio, cfg: dict[str, Any], language: str | None):
    # The SAME decoding settings are used by the single pass and by every parallel chunk.
    return model.transcribe(
        audio,
        language=language,
        beam_size=cfg["beam"],
        vad_filter=True,  # skip silence: faster on long recordings, fewer hallucinations
        condition_on_previous_text=False,
    )


def transcribe(wav: Path, duration: float, thresholds: dict[str, Any], on_progress: Callable[[float], None]) -> TranscriptResult:
    if os.environ.get("DSO_TRANSCRIBER", "whisper").lower() == "stub":
        return _stub(wav, duration, on_progress)
    workers = int(os.environ.get("DSO_TRANSCRIBE_WORKERS", "1") or 1)
    if workers > 1:
        return transcribe_parallel(wav, duration, thresholds, on_progress, workers)

    cfg = _settings(thresholds)
    model = _model(cfg)
    seg_iter, info = _run(model, load_wav_16k_mono(wav), cfg, cfg["language"])
    segs: list[tuple[float, float, str]] = []
    for s in seg_iter:  # generator: transcription actually runs here
        text = s.text.strip()
        if text:
            segs.append((round(float(s.start), 3), round(float(s.end), 3), text))
        if duration > 0:
            on_progress(min(float(s.end) / duration, 1.0))
    on_progress(1.0)
    return TranscriptResult(segs, info.language, f"faster-whisper {Path(cfg['model_name']).name} {cfg['compute']}")


# ---------------------------------------------------------------------------------------------
# Parallel chunks (experimental, OFF unless DSO_TRANSCRIBE_WORKERS > 1).
# The original is never cut: chunks are slices of the temporary 16 kHz WAV that video.py already made.
# Each chunk is read with `overlap` seconds of extra audio on both sides; a segment is kept only by the
# chunk whose OWN zone [start, end) contains the segment's midpoint, so overlap duplicates are dropped.
# Language: detected ONCE on the whole recording (same as the single pass), then given to every chunk.
# ---------------------------------------------------------------------------------------------
SR = 16000


def plan_chunks(duration: float, n: int, overlap: float) -> list[dict[str, float]]:
    """[{own_start, own_end, read_start, read_end}] covering [0, duration) with no gaps."""
    n = max(1, int(n))
    size = duration / n
    out = []
    for i in range(n):
        a = i * size
        b = duration if i == n - 1 else (i + 1) * size
        out.append({"own_start": a, "own_end": b,
                    "read_start": max(0.0, a - overlap), "read_end": min(duration, b + overlap)})
    return out


def keep_own(chunk: dict[str, float], segs: list[tuple[float, float, str]], last: bool) -> list[tuple[float, float, str]]:
    """Segments are already in absolute time. Keep those whose midpoint is in this chunk's own zone."""
    kept = []
    for s, e, t in segs:
        mid = (s + e) / 2
        if chunk["own_start"] <= mid and (mid < chunk["own_end"] or (last and mid <= chunk["own_end"] + 1e-6)):
            kept.append((s, e, t))
    return kept


def _chunk_worker(args: tuple) -> list[tuple[float, float, str]]:
    npy, offset, cfg, language, threads = args
    import numpy as np

    audio = np.load(npy)
    model = _model(cfg, cpu_threads=threads)
    seg_iter, _ = _run(model, audio, cfg, language)
    out = []
    for s in seg_iter:
        text = s.text.strip()
        if text:
            out.append((round(float(s.start) + offset, 3), round(float(s.end) + offset, 3), text))
    return out


def detect_language(audio, cfg: dict[str, Any]) -> str | None:
    """Same detection the single pass does (VAD-filtered start of the recording), without decoding."""
    if cfg["language"]:
        return cfg["language"]
    _, info = _run(_model(cfg), audio, cfg, None)  # returns before decoding (lazy generator)
    return info.language


def transcribe_parallel(wav: Path, duration: float, thresholds: dict[str, Any], on_progress: Callable[[float], None],
                        workers: int, worker_fn: Callable[[tuple], list] | None = None) -> TranscriptResult:
    import multiprocessing
    import tempfile
    from concurrent.futures import ProcessPoolExecutor, as_completed

    import numpy as np

    cfg = _settings(thresholds)
    threads = int(os.environ.get("DSO_TRANSCRIBE_THREADS", "2") or 2)
    overlap = float(os.environ.get("DSO_TRANSCRIBE_OVERLAP_S", "30") or 30)
    audio = load_wav_16k_mono(wav)
    duration = len(audio) / SR
    language = detect_language(audio, cfg) if worker_fn is None else (cfg["language"] or "en")
    chunks = plan_chunks(duration, workers, overlap)
    results: dict[int, list] = {}
    with tempfile.TemporaryDirectory(prefix="dso-chunks-") as tmp:
        jobs = []
        for i, c in enumerate(chunks):
            npy = Path(tmp) / f"chunk{i}.npy"
            np.save(npy, audio[int(round(c["read_start"] * SR)): int(round(c["read_end"] * SR))])
            jobs.append((str(npy), c["read_start"], cfg, language, threads))
        fn = worker_fn or _chunk_worker
        # spawn (not fork): the parent may already hold a loaded CTranslate2 model and its threads.
        with ProcessPoolExecutor(max_workers=len(chunks), mp_context=multiprocessing.get_context("spawn")) as pool:
            futs = {pool.submit(fn, j): i for i, j in enumerate(jobs)}
            for done, f in enumerate(as_completed(futs), start=1):
                results[futs[f]] = f.result()
                on_progress(done / len(chunks))
    segs: list[tuple[float, float, str]] = []
    for i, c in enumerate(chunks):
        segs.extend(keep_own(c, results[i], last=i == len(chunks) - 1))
    segs.sort(key=lambda x: (x[0], x[1]))
    on_progress(1.0)
    label = f"faster-whisper {Path(cfg['model_name']).name} {cfg['compute']}, {len(chunks)} parallel chunks"
    return TranscriptResult(segs, language, label)
