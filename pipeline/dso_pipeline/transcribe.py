"""Local speech-to-text with faster-whisper (CTranslate2, CPU, int8). No cloud / external APIs.

Model: contracts/thresholds.json video.whisper_model (default "small") + whisper_compute_type ("int8").
Overrides (env):  DSO_WHISPER_MODEL=base|small|medium|large-v3|/path/to/ct2-model
                  DSO_WHISPER_COMPUTE=int8|int8_float32|float32
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


def transcribe(wav: Path, duration: float, thresholds: dict[str, Any], on_progress: Callable[[float], None]) -> TranscriptResult:
    if os.environ.get("DSO_TRANSCRIBER", "whisper").lower() == "stub":
        return _stub(wav, duration, on_progress)

    from faster_whisper import WhisperModel  # heavy import only when really needed

    vcfg = thresholds.get("video", {})
    model_name = os.environ.get("DSO_WHISPER_MODEL") or vcfg.get("whisper_model", "small")
    compute = os.environ.get("DSO_WHISPER_COMPUTE") or vcfg.get("whisper_compute_type", "int8")
    language = os.environ.get("DSO_WHISPER_LANGUAGE") or None
    beam = int(os.environ.get("DSO_WHISPER_BEAM", "5"))
    model = WhisperModel(
        model_name,
        device="cpu",
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
    return TranscriptResult(segs, info.language, f"faster-whisper {Path(model_name).name} {compute}")
