"""REC v1.4: the user's Whisper model + device choice (Settings page).

Saved in data/settings.json (a small JSON file next to the database; no DB change). Only jobs started
after a change use it; nothing is re-processed automatically. Environment variables DSO_WHISPER_MODEL /
DSO_WHISPER_DEVICE still win over the saved setting. With no saved file the defaults come from
contracts/thresholds.json (small on CPU), so nothing changes for a user who never opens the page.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from pathlib import Path

from dso_contracts.models import (
    ErrorCode, Settings, SettingsUpdate, WhisperDevice, WhisperModelInfo, WhisperModelName,
)

from . import settings
from .errors import ApiError

log = logging.getLogger("dso.settings")

# Hugging Face repos faster-whisper 1.2.x downloads for each name (faster_whisper.utils._MODELS).
HF_REPOS = {
    "small": "Systran/faster-whisper-small",
    "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
    "large-v3": "Systran/faster-whisper-large-v3",
}
LABELS = {"small": "Fast", "large-v3-turbo": "Fast + accurate", "large-v3": "Most accurate"}
ENV_MODEL, ENV_DEVICE = "DSO_WHISPER_MODEL", "DSO_WHISPER_DEVICE"
_lock = threading.Lock()
_gpu_cache: list[bool | None] = []


def settings_path() -> Path:
    return Path(os.environ.get("DSO_SETTINGS_PATH", settings.DATA_DIR / "settings.json"))


def _defaults() -> tuple[str, str]:
    try:
        video = json.loads(settings.THRESHOLDS.read_text(encoding="utf-8")).get("video", {})
    except (OSError, ValueError):
        video = {}
    model = video.get("whisper_model", "small")
    device = video.get("whisper_device", "cpu")
    if model not in HF_REPOS:
        model = "small"
    if device not in {d.value for d in WhisperDevice}:
        device = "cpu"
    return model, device


def load() -> tuple[str, str]:
    """Saved (model, device). A missing or broken file means the defaults."""
    model, device = _defaults()
    try:
        raw = json.loads(settings_path().read_text(encoding="utf-8"))
        saved = SettingsUpdate.model_validate({"whisper_model": raw.get("whisper_model"),
                                               "whisper_device": raw.get("whisper_device")})
        return saved.whisper_model.value, saved.whisper_device.value
    except FileNotFoundError:
        return model, device
    except Exception as e:  # noqa: BLE001 - a hand-edited bad file must not break processing
        log.warning("ignoring invalid %s: %s", settings_path(), e)
        return model, device


def _cache_dirs() -> list[Path]:
    dirs = []
    for var in ("DSO_WHISPER_MODEL_DIR", "HF_HUB_CACHE", "HUGGINGFACE_HUB_CACHE"):
        if os.environ.get(var):
            dirs.append(Path(os.environ[var]))
    if os.environ.get("HF_HOME"):
        dirs.append(Path(os.environ["HF_HOME"]) / "hub")
    dirs.append(Path.home() / ".cache" / "huggingface" / "hub")
    return dirs


def is_installed(name: str) -> bool:
    """True when the model's weights (model.bin) are fully downloaded in a local Hugging Face cache."""
    folder = "models--" + HF_REPOS[name].replace("/", "--")
    for d in _cache_dirs():
        snaps = d / folder / "snapshots"
        if snaps.is_dir() and any((s / "model.bin").is_file() for s in snaps.iterdir()):
            return True
    return False


def _probe_gpu() -> bool | None:
    """Ask the PIPELINE venv (which has CTranslate2) how many NVIDIA GPUs it can use."""
    py = settings.PIPELINE_PYTHON
    if not Path(py).exists():
        return None
    try:
        r = subprocess.run([py, "-c", "import ctranslate2; print(ctranslate2.get_cuda_device_count())"],
                           capture_output=True, text=True, timeout=60)
        return int(r.stdout.strip().splitlines()[-1]) > 0 if r.returncode == 0 else None
    except Exception:  # noqa: BLE001
        return None


def gpu_available() -> bool | None:
    """Checked once per backend start (the answer does not change while it runs)."""
    with _lock:
        if not _gpu_cache:
            _gpu_cache.append(_probe_gpu())
        return _gpu_cache[0]


def current() -> Settings:
    model, device = load()
    overrides = [v for v in (ENV_MODEL, ENV_DEVICE) if os.environ.get(v)]
    return Settings(
        whisper_model=WhisperModelName(model),
        whisper_device=WhisperDevice(device),
        effective_model=os.environ.get(ENV_MODEL) or model,
        effective_device=(os.environ.get(ENV_DEVICE) or device).strip().lower(),
        env_overrides=overrides,
        models=[WhisperModelInfo(name=WhisperModelName(n), label=LABELS[n], installed=is_installed(n)) for n in HF_REPOS],
        gpu_available=gpu_available(),
    )


def save(update: SettingsUpdate) -> Settings:
    model, device = update.whisper_model.value, update.whisper_device.value
    if not is_installed(model):
        raise ApiError(ErrorCode.validation_error,
                       f"The model '{model}' is not installed on this computer. See the README "
                       "(section 'Which Whisper model?') for the one-line download command.",
                       {"whisper_model": model})
    if device == "cuda" and gpu_available() is False:
        raise ApiError(ErrorCode.validation_error,
                       "No usable NVIDIA GPU was found, so 'GPU' cannot be chosen. Pick Auto or CPU.",
                       {"whisper_device": device})
    p = settings_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"whisper_model": model, "whisper_device": device}, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, p)
    return current()


def pipeline_env(env: dict[str, str]) -> dict[str, str]:
    """Add the saved model + device for the pipeline subprocess. Env vars that are already set win."""
    model, device = load()
    if not env.get(ENV_MODEL):
        env[ENV_MODEL] = model
    if not env.get(ENV_DEVICE):
        env[ENV_DEVICE] = device
    return env
