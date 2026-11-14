"""Offline unit and regression tests for speaker diarization, role classification, and postpass."""
from __future__ import annotations

import json
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from dso_contracts.models import Manifest
from dso_pipeline import diarize, postpass


def _write_wav(path: Path, samples: np.ndarray, sr: int = 16000) -> None:
    clipped = np.clip(samples * 32767.0, -32768.0, 32767.0).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(clipped.tobytes())


def test_diarize_empty_and_single_segment(tmp_path):
    wav = tmp_path / "empty.wav"
    _write_wav(wav, np.zeros(16000, dtype=np.float32))
    assert diarize.diarize_wav(wav, []) == {"speakers": [], "diarization": []}

    segs = [{"id": "s1", "start": 0.0, "end": 1.0, "text": "hello", "frame_id": "f1", "speaker": None}]
    res = diarize.diarize_wav(wav, segs, include_roles=False)
    assert [s["speaker"] for s in segs] == ["Speaker 1"]
    assert res["speakers"] == [{"speaker": "Speaker 1", "segment_count": 1, "seconds_spoken": 1.0}]
    assert res["diarization"][0]["segment_id"] == "s1"
    assert res["diarization"][0]["speaker_id"] == "Speaker 1"
    assert res["diarization"][0]["overlap"] is False


def test_diarize_preserves_text_timestamps_and_creates_no_audio_files(tmp_path):
    sr = 16000
    tt = np.arange(int(sr * 3.0)) / sr
    s1 = (0.25 * np.sin(2.0 * np.pi * 110.0 * tt)).astype(np.float32)
    s2 = (0.25 * (np.sin(2.0 * np.pi * 240.0 * tt) + 0.5 * np.sin(2.0 * np.pi * 720.0 * tt))).astype(np.float32)
    wav = tmp_path / "two.wav"
    _write_wav(wav, np.concatenate([s1, s2, s1]))

    orig = [
        {"id": "s1", "start": 0.0, "end": 2.9, "text": "intro words", "frame_id": "f1", "speaker": None},
        {"id": "s2", "start": 3.0, "end": 5.9, "text": "second speaker words", "frame_id": "f2", "speaker": None},
        {"id": "s3", "start": 6.0, "end": 8.9, "text": "closing words", "frame_id": None, "speaker": None},
    ]
    segs = [dict(x) for x in orig]
    res = diarize.diarize_wav(wav, segs)

    for a, b in zip(orig, segs):
        assert b["id"] == a["id"]
        assert b["start"] == a["start"]
        assert b["end"] == a["end"]
        assert b["text"] == a["text"]
        assert b["frame_id"] == a["frame_id"]
        assert isinstance(b["speaker"], str) and b["speaker"].startswith("Speaker ")
    assert len(res["speakers"]) >= 1
    assert not (tmp_path / "audio").exists()
    assert list(tmp_path.glob("*.wav")) == [wav]


def test_diarize_role_classification_overlap_and_metadata(monkeypatch, tmp_path):
    """Verify PRESENTER / DOCUMENTARY / UNKNOWN, honest overlap detection, and sub_turns."""
    wav = tmp_path / "meeting.wav"
    _write_wav(wav, np.zeros(16000 * 140, dtype=np.float32))

    segs = [
        {"id": "s1", "start": 0.0, "end": 18.0, "text": "Presenter opening", "frame_id": "f1", "speaker": None},
        {"id": "s2", "start": 20.0, "end": 35.0, "text": "Documentary narrator", "frame_id": "f2", "speaker": None},
        {"id": "s3", "start": 35.0, "end": 42.0, "text": "Overlap handoff", "frame_id": "f2", "speaker": None},
        {"id": "s4", "start": 45.0, "end": 60.0, "text": "Presenter continues", "frame_id": "f3", "speaker": None},
        {"id": "s5", "start": 62.0, "end": 69.0, "text": "Audience question", "frame_id": "f3", "speaker": None},
        {"id": "s6", "start": 70.0, "end": 82.0, "text": "Documentary ad", "frame_id": "f4", "speaker": None},
        {"id": "s7", "start": 85.0, "end": 115.0, "text": "Mixed long segment", "frame_id": "f5", "speaker": None},
    ]

    def fake_neural(samples, segments, max_speakers):
        # 4 clusters: 0=Presenter, 1=Doc1, 2=Audience QA, 3=Ad
        seg_cluster = [0, 1, 0, 0, 2, 3, 0]
        confs = [0.62, 0.71, 0.28, 0.58, 0.44, 0.68, None]  # honest None when uncertain
        seg_ov = [False, False, True, False, False, True, False]
        seg_ov_sec = [0.0, 0.0, 1.4, 0.0, 0.0, 0.9, 0.0]
        seg_ov_ratio = [0.0, 0.0, 0.20, 0.0, 0.0, 0.075, 0.0]
        sub_turns = [
            [{"start": 0.0, "end": 18.0, "_cluster": 0, "overlap": False}],
            [{"start": 20.0, "end": 35.0, "_cluster": 1, "overlap": False}],
            [
                {"start": 35.0, "end": 38.0, "_cluster": 1, "overlap": True},
                {"start": 38.0, "end": 42.0, "_cluster": 0, "overlap": True},
            ],
            [{"start": 45.0, "end": 60.0, "_cluster": 0, "overlap": False}],
            [{"start": 62.0, "end": 69.0, "_cluster": 2, "overlap": False}],
            [{"start": 70.0, "end": 82.0, "_cluster": 3, "overlap": True}],
            [
                {"start": 85.0, "end": 92.0, "_cluster": 0, "overlap": False},
                {"start": 94.0, "end": 108.0, "_cluster": 2, "overlap": False},
                {"start": 109.0, "end": 115.0, "_cluster": 0, "overlap": False},
            ],
        ]
        p_ov = np.zeros(14000, dtype=np.float32)
        p_ov[7400:7500] = 0.85  # middle of s6, no neighbor crossing edge
        return seg_cluster, confs, seg_ov, seg_ov_sec, seg_ov_ratio, sub_turns, p_ov, np.ones((7, 4))

    monkeypatch.setattr(diarize, "_diarize_neural", fake_neural)

    playback_windows = [(19.5, 38.5), (69.5, 83.0)]
    res = diarize.diarize_wav(
        wav,
        segs,
        include_roles=True,
        playback_windows=playback_windows,
    )

    assert segs[0]["speaker"] == "Speaker 1 (Presenter)"
    assert segs[1]["speaker"] == "Documentary Audio (Documentary)"
    assert segs[2]["speaker"] == "Speaker 1 + Documentary Audio (Overlap)"
    assert segs[3]["speaker"] == "Speaker 1 (Presenter)"
    assert segs[4]["speaker"] == "Speaker 2 (Unknown)"
    # Solo speaker over ad jingle/music stays single-speaker Documentary with Overlap marker
    assert segs[5]["speaker"] == "Documentary Audio (Documentary, Overlap)"
    assert segs[6]["speaker"] == "Speaker 1 (Presenter)"

    # Verify structured transcript.json metadata
    by_id = {d["segment_id"]: d for d in res["diarization"]}
    assert by_id["s3"]["overlap"] is True
    assert by_id["s3"]["overlap_speakers"] == ["Speaker 1", "Documentary Audio"]
    assert by_id["s6"]["overlap"] is True
    assert by_id["s6"]["overlap_speakers"] == ["Documentary Audio"]
    assert by_id["s7"]["speaker_confidence"] is None
    assert [t["speaker_id"] for t in by_id["s7"]["sub_turns"]] == ["Speaker 1", "Speaker 2", "Speaker 1"]
    assert [t["role"] for t in by_id["s7"]["sub_turns"]] == ["PRESENTER", "UNKNOWN", "PRESENTER"]

    spk_roles = {sp["speaker_id"]: sp["role"] for sp in res["speakers"]}
    assert spk_roles == {
        "Speaker 1": "PRESENTER",
        "Documentary Audio": "DOCUMENTARY",
        "Speaker 2": "UNKNOWN",
    }
    assert res["speakers"][0]["overlap_seconds"] == 1.4
    assert res["speakers"][0]["role_cues"]["static_blocks"] >= 2


def test_extract_playback_windows_ignores_corner_pip_and_detects_fullscreen(monkeypatch, tmp_path):
    dummy_vid = tmp_path / "meeting.mp4"
    dummy_vid.write_bytes(b"mp4")

    # 30 seconds at 2 fps = 60 frames (160x90):
    # [0..9s] (frames 0..17): static slide
    # [9..19s] (frames 18..37): static slide + busy bottom-right corner PiP (row >=76, col >=120)
    # [19..30s] (frames 38..59): full-frame documentary playback
    frames = np.full((60, 90, 160), 220, dtype=np.uint8)
    for i in range(18, 38):
        frames[i, 76:, 120:] = (i * 53) % 255  # corner PiP flicker only
    for i in range(38, 60):
        frames[i, :76, :120] = (i * 67 + np.arange(120)[None, :]) % 255

    monkeypatch.setattr(
        diarize.subprocess,
        "run",
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=frames.tobytes(), stderr=b""),
    )

    wins = diarize.extract_playback_windows(dummy_vid)
    assert len(wins) == 1
    w0, w1 = wins[0]
    assert 17.0 <= w0 <= 21.0
    assert w1 >= 28.0


def test_postpass_run_speakers_writes_transcript_and_valid_manifest(monkeypatch, tmp_path):
    out_dir = tmp_path / "derived"
    out_dir.mkdir()
    vid = tmp_path / "video.mp4"
    vid.write_bytes(b"fake")
    audio_dir = out_dir / "audio"
    audio_dir.mkdir()
    (audio_dir / "speaker-1.wav").write_bytes(b"legacy")

    manifest = {
        "schema_version": "1.0",
        "asset_id": "a_12345678",
        "kind": "video",
        "original": {"path": "originals/a_12345678/video.mp4", "bytes": 4, "sha256": "0" * 64},
        "metadata": {
            "title": None, "author": None, "doc_number": None, "revision": None,
            "date": None, "language": "en", "duration_seconds": 60.0,
        },
        "segments": [
            {"id": "s1", "start": 0.0, "end": 30.0, "text": "Hello", "frame_id": "f1", "speaker": None},
            {"id": "s2", "start": 30.0, "end": 60.0, "text": "Video", "frame_id": "f2", "speaker": None},
        ],
        "frames": [
            {"id": "f1", "t_start": 0.0, "t_end": 30.0, "path": "frames/f1.jpg", "bytes": 10, "phash": "0" * 16, "matched_slide": None},
            {"id": "f2", "t_start": 30.0, "t_end": 60.0, "path": "frames/f2.jpg", "bytes": 10, "phash": "1" * 16, "matched_slide": None},
        ],
        "slides": [],
        "derived_files": [
            {"path": "transcript.json", "bytes": 10, "kind": "transcript"},
            {"path": "audio/speaker-1.wav", "bytes": 6, "kind": "audio"},
        ],
        "pipeline": {
            "version": "1.0", "model": "small", "frame_threshold": 6, "seconds": 1.0, "warnings": []
        },
    }
    transcript = {
        "language": "en",
        "model": "small",
        "duration_seconds": 60.0,
        "segments": manifest["segments"],
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (out_dir / "transcript.json").write_text(json.dumps(transcript), encoding="utf-8")

    def fake_run(cmd, **kw):
        wav_path = Path(cmd[-1])
        _write_wav(wav_path, np.zeros(16000, dtype=np.float32))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    def fake_diarize_wav(wav_path, segments, **kwargs):
        assert kwargs.get("include_roles") is True
        assert Path(kwargs.get("video_path")) == vid.resolve()
        segments[0]["speaker"] = "Speaker 1 (Presenter)"
        segments[1]["speaker"] = "Speaker 2 (Documentary)"
        return {
            "speakers": [
                {"speaker": "Speaker 1 (Presenter)", "speaker_id": "Speaker 1", "role": "PRESENTER", "segment_count": 1, "seconds_spoken": 30.0},
                {"speaker": "Speaker 2 (Documentary)", "speaker_id": "Speaker 2", "role": "DOCUMENTARY", "segment_count": 1, "seconds_spoken": 30.0},
            ],
            "diarization": [
                {"segment_id": "s1", "speaker_id": "Speaker 1", "speaker_category": "PRESENTER", "speaker_confidence": 0.72, "overlap": False, "overlap_seconds": 0.0, "overlap_ratio": 0.0, "overlap_speakers": [], "sub_turns": []},
                {"segment_id": "s2", "speaker_id": "Speaker 2", "speaker_category": "DOCUMENTARY", "speaker_confidence": 0.65, "overlap": False, "overlap_seconds": 0.0, "overlap_ratio": 0.0, "overlap_speakers": [], "sub_turns": []},
            ],
        }

    monkeypatch.setattr(postpass.subprocess, "run", fake_run)
    monkeypatch.setattr(postpass.diarize, "diarize_wav", fake_diarize_wav)

    summary = postpass.run_speakers("a_12345678", vid, out_dir, dry_run=False)
    assert summary["speaker_count"] == 2
    assert not audio_dir.exists()

    updated_m = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    Manifest.model_validate(updated_m)
    assert [s["speaker"] for s in updated_m["segments"]] == ["Speaker 1 (Presenter)", "Speaker 2 (Documentary)"]
    assert all(d["kind"] != "audio" for d in updated_m["derived_files"])

    updated_t = json.loads((out_dir / "transcript.json").read_text(encoding="utf-8"))
    assert len(updated_t["diarization"]) == 2
    assert updated_t["speakers"][1]["role"] == "DOCUMENTARY"


def test_role_classifier_live_camera_talk_and_tiny_overlap_fragment():
    """Live full-screen camera feeds stay PRESENTER, and tiny overlapped bursts stay UNKNOWN."""
    # Case A: continuous live-camera podium talk (playback covers 95% of recording, zero static slides)
    cam_segs = [{"id": f"s{i+1}", "start": float(i * 10), "end": float((i + 1) * 10 - 0.5)} for i in range(6)]
    cam_spks = ["Speaker 1"] * 5 + ["Speaker 2"]
    roles_cam, _ = diarize._classify_speaker_roles(
        cam_segs,
        cam_spks,
        [0.65] * 6,
        [0.0] * 6,
        [False] * 6,
        [(1.0, 58.0)],
    )
    assert roles_cam == {"Speaker 1": "PRESENTER", "Speaker 2": "UNKNOWN"}

    # Case B: dominant static speaker + tiny (<2% share) overlapped glitch across a 25s pause
    mix_segs = [
        {"id": f"m{i+1}", "start": float(i * 50), "end": float(i * 50 + 45)} for i in range(12)
    ] + [
        {"id": "x1", "start": 620.0, "end": 628.0},
        {"id": "x2", "start": 660.0, "end": 668.0},
    ]
    mix_spks = ["Speaker 1"] * 12 + ["Speaker 2", "Speaker 2"]
    mix_ov = [False] * 12 + [True, False]
    roles_mix, _ = diarize._classify_speaker_roles(
        mix_segs,
        mix_spks,
        [0.70] * 14,
        [0.0] * 12 + [2.0, 0.0],
        mix_ov,
        [],
    )
    assert roles_mix["Speaker 1"] == "PRESENTER"
    assert roles_mix["Speaker 2"] == "UNKNOWN"


def test_pyannote_segmentation_dense_100hz_interpolation_has_no_holes():
    """58.9 Hz powerset outputs must interpolate onto 100 Hz with zero sparse holes."""
    class FakeSess:
        def get_inputs(self):
            return [SimpleNamespace(name="input")]

        def run(self, _outputs, feed):
            bs = feed["input"].shape[0]
            logp = np.full((bs, 589, 7), -20.0, dtype=np.float32)
            logp[:, :, 4] = 0.0  # continuous 2-speaker overlap class across every 589-frame window
            return [logp]

    samples = np.zeros(20 * 16000, dtype=np.float32)
    p_ov, p_chg = diarize._run_pyannote_segmentation(samples, FakeSess())
    assert len(p_ov) == 2000
    assert len(p_chg) == 2000
    assert float(p_ov.min()) > 0.99
    assert int((p_ov == 0.0).sum()) == 0


def test_role_classifier_break_spanning_segments_do_not_promote_stray_chatter():
    """Long break/silence Whisper spans with short voiced speech stay UNKNOWN, not PRESENTER."""
    segs = [
        {"id": f"p{i+1}", "start": float(i * 40), "end": float(i * 40 + 35)} for i in range(10)
    ] + [
        {"id": "b1", "start": 500.0, "end": 643.0},  # 143s silent break span, only 2s murmured speech
        {"id": "b2", "start": 665.0, "end": 717.0},  # 52s break span, only 1s speech + low confidence
    ]
    spks = ["Speaker 1"] * 10 + ["Speaker 2", "Speaker 2"]
    confs = [0.75] * 10 + [0.40, None]
    vdur = [30.0] * 10 + [2.0, 1.0]
    roles, cues = diarize._classify_speaker_roles(
        segs,
        spks,
        confs,
        [0.0] * 12,
        [False] * 12,
        [],
        seg_vdur=vdur,
    )
    assert roles["Speaker 1"] == "PRESENTER"
    assert roles["Speaker 2"] == "UNKNOWN"
    assert cues["Speaker 2"]["static_seconds"] == 3.0
    assert cues["Speaker 2"]["static_share"] < 0.01


def test_role_priority_numbering_keeps_presenters_1_to_n_before_documentary_and_unknown(monkeypatch, tmp_path):
    """Lobby music / documentary clips must not steal Speaker 1..N from live presenters."""
    wav = tmp_path / "multi_presenter.wav"
    _write_wav(wav, np.zeros(16000 * 300, dtype=np.float32))

    segs = [
        {"id": "s1", "start": 0.0, "end": 30.0, "text": "Lobby music", "frame_id": "f1", "speaker": None},
        {"id": "s2", "start": 35.0, "end": 55.0, "text": "Presenter 1 intro", "frame_id": "f2", "speaker": None},
        {"id": "s3", "start": 80.0, "end": 100.0, "text": "Presenter 1 part 2", "frame_id": "f2", "speaker": None},
        {"id": "s4", "start": 105.0, "end": 135.0, "text": "Embedded documentary", "frame_id": "f3", "speaker": None},
        {"id": "s5", "start": 140.0, "end": 148.0, "text": "Audience question", "frame_id": "f4", "speaker": None},
        {"id": "s6", "start": 150.0, "end": 175.0, "text": "Presenter 2 part 1", "frame_id": "f4", "speaker": None},
        {"id": "s7", "start": 200.0, "end": 225.0, "text": "Presenter 2 part 2", "frame_id": "f5", "speaker": None},
    ]

    def fake_neural(samples, segments, max_speakers):
        # Cluster 0 = lobby music, 1 = Presenter 1, 2 = documentary voice, 3 = audience Q&A, 4 = Presenter 2
        seg_cluster = [0, 1, 1, 2, 3, 4, 4]
        confs = [0.60, 0.75, 0.78, 0.70, 0.55, 0.80, 0.82]
        seg_ov = [False] * 7
        seg_ov_sec = [0.0] * 7
        seg_ov_ratio = [0.0] * 7
        sub_turns = [[{"start": s["start"], "end": s["end"], "_cluster": seg_cluster[i], "overlap": False}] for i, s in enumerate(segments)]
        p_ov = np.zeros(30000, dtype=np.float32)
        seg_vdur = [15.0, 18.0, 18.0, 22.0, 6.0, 22.0, 22.0]
        seg_media = [True, False, False, False, False, False, False]
        return seg_cluster, confs, seg_ov, seg_ov_sec, seg_ov_ratio, sub_turns, p_ov, np.ones((7, 5)), seg_vdur, seg_media

    monkeypatch.setattr(diarize, "_diarize_neural", fake_neural)
    res = diarize.diarize_wav(
        wav,
        segs,
        include_roles=True,
        playback_windows=[(104.0, 136.0)],
    )

    assert [s["speaker"] for s in segs] == [
        "Documentary Audio (Documentary)",
        "Speaker 1 (Presenter)",
        "Speaker 1 (Presenter)",
        "Documentary Audio (Documentary)",
        "Speaker 3 (Unknown)",
        "Speaker 2 (Presenter)",
        "Speaker 2 (Presenter)",
    ]
    assert [sp["speaker_id"] for sp in res["speakers"]] == [
        "Speaker 1",
        "Speaker 2",
        "Speaker 3",
        "Documentary Audio",
    ]


def test_transcribe_passes_vad_parameters_when_supported(monkeypatch, tmp_path):
    """transcribe() passes vad_parameters when WhisperModel.transcribe accepts it."""
    import sys
    import types
    from dso_pipeline import transcribe as tr

    captured = {}

    class ModernWhisperModel:
        def __init__(self, name, device, compute_type, download_root=None):
            pass

        def transcribe(
            self,
            audio,
            language=None,
            beam_size=5,
            vad_filter=False,
            vad_parameters=None,
            condition_on_previous_text=True,
        ):
            captured["vad_parameters"] = vad_parameters
            seg = types.SimpleNamespace(start=0.0, end=2.0, text=" Hello ")
            return iter([seg]), types.SimpleNamespace(language="en")

    monkeypatch.delenv("DSO_TRANSCRIBER", raising=False)
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=ModernWhisperModel))
    monkeypatch.setattr(tr, "load_wav_16k_mono", lambda wav: b"")
    tr.transcribe(tmp_path / "a.wav", 5.0, {}, lambda p: None)
    assert captured["vad_parameters"] == {"min_silence_duration_ms": 500, "max_speech_duration_s": 25}



