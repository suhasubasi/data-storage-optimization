"""Real progress reporting: progress.json fields, and Whisper output is unchanged by progress reporting.

faster-whisper is replaced by a small fake module here (synthetic segments, test only), so the test
runs in CI without model weights. It checks that our transcribe() wrapper returns exactly the same
transcript whether progress is recorded or not, and that progress = segment end / duration.
"""
import json
import sys
import types

import pytest

from dso_pipeline import transcribe as tr
from dso_pipeline.common import Status


def test_status_writes_stage_progress_only_when_measured(tmp_path):
    s = Status(tmp_path)
    s.progress("probing", 0.0)
    assert json.loads((tmp_path / "progress.json").read_text()) == {"stage": "probing", "progress": 0.0}
    s.progress("transcribing", 0.35 + 0.6 * 0.5, stage_progress=0.5)
    assert json.loads((tmp_path / "progress.json").read_text()) == {
        "stage": "transcribing", "progress": 0.65, "stage_progress": 0.5}
    s.progress("transcribing", 2.0, stage_progress=7.0)  # clamped, never above 100%
    assert json.loads((tmp_path / "progress.json").read_text()) == {
        "stage": "transcribing", "progress": 1.0, "stage_progress": 1.0}


class _Seg:
    def __init__(self, start, end, text):
        self.start, self.end, self.text = start, end, text


FAKE_SEGMENTS = [(0.0, 4.2, " Hello and welcome."), (4.2, 9.9, " "), (12.0, 30.5, " Second part."),
                 (31.0, 58.25, " Thank you.")]
DURATION = 60.0


@pytest.fixture
def fake_whisper(monkeypatch, tmp_path):
    calls = []

    class WhisperModel:
        def __init__(self, name, **kw):
            calls.append(("init", name, kw))

        def transcribe(self, audio, **kw):
            calls.append(("transcribe", kw))
            return (_Seg(*s) for s in FAKE_SEGMENTS), types.SimpleNamespace(language="en")

    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=WhisperModel))
    monkeypatch.setattr(tr, "load_wav_16k_mono", lambda wav: [0.0])
    monkeypatch.delenv("DSO_TRANSCRIBER", raising=False)
    for k in ("DSO_WHISPER_MODEL", "DSO_WHISPER_COMPUTE", "DSO_WHISPER_LANGUAGE", "DSO_WHISPER_BEAM"):
        monkeypatch.delenv(k, raising=False)
    return calls


def test_transcript_identical_with_and_without_progress(fake_whisper, tmp_path):
    th = {"video": {"whisper_model": "small", "whisper_compute_type": "int8"}}
    seen = []
    a = tr.transcribe(tmp_path / "a.wav", DURATION, th, lambda p: None)
    b = tr.transcribe(tmp_path / "a.wav", DURATION, th, seen.append)
    assert a == b  # same segments, language and model label
    assert a.segments == [(0.0, 4.2, "Hello and welcome."), (12.0, 30.5, "Second part."), (31.0, 58.25, "Thank you.")]
    # Progress is real: end of each finished segment / duration, never decreasing, then 1.0 at the end.
    assert seen == [pytest.approx(x) for x in (4.2 / 60, 9.9 / 60, 30.5 / 60, 58.25 / 60, 1.0)]
    assert seen == sorted(seen)
    # Whisper settings are unchanged (same model, compute type, beam, VAD, no previous-text conditioning).
    inits = [c for c in fake_whisper if c[0] == "init"]
    runs = [c[1] for c in fake_whisper if c[0] == "transcribe"]
    assert all(c[1] == "small" and c[2]["compute_type"] == "int8" and c[2]["device"] == "cpu" for c in inits)
    assert runs[0] == runs[1] == {"language": None, "beam_size": 5, "vad_filter": True,
                                  "condition_on_previous_text": False}


def test_video_progress_json_has_stage_progress(samples, data_dir, monkeypatch):
    """End to end on a synthetic test video (stub transcriber): the run ends at done/100%."""
    import shutil
    if not shutil.which("ffmpeg"):
        pytest.skip("ffmpeg not installed")
    from conftest import place_original
    from dso_pipeline import video

    monkeypatch.setenv("DSO_TRANSCRIBER", "stub")
    writes = []
    real = Status.progress

    def spy(self, stage, progress, stage_progress=None):
        writes.append((stage, progress, stage_progress))
        return real(self, stage, progress, stage_progress)

    monkeypatch.setattr(Status, "progress", spy)
    orig = place_original(data_dir, "a_p1", samples / "talk.mp4")
    out = data_dir / "derived" / "a_p1"
    out.mkdir(parents=True)
    from dso_pipeline.common import load_thresholds
    video.process_video(orig, out, load_thresholds(), Status(out))
    stages = [w[0] for w in writes]
    assert "extracting key frames" in stages and "transcribing" in stages
    overall = [w[1] for w in writes]
    assert overall == sorted(overall)  # whole-job percent never goes backwards
    tp = [w[2] for w in writes if w[0] == "transcribing" and w[2] is not None]
    assert tp and tp[-1] == 1.0
    kf = [w[2] for w in writes if w[0] == "extracting key frames" and w[2] is not None]
    assert all(0.0 <= x <= 1.0 for x in kf)
