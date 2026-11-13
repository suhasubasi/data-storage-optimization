"""Shared helpers: hashing, text normalisation, thresholds, status files, atomic JSON writes."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from typing import Any

import imagehash
from PIL import Image

PKG_DIR = Path(__file__).resolve().parent
REPO_ROOT = PKG_DIR.parent.parent
DEFAULT_THRESHOLDS = REPO_ROOT / "contracts" / "thresholds.json"

_WS = re.compile(r"\s+")


def load_thresholds() -> dict[str, Any]:
    """contracts/thresholds.json (override path with env DSO_THRESHOLDS)."""
    path = Path(os.environ.get("DSO_THRESHOLDS", DEFAULT_THRESHOLDS))
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    """SHA-256 of a file, read-only, streamed (works for multi-GB recordings)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def normalise_text(text: str) -> str:
    """CONTRACTS.md §3: NFKC -> lowercase -> collapse whitespace -> strip."""
    return _WS.sub(" ", unicodedata.normalize("NFKC", text).lower()).strip()


def text_sha256(text: str) -> str:
    return hashlib.sha256(normalise_text(text).encode("utf-8")).hexdigest()


def phash_hex(img: Image.Image, hash_size: int = 8) -> str:
    """imagehash.phash(hash_size=8) as 16 lowercase hex chars."""
    return str(imagehash.phash(img.convert("RGB"), hash_size=hash_size)).lower()


def phash_file(path: Path, hash_size: int = 8) -> str:
    with Image.open(path) as im:
        return phash_hex(im, hash_size)


def phash_distance(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def write_json_atomic(path: Path, data: Any) -> None:
    """Write to <name>.tmp then rename, so readers never see a half-written file.

    On Windows, os.replace can raise PermissionError (WinError 5) if another process
    has the destination open (the API or UI polling progress.json, antivirus, etc.).
    Retry with a short backoff; if it is still locked, overwrite in place so a
    progress update cannot kill a long job.
    """
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    last_err: Exception | None = None
    for attempt in range(12):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as e:
            last_err = e
            time.sleep(0.05 * (attempt + 1))
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    except OSError:
        if last_err:
            raise last_err
        raise


class Status:
    """progress.json / error.json in the derived folder (status files, never counted as derived data)."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.stage = "starting"
        self._last_progress_write = -1.0
        self._last_progress_value = -1.0
        self._last_stage_written: str | None = None

    def progress(self, stage: str, progress: float, stage_progress: float | None = None) -> None:
        """progress = whole job (0..1, stage-weighted: fixed weights per step, see video.py).
        stage_progress = real fraction of the CURRENT step only (e.g. transcribing = last finished
        Whisper segment end / media duration). It is only written when the step really measures it."""
        self.stage = stage
        value = round(max(0.0, min(1.0, progress)), 3)
        now = time.monotonic()
        should_write = (
            stage != self._last_stage_written
            or value >= 1.0
            or self._last_progress_write < 0
            or abs(value - self._last_progress_value) >= 0.02
            or (now - self._last_progress_write) >= 0.5
        )
        if not should_write:
            return
        data: dict[str, Any] = {"stage": stage, "progress": value}
        if stage_progress is not None:
            data["stage_progress"] = round(max(0.0, min(1.0, stage_progress)), 3)
        write_json_atomic(self.out_dir / "progress.json", data)
        self._last_progress_write = now
        self._last_progress_value = value
        self._last_stage_written = stage

    def error(self, message: str, details: dict[str, Any] | None = None) -> None:
        write_json_atomic(
            self.out_dir / "error.json",
            {"error": {"code": "pipeline_failed", "message": message, "details": details}},
        )
