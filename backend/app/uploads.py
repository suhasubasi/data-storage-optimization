"""Save an original untouched (CONTRACTS.md §3 step 1): data/originals/<asset_id>/<filename>,
SHA-256 while streaming, then read-only (REC). Never overwrites or deletes anything."""
from __future__ import annotations

import hashlib
import os
import stat
import uuid
from pathlib import Path
from typing import BinaryIO

from dso_contracts.models import ErrorCode

from . import db, duplicates, settings
from .errors import ApiError

KIND_BY_EXT = {".mp4": "video", ".pdf": "document"}
CHUNK = 1024 * 1024


def safe_filename(name: str | None) -> str:
    base = Path((name or "").replace("\\", "/")).name.strip()
    if not base or base.startswith(".") or base.endswith(".part"):
        raise ApiError(ErrorCode.validation_error, "The uploaded file needs a normal file name.", {"filename": name})
    return base


def kind_for(filename: str) -> str:
    kind = KIND_BY_EXT.get(Path(filename).suffix.lower())
    if kind is None:
        raise ApiError(ErrorCode.unsupported_file_type, "Only .mp4 videos and .pdf documents are supported.",
                       {"filename": filename})
    return kind


def save_original(src: BinaryIO, filename: str | None, source_system: str, owner: str) -> str:
    """Returns the new asset id. Identical bytes uploaded twice -> two assets (simulated copies)."""
    filename = safe_filename(filename)
    kind = kind_for(filename)
    owner = (owner or "").strip()
    if not owner:
        raise ApiError(ErrorCode.validation_error, "Owner must not be empty.", {"field": "owner"})
    db.init_db()
    with db.read() as conn:
        while True:
            asset_id = "a_" + uuid.uuid4().hex[:8]
            if not conn.execute("SELECT 1 FROM assets WHERE id = ?", (asset_id,)).fetchone() \
                    and not (settings.ORIGINALS_DIR / asset_id).exists():
                break
    folder = settings.ORIGINALS_DIR / asset_id
    folder.mkdir(parents=True, exist_ok=False)
    target, part = folder / filename, folder / (filename + ".part")
    h, size = hashlib.sha256(), 0
    with open(part, "xb") as out:
        while chunk := src.read(CHUNK):
            h.update(chunk)
            out.write(chunk)
            size += len(chunk)
    os.replace(part, target)  # rename of our own temp file into a fresh, empty folder
    os.chmod(target, stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
    with db.write() as conn:
        conn.execute(
            "INSERT INTO assets (id, filename, kind, bytes, sha256, source_system, source_simulated, owner, status, "
            "original_path, created_at) VALUES (?,?,?,?,?,?,1,?,'uploaded',?,?)",
            (asset_id, filename, kind, size, h.hexdigest(), source_system, owner,
             f"originals/{asset_id}/{filename}", db.utc_now()))
    duplicates.recompute_matches()  # exact-file matches are known right after upload
    return asset_id
