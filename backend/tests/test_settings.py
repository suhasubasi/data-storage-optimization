"""REC v1.4: Whisper model + device setting. No model, no GPU: the HF cache is a temp dir, the GPU probe is mocked."""
import json

import pytest

from app import whisper_settings as ws
from dso_contracts.models import Settings


@pytest.fixture
def env(monkeypatch, tmp_path):
    cache = tmp_path / "hf"
    monkeypatch.setenv("DSO_WHISPER_MODEL_DIR", str(cache))
    monkeypatch.setenv("HF_HUB_CACHE", str(cache))
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.setattr(ws.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setenv("DSO_SETTINGS_PATH", str(tmp_path / "settings.json"))
    for k in ("DSO_WHISPER_MODEL", "DSO_WHISPER_DEVICE"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(ws, "_gpu_cache", [True])

    def install(name):
        snap = cache / ("models--" + ws.HF_REPOS[name].replace("/", "--")) / "snapshots" / "abc"
        snap.mkdir(parents=True)
        (snap / "model.bin").write_bytes(b"x")

    install("small")
    return type("E", (), {"install": staticmethod(install), "path": tmp_path / "settings.json"})


def test_default_is_small_on_cpu_and_lists_three_models(client, env):
    r = client.get("/api/settings")
    assert r.status_code == 200
    body = r.json()
    Settings.model_validate(body)
    assert (body["whisper_model"], body["whisper_device"]) == ("small", "cpu")
    assert (body["effective_model"], body["effective_device"]) == ("small", "cpu")
    assert [m["name"] for m in body["models"]] == ["small", "large-v3-turbo", "large-v3"]
    assert [m["installed"] for m in body["models"]] == [True, False, False]
    assert body["gpu_available"] is True and body["env_overrides"] == []


def test_save_and_read_back(client, env):
    env.install("large-v3-turbo")
    r = client.put("/api/settings", json={"whisper_model": "large-v3-turbo", "whisper_device": "cuda"})
    assert r.status_code == 200, r.text
    assert (r.json()["whisper_model"], r.json()["whisper_device"]) == ("large-v3-turbo", "cuda")
    assert json.loads(env.path.read_text()) == {"whisper_model": "large-v3-turbo", "whisper_device": "cuda"}
    assert client.get("/api/settings").json()["effective_model"] == "large-v3-turbo"


@pytest.mark.parametrize("body", [
    {"whisper_model": "medium", "whisper_device": "cpu"},      # medium is deliberately not offered
    {"whisper_model": "tiny", "whisper_device": "cpu"},
    {"whisper_model": "small", "whisper_device": "tpu"},
    {"whisper_model": "small"},
    {"whisper_model": "small", "whisper_device": "cpu", "extra": 1},
])
def test_rejects_unknown_values(client, env, body):
    r = client.put("/api/settings", json=body)
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"
    assert not env.path.exists()


def test_rejects_model_that_is_not_installed(client, env):
    r = client.put("/api/settings", json={"whisper_model": "large-v3", "whisper_device": "cpu"})
    assert r.status_code == 422
    assert "README" in r.json()["error"]["message"]
    assert not env.path.exists()


def test_rejects_gpu_when_there_is_none(client, env, monkeypatch):
    monkeypatch.setattr(ws, "_gpu_cache", [False])
    r = client.put("/api/settings", json={"whisper_model": "small", "whisper_device": "cuda"})
    assert r.status_code == 422
    assert client.put("/api/settings", json={"whisper_model": "small", "whisper_device": "auto"}).status_code == 200


def test_env_vars_still_win(client, env, monkeypatch):
    env.install("large-v3")
    client.put("/api/settings", json={"whisper_model": "large-v3", "whisper_device": "cpu"})
    monkeypatch.setenv("DSO_WHISPER_DEVICE", "cuda")
    body = client.get("/api/settings").json()
    assert body["whisper_device"] == "cpu" and body["effective_device"] == "cuda"
    assert body["env_overrides"] == ["DSO_WHISPER_DEVICE"]
    out = ws.pipeline_env({"DSO_WHISPER_DEVICE": "cuda"})
    assert out["DSO_WHISPER_DEVICE"] == "cuda" and out["DSO_WHISPER_MODEL"] == "large-v3"


def test_pipeline_env_uses_saved_setting_or_defaults(env):
    assert ws.pipeline_env({}) == {"DSO_WHISPER_MODEL": "small", "DSO_WHISPER_DEVICE": "cpu"}
    env.path.write_text(json.dumps({"whisper_model": "large-v3-turbo", "whisper_device": "auto"}))
    assert ws.pipeline_env({}) == {"DSO_WHISPER_MODEL": "large-v3-turbo", "DSO_WHISPER_DEVICE": "auto"}


def test_broken_settings_file_falls_back_to_defaults(env):
    env.path.write_text('{"whisper_model": "medium", "whisper_device": "cpu"}')
    assert ws.load() == ("small", "cpu")
    env.path.write_text("not json")
    assert ws.load() == ("small", "cpu")


def test_incomplete_download_is_not_installed(env, tmp_path):
    snap = tmp_path / "hf" / "models--Systran--faster-whisper-large-v3" / "snapshots" / "abc"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}")  # no model.bin yet
    assert ws.is_installed("large-v3") is False


def test_job_passes_the_setting_to_the_pipeline(env, monkeypatch, tmp_path):
    """The job runner hands the saved model + device to the pipeline subprocess (subprocess mocked)."""
    from app import jobs, settings

    env.path.write_text(json.dumps({"whisper_model": "large-v3-turbo", "whisper_device": "cuda"}))
    seen = {}

    class FakeProc:
        returncode = 1

        def __init__(self, cmd, **kw):
            seen.update(kw["env"])

        def poll(self):
            return 1

    orig = tmp_path / "data_orig.mp4"
    orig.write_bytes(b"x")
    monkeypatch.setattr(jobs.subprocess, "Popen", FakeProc)
    monkeypatch.setattr(settings, "PIPELINE_PYTHON", str(orig))  # any existing path
    monkeypatch.setattr(settings, "DATA_DIR", tmp_path)
    monkeypatch.setattr(jobs, "_update_job", lambda *a, **k: None)
    monkeypatch.setattr(jobs, "_set_asset_status", lambda *a, **k: None)
    monkeypatch.setattr(jobs, "_fail", lambda *a, **k: None)
    jobs._run_job("j_test", "a_test", "video", orig.name)
    assert seen["DSO_WHISPER_MODEL"] == "large-v3-turbo" and seen["DSO_WHISPER_DEVICE"] == "cuda"
