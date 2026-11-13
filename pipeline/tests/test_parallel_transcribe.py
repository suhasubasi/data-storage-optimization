"""Parallel chunked transcription: chunk plan + stitching. Uses a synthetic silent WAV and a fake worker
(test-only; no model, no real audio)."""
import wave

import numpy as np

from dso_pipeline import transcribe as T

# Fake "spoken" sentences on an absolute timeline (seconds), only for the stitching test.
TRUTH = [(i * 7.0, i * 7.0 + 5.0, f"sentence {i}") for i in range(17)]  # 0..117 s


def fake_worker(args):
    """Return every TRUTH sentence that lies fully inside the audio this chunk read (absolute times)."""
    npy, offset, cfg, language, threads = args
    n = len(np.load(npy)) / T.SR
    return [(s, e, t) for s, e, t in TRUTH if s >= offset and e <= offset + n]


def write_silence(path, seconds):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(np.zeros(int(seconds * 16000), dtype=np.int16).tobytes())


def test_plan_chunks_cover_everything():
    c = T.plan_chunks(100.0, 4, 30.0)
    assert [x["own_start"] for x in c] == [0.0, 25.0, 50.0, 75.0] and c[-1]["own_end"] == 100.0
    assert c[0]["read_start"] == 0.0 and c[1]["read_start"] == 0.0 and c[2]["read_start"] == 20.0
    assert c[-1]["read_end"] == 100.0 and c[0]["read_end"] == 55.0
    assert T.plan_chunks(10.0, 1, 30.0) == [{"own_start": 0.0, "own_end": 10.0, "read_start": 0.0, "read_end": 10.0}]


def test_keep_own_uses_midpoint():
    c = {"own_start": 10.0, "own_end": 20.0}
    segs = [(8.0, 11.0, "a"), (9.0, 13.0, "b"), (19.0, 22.0, "c"), (18.0, 21.0, "d")]
    assert [t for *_, t in T.keep_own(c, segs, last=False)] == ["b", "d"]  # mids 9.5 / 11 / 20.5 / 19.5


def test_parallel_stitch_no_duplicates_no_gaps(tmp_path, monkeypatch):
    monkeypatch.setenv("DSO_TRANSCRIBE_OVERLAP_S", "10")
    wav = tmp_path / "a.wav"
    write_silence(wav, 120.0)
    seen = []
    r = T.transcribe_parallel(wav, 120.0, {"video": {}}, seen.append, workers=4, worker_fn=fake_worker)
    assert r.segments == TRUTH  # every sentence exactly once, in order
    assert seen[-1] == 1.0 and "4 parallel chunks" in r.model_label


def test_single_pass_is_default(monkeypatch):
    monkeypatch.delenv("DSO_TRANSCRIBE_WORKERS", raising=False)
    called = {}
    monkeypatch.setattr(T, "transcribe_parallel", lambda *a, **k: called.setdefault("parallel", True))
    monkeypatch.setenv("DSO_TRANSCRIBER", "stub")
    T.transcribe(None, 3.0, {}, lambda p: None)
    assert "parallel" not in called
