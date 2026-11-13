"""Local speech-to-text with faster-whisper (CTranslate2). No cloud / external APIs.

Model: contracts/thresholds.json video.whisper_model (default "small") + whisper_compute_type ("int8").
Device: video.whisper_device = cpu (default) | cuda | auto. auto = NVIDIA GPU if CTranslate2 sees one,
        else CPU. On the GPU the compute type is video.whisper_compute_type_cuda ("int8_float16").
        The CPU path (cpu + int8) is exactly what it was before; GPU text is close but NOT identical.
Model choice (v1.4): the app's Settings page saves small | large-v3-turbo | large-v3 and the backend passes it
        as DSO_WHISPER_MODEL / DSO_WHISPER_DEVICE. With no setting saved, nothing changes (small on CPU).
Overrides (env):  DSO_WHISPER_MODEL=small|large-v3-turbo|large-v3|/path/to/ct2-model (any faster-whisper name works)
                  DSO_WHISPER_DEVICE=cpu|cuda|auto
                  DSO_WHISPER_COMPUTE=int8|int8_float32|float32 (CPU) or int8_float16|float16 (GPU)
                  DSO_WHISPER_LANGUAGE=en|sv|...   (default: auto-detect)
                  DSO_WHISPER_BEAM=5               (1 = fastest)
                  DSO_WHISPER_MODEL_DIR=<dir>      (where weights are cached; default HF cache ~/.cache/huggingface)
The weights are downloaded once from Hugging Face on first use, then inference is fully offline
(set HF_HUB_OFFLINE=1 to forbid any network access once cached).

TEST HOOK: DSO_TRANSCRIBER=stub returns fixed fake segments WITHOUT running whisper. It exists only so
unit tests can check the wiring quickly; the manifest then says model "stub (test only, not a real transcript)".
"""
from __future__ import annotations

import os
import sys
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass
class TranscriptResult:
    segments: list[tuple[float, float, str]]
    language: str | None
    model_label: str
    device: str = "cpu"
    compute_type: str = "int8"


DEVICES = ("cpu", "cuda", "auto")
# The models the UI offers (v1.4). 'medium' is deliberately left out. The env var may still name any
# faster-whisper model or a local CTranslate2 folder (advanced use).
UI_MODELS = ("small", "large-v3-turbo", "large-v3")


def select_model(thresholds: dict[str, Any]) -> str:
    """Model name: env DSO_WHISPER_MODEL, else thresholds video.whisper_model, else 'small'."""
    name = (os.environ.get("DSO_WHISPER_MODEL") or thresholds.get("video", {}).get("whisper_model") or "small").strip()
    if not name:
        raise ValueError("whisper model name is empty")
    return name


def cuda_device_count() -> int:
    """Number of NVIDIA GPUs CTranslate2 can use (0 if none, or if CTranslate2 has no CUDA support)."""
    try:
        import ctranslate2

        return int(ctranslate2.get_cuda_device_count())
    except Exception:
        return 0


def select_device(thresholds: dict[str, Any], cuda_count: Callable[[], int] | None = None) -> tuple[str, str]:
    """Pick (device, compute_type). Default is cpu + int8, the same as before GPU support existed."""
    cuda_count = cuda_count or cuda_device_count
    vcfg = thresholds.get("video", {})
    want = (os.environ.get("DSO_WHISPER_DEVICE") or vcfg.get("whisper_device") or "cpu").strip().lower()
    if want not in DEVICES:
        raise ValueError(f"whisper device must be one of {DEVICES}, got {want!r}")
    if want == "auto":
        device = "cuda" if cuda_count() > 0 else "cpu"
    elif want == "cuda":
        if cuda_count() <= 0:
            raise RuntimeError("whisper device 'cuda' was asked for, but no NVIDIA GPU is usable "
                               "(see pipeline/README.md, GPU setup)")
        device = "cuda"
    else:
        device = "cpu"
    if device == "cuda":
        default = vcfg.get("whisper_compute_type_cuda", "int8_float16")
    else:
        default = vcfg.get("whisper_compute_type", "int8")
    return device, os.environ.get("DSO_WHISPER_COMPUTE") or default


def add_nvidia_dll_dirs() -> None:
    """Windows only: make the cuBLAS/cuDNN DLLs from pip packages (nvidia-cublas-cu12, ...) findable."""
    if sys.platform != "win32":
        return
    for base in map(Path, sys.path):
        nv = base / "nvidia"
        if not nv.is_dir():
            continue
        for bin_dir in nv.glob("*/bin"):
            try:
                os.add_dll_directory(str(bin_dir))
            except OSError:
                continue
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


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


def transcribe(wav: Path, duration: float, thresholds: dict[str, Any], on_progress: Callable[[float], None]) -> TranscriptResult:
    if os.environ.get("DSO_TRANSCRIBER", "whisper").lower() == "stub":
        return _stub(wav, duration, on_progress)

    from faster_whisper import WhisperModel  # heavy import only when really needed

    model_name = select_model(thresholds)
    device, compute = select_device(thresholds)
    if device == "cuda":
        add_nvidia_dll_dirs()
    language = os.environ.get("DSO_WHISPER_LANGUAGE") or None
    beam = int(os.environ.get("DSO_WHISPER_BEAM", "5"))
    model = WhisperModel(
        model_name,
        device=device,
        compute_type=compute,
        download_root=os.environ.get("DSO_WHISPER_MODEL_DIR") or None,
    )
    seg_iter, info = model.transcribe(
        load_wav_16k_mono(wav),
        language=language,
        beam_size=beam,
        vad_filter=True,  # skip silence: faster on long recordings, fewer hallucinations
        condition_on_previous_text=False,
    )
    segs: list[tuple[float, float, str]] = []
    for s in seg_iter:  # generator: transcription actually runs here
        text = s.text.strip()
        if text:
            segs.append((round(float(s.start), 3), round(float(s.end), 3), text))
        if duration > 0:
            on_progress(min(float(s.end) / duration, 1.0))
    on_progress(1.0)
    # The label goes into transcript.json and the manifest, so every result says how it was made.
    label = f"faster-whisper {Path(model_name).name} {compute}" + (" cuda" if device == "cuda" else "")
    return TranscriptResult(segs, info.language, label, device, compute)
