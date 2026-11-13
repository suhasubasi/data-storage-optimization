"""Whisper model choice (v1.4). No model download and no GPU: faster_whisper and the GPU count are mocked."""
import sys
import types

import pytest

from dso_pipeline import transcribe as tr

CFG = {"video": {"whisper_model": "small", "whisper_compute_type": "int8",
                 "whisper_device": "cpu", "whisper_compute_type_cuda": "int8_float16"}}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("DSO_WHISPER_MODEL", "DSO_WHISPER_DEVICE", "DSO_WHISPER_COMPUTE", "DSO_TRANSCRIBER"):
        monkeypatch.delenv(k, raising=False)


class FakeModel:
    calls = []

    def __init__(self, name, device, compute_type, download_root=None):
        FakeModel.calls.append((name, device, compute_type))

    def transcribe(self, audio, **kw):
        FakeModel.kw = kw
        return iter([types.SimpleNamespace(start=0.0, end=2.0, text=" Hi. ")]), types.SimpleNamespace(language="en")


@pytest.fixture
def fake_whisper(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", types.SimpleNamespace(WhisperModel=FakeModel))
    monkeypatch.setattr(tr, "load_wav_16k_mono", lambda wav: b"")
    FakeModel.calls = []
    return FakeModel


def test_ui_models_are_exactly_three_and_no_medium():
    assert tr.UI_MODELS == ("small", "large-v3-turbo", "large-v3")
    assert "medium" not in tr.UI_MODELS


def test_default_model_is_small():
    assert tr.select_model(CFG) == "small"
    assert tr.select_model({}) == "small"


def test_env_model_wins(monkeypatch):
    monkeypatch.setenv("DSO_WHISPER_MODEL", "large-v3-turbo")
    assert tr.select_model(CFG) == "large-v3-turbo"


def test_cpu_small_path_is_unchanged(fake_whisper, tmp_path, monkeypatch):
    monkeypatch.setattr(tr, "cuda_device_count", lambda: 1)  # a GPU exists, but the default stays CPU
    r = tr.transcribe(tmp_path / "a.wav", 10.0, CFG, lambda p: None)
    assert fake_whisper.calls == [("small", "cpu", "int8")]
    assert r.model_label == "faster-whisper small int8"
    assert (r.device, r.compute_type) == ("cpu", "int8")
    assert fake_whisper.kw == {"language": None, "beam_size": 5, "vad_filter": True, "condition_on_previous_text": False}


@pytest.mark.parametrize("model", ["large-v3-turbo", "large-v3"])
def test_settings_model_and_gpu_reach_whisper_and_the_label(fake_whisper, tmp_path, monkeypatch, model):
    # This is what the backend sets from the saved setting.
    monkeypatch.setenv("DSO_WHISPER_MODEL", model)
    monkeypatch.setenv("DSO_WHISPER_DEVICE", "cuda")
    monkeypatch.setattr(tr, "cuda_device_count", lambda: 1)
    monkeypatch.setattr(tr, "add_nvidia_dll_dirs", lambda: None)
    r = tr.transcribe(tmp_path / "a.wav", 10.0, CFG, lambda p: None)
    assert fake_whisper.calls == [(model, "cuda", "int8_float16")]
    assert r.model_label == f"faster-whisper {model} int8_float16 cuda"
    # Same Whisper settings for every model.
    assert fake_whisper.kw == {"language": None, "beam_size": 5, "vad_filter": True, "condition_on_previous_text": False}


def test_big_model_on_cpu(fake_whisper, tmp_path, monkeypatch):
    monkeypatch.setenv("DSO_WHISPER_MODEL", "large-v3-turbo")
    r = tr.transcribe(tmp_path / "a.wav", 10.0, CFG, lambda p: None)
    assert fake_whisper.calls == [("large-v3-turbo", "cpu", "int8")]
    assert r.model_label == "faster-whisper large-v3-turbo int8"


def test_word_timestamps_are_requested_for_diarization(fake_whisper, tmp_path):
    tr.transcribe(tmp_path / 'audio.wav', 2, CFG, lambda p: None, with_words=True)
    assert fake_whisper.kw['word_timestamps'] is True
