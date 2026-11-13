"""Whisper device choice. No GPU and no model needed: the CUDA device count is mocked."""
import sys
import types

import pytest

from dso_pipeline import transcribe as tr

CFG = {"video": {"whisper_model": "small", "whisper_compute_type": "int8",
                 "whisper_device": "cpu", "whisper_compute_type_cuda": "int8_float16"}}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("DSO_WHISPER_DEVICE", "DSO_WHISPER_COMPUTE"):
        monkeypatch.delenv(k, raising=False)


def cfg(**video):
    return {"video": {**CFG["video"], **video}}


def test_default_is_cpu_int8_even_with_a_gpu():
    assert tr.select_device(CFG, lambda: 1) == ("cpu", "int8")


def test_missing_settings_fall_back_to_cpu_int8():
    assert tr.select_device({}, lambda: 1) == ("cpu", "int8")


def test_auto_uses_gpu_when_there_is_one():
    assert tr.select_device(cfg(whisper_device="auto"), lambda: 1) == ("cuda", "int8_float16")


def test_auto_without_gpu_is_the_unchanged_cpu_path():
    assert tr.select_device(cfg(whisper_device="auto"), lambda: 0) == ("cpu", "int8")


def test_cuda_without_gpu_fails_clearly():
    with pytest.raises(RuntimeError, match="no NVIDIA GPU"):
        tr.select_device(cfg(whisper_device="cuda"), lambda: 0)


def test_env_overrides(monkeypatch):
    monkeypatch.setenv("DSO_WHISPER_DEVICE", "cuda")
    monkeypatch.setenv("DSO_WHISPER_COMPUTE", "float16")
    assert tr.select_device(CFG, lambda: 2) == ("cuda", "float16")


def test_bad_device_is_rejected(monkeypatch):
    monkeypatch.setenv("DSO_WHISPER_DEVICE", "tpu")
    with pytest.raises(ValueError):
        tr.select_device(CFG, lambda: 1)


def test_cuda_device_count_reads_ctranslate2(monkeypatch):
    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_cuda_device_count=lambda: 3))
    assert tr.cuda_device_count() == 3

    def boom():
        raise RuntimeError("no CUDA driver")
    monkeypatch.setitem(sys.modules, "ctranslate2", types.SimpleNamespace(get_cuda_device_count=boom))
    assert tr.cuda_device_count() == 0


class FakeModel:
    calls = []

    def __init__(self, name, device, compute_type, download_root=None):
        FakeModel.calls.append((name, device, compute_type))

    def transcribe(self, audio, **kw):
        FakeModel.kw = kw
        seg = types.SimpleNamespace(start=0.0, end=1.5, text=" Hello. ")
        return iter([seg]), types.SimpleNamespace(language="en")


@pytest.mark.parametrize("device_cfg,count,want_dev,want_label", [
    ("cpu", 1, "cpu", "faster-whisper small int8"),          # CPU label is exactly as before
    ("auto", 0, "cpu", "faster-whisper small int8"),
    ("auto", 1, "cuda", "faster-whisper small int8_float16 cuda"),
])
def test_transcribe_passes_device_and_labels_it(monkeypatch, tmp_path, device_cfg, count, want_dev, want_label):
    monkeypatch.delenv("DSO_TRANSCRIBER", raising=False)
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setattr(tr, "cuda_device_count", lambda: count)
    monkeypatch.setattr(tr, "load_wav_16k_mono", lambda wav: b"")
    FakeModel.calls = []
    r = tr.transcribe(tmp_path / "a.wav", 10.0, cfg(whisper_device=device_cfg), lambda p: None)
    assert FakeModel.calls[0][1] == want_dev
    assert r.device == want_dev and r.model_label == want_label
    assert r.segments == [(0.0, 1.5, "Hello.")]
    # Same Whisper settings on every device.
    assert FakeModel.kw == {"language": None, "beam_size": 5, "vad_filter": True, "condition_on_previous_text": False}
