import json
import os
import shutil
import subprocess
import sys
import time

import pytest

from conftest import fingerprint, place_original
from helpers import check_manifest
from dso_pipeline.video import frame_for

needs_ffmpeg = pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")


def run_cli(asset_id, inp, out, **env):
    e = {**os.environ, **env}
    return subprocess.run([sys.executable, "-m", "dso_pipeline", "process", "--asset-id", asset_id, "--kind", "video",
                           "--input", str(inp), "--out", str(out)], capture_output=True, text=True, env=e)


def test_frame_for_rule():
    frames = [{"id": "f1", "t_start": 0, "t_end": 5}, {"id": "f2", "t_start": 5, "t_end": 11}]
    assert frame_for(0, frames) == "f1"
    assert frame_for(4.99, frames) == "f1"
    assert frame_for(5, frames) == "f2"  # [t_start, t_end)
    assert frame_for(11, frames) == "f2"  # at/after end -> last frame
    assert frame_for(1, []) is None


def _check_video_manifest(m, out):
    assert m["kind"] == "video" and m["slides"] == []
    assert [f["id"] for f in m["frames"]] == ["f1", "f2", "f3", "f4"]  # 4 slides in the sample => 4 key frames
    for a, b in zip(m["frames"], m["frames"][1:]):
        assert a["t_end"] == b["t_start"]
    assert m["frames"][0]["t_start"] == 0
    assert abs(m["frames"][-1]["t_end"] - m["metadata"]["duration_seconds"]) < 0.01
    for s in m["segments"]:
        f = next(f for f in m["frames"] if f["id"] == s["frame_id"])
        assert f["t_start"] <= s["start"] < f["t_end"] or f is m["frames"][-1]
        assert s["speaker"] is None
    t = json.loads((out / "transcript.json").read_text())
    assert t["segments"] == m["segments"]
    assert m["pipeline"]["frame_threshold"] == 12


@needs_ffmpeg
def test_video_with_stub_transcriber(samples, data_dir):
    """Wiring test. DSO_TRANSCRIBER=stub = fake transcript (TEST ONLY), real ffmpeg key frames."""
    orig = place_original(data_dir, "a_v1", samples / "talk.mp4")
    before = fingerprint(orig)
    out = data_dir / "derived" / "a_v1"
    p = run_cli("a_v1", orig, out, DSO_TRANSCRIBER="stub")
    assert p.returncode == 0, p.stderr
    m = check_manifest(out)
    assert fingerprint(orig) == before
    assert m["pipeline"]["model"].startswith("stub")
    assert len(m["segments"]) == 3
    _check_video_manifest(m, out)


def _whisper_cached(name="small"):
    try:
        from huggingface_hub import try_to_load_from_cache
        return isinstance(try_to_load_from_cache(f"Systran/faster-whisper-{name}", "model.bin"), str)
    except Exception:
        return False


@needs_ffmpeg
@pytest.mark.skipif(not (_whisper_cached() or os.environ.get("DSO_RUN_WHISPER") == "1"),
                    reason="faster-whisper 'small' not cached; set DSO_RUN_WHISPER=1 to download and run")
def test_video_real_local_whisper(samples, data_dir):
    """REAL local faster-whisper run on the ~22 s synthetic talk (about 4 s on 8 CPU cores)."""
    orig = place_original(data_dir, "a_v2", samples / "talk.mp4")
    before = fingerprint(orig)
    out = data_dir / "derived" / "a_v2"
    t0 = time.monotonic()
    p = run_cli("a_v2", orig, out, HF_HUB_OFFLINE="1")
    took = time.monotonic() - t0
    assert p.returncode == 0, p.stderr
    m = check_manifest(out)
    assert fingerprint(orig) == before
    assert m["pipeline"]["model"] == "faster-whisper small int8"
    assert m["metadata"]["language"] == "en"
    _check_video_manifest(m, out)
    see_here = [s for s in m["segments"] if "see here" in s["text"].lower()]
    assert see_here, [s["text"] for s in m["segments"]]
    assert see_here[0]["frame_id"] == "f2"  # "as you see here" -> the handover slide
    print(f"real whisper run: {took:.1f}s for {m['metadata']['duration_seconds']}s of video")


@needs_ffmpeg
def test_noisy_static_slide_gives_one_frame_and_no_audio_is_ok(data_dir, tmp_path):
    """General keyframe mode tolerates compression noise and videos without audio.

    Slide-content filtering is tested separately in test_slide_content.py.
    """
    import pymupdf
    from synthetic_samples import make_deck, SLIDES_A
    from dso_pipeline.common import load_thresholds

    # A silent-video test needs only the deck, not the speech/video fixture.
    deck = tmp_path / "deck.pdf"
    make_deck(deck, SLIDES_A, "Rev A")
    png = tmp_path / "s.png"
    with pymupdf.open(deck) as d:
        d[1].get_pixmap(matrix=pymupdf.Matrix(1.333, 1.333)).save(png)
    src = tmp_path / "noisy.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-loop", "1", "-framerate", "25", "-i", str(png), "-t", "6",
                    "-vf", "noise=alls=25:allf=t,format=yuv420p", "-c:v", "libx264", "-crf", "30", str(src)], check=True)
    orig = place_original(data_dir, "a_v3", src)
    out = data_dir / "derived" / "a_v3"
    # Isolate keyframe change detection from the independent text-slide gate.
    # The temporary configuration leaves application defaults unchanged.
    thresholds = load_thresholds()
    thresholds["video"]["slides_only"] = False
    config = tmp_path / "thresholds.json"
    config.write_text(json.dumps(thresholds), encoding="utf-8")
    p = run_cli("a_v3", orig, out, DSO_TRANSCRIBER="stub", DSO_THRESHOLDS=str(config))
    assert p.returncode == 0, p.stderr
    m = check_manifest(out)
    assert len(m["frames"]) == 1 and m["segments"] == []
    assert m["metadata"]["language"] is None and m["pipeline"]["model"] is None
    assert any("no audio" in w for w in m["pipeline"]["warnings"])
