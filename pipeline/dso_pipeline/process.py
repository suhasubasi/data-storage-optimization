"""Orchestrates one run: safety checks -> kind processor -> validate -> manifest.json LAST (atomic).

Never deletes or modifies the original. The only things removed are this pipeline's own previous
outputs inside --out (stale frames/pages/transcript/status files) and its temp files.
"""
from __future__ import annotations

import os
import shutil
import time
import traceback
from pathlib import Path
from typing import Any

from dso_contracts.models import Manifest

from . import __version__
from .common import Status, load_thresholds, sha256_file, write_json_atomic

# Only these names inside --out are ever cleaned (our own outputs from an earlier run).
_OWN_OUTPUTS = ("manifest.json", "manifest.json.tmp", "error.json", "progress.json", "transcript.json", "frames", "pages")


class PipelineError(RuntimeError):
    pass


def _data_dir(input_path: Path, out_dir: Path) -> Path:
    if os.environ.get("DSO_DATA_DIR"):
        return Path(os.environ["DSO_DATA_DIR"]).resolve()
    for parent in input_path.parents:
        if parent.name == "originals":
            return parent.parent
    if out_dir.parent.name == "derived":
        return out_dir.parent.parent
    return input_path.parent


def _check_paths(input_path: Path, out_dir: Path) -> None:
    if not input_path.is_file():
        raise PipelineError(f"input file not found: {input_path}")
    if out_dir == input_path.parent or out_dir in input_path.parents:
        raise PipelineError("--out must not contain the original file (originals are read-only)")
    if any(p.name == "originals" for p in [out_dir, *out_dir.parents]):
        raise PipelineError("--out must not be inside an originals/ folder")


def _clean_previous(out_dir: Path) -> None:
    for name in _OWN_OUTPUTS:
        p = out_dir / name
        if p.is_dir() and not p.is_symlink():
            shutil.rmtree(p)
        elif p.exists() or p.is_symlink():
            p.unlink()


def run(asset_id: str, kind: str, input_path: Path, out_dir: Path) -> dict[str, Any]:
    t0 = time.monotonic()
    input_path = input_path.resolve()
    out_dir = out_dir.resolve()
    try:
        _check_paths(input_path, out_dir)
    except PipelineError as e:
        # Still report in error.json when --out itself is a safe place to write.
        if not any(p.name == "originals" for p in [out_dir, *out_dir.parents]) and out_dir not in input_path.parents:
            out_dir.mkdir(parents=True, exist_ok=True)
            Status(out_dir).error(str(e), {"stage": "checking input"})
        raise
    out_dir.mkdir(parents=True, exist_ok=True)
    _clean_previous(out_dir)
    status = Status(out_dir)

    try:
        status.progress("hashing original", 0.0)
        st_before = input_path.stat()
        file_sha = sha256_file(input_path)
        thresholds = load_thresholds()

        if kind == "document":
            with open(input_path, "rb") as f:
                head = f.read(5)
            if head == b"%PDF-":
                from .document import process_document
                parts = process_document(input_path, out_dir, thresholds, status)
            else:
                from .presentation import is_pptx, process_presentation
                if not is_pptx(input_path):
                    raise PipelineError("kind 'document' needs a PDF or a PowerPoint .pptx file")
                parts = process_presentation(input_path, out_dir, thresholds, status)
        elif kind == "video":
            from .video import process_video
            parts = process_video(input_path, out_dir, thresholds, status)
        else:
            raise PipelineError(f"unknown kind: {kind}")

        st_after = input_path.stat()
        if (st_after.st_size, st_after.st_mtime_ns) != (st_before.st_size, st_before.st_mtime_ns):
            raise PipelineError("original file changed during processing; refusing to write a manifest")

        # Re-measure every derived file on disk (sizes must be real).
        for d in parts["derived_files"]:
            d["bytes"] = (out_dir / d["path"]).stat().st_size

        rel_original = os.path.relpath(input_path, _data_dir(input_path, out_dir)).replace(os.sep, "/")
        pipeline_info: dict[str, Any] = {
            "version": __version__,
            "model": parts["model"],
            "frame_threshold": parts["frame_threshold"],
            "seconds": round(time.monotonic() - t0, 3),
        }
        if parts["warnings"]:
            pipeline_info["warnings"] = parts["warnings"]
        if parts.get("unique_slides"):
            pipeline_info["unique_slides"] = parts["unique_slides"]
        manifest = {
            "schema_version": "1.0",
            "asset_id": asset_id,
            "kind": kind,
            "original": {"path": rel_original, "bytes": st_before.st_size, "sha256": file_sha},
            "metadata": parts["metadata"],
            "segments": parts["segments"],
            "frames": parts["frames"],
            "slides": parts["slides"],
            "derived_files": parts["derived_files"],
            "pipeline": pipeline_info,
        }
        Manifest.model_validate(manifest)  # raises on any contract violation

        status.progress("done", 1.0)
        manifest["pipeline"]["seconds"] = round(time.monotonic() - t0, 3)
        write_json_atomic(out_dir / "manifest.json", manifest)  # LAST
        return manifest
    except Exception as e:  # noqa: BLE001 - report every failure in error.json
        status.error(
            f"Processing failed while {status.stage}: {e}",
            {"stage": status.stage, "type": type(e).__name__, "trace": traceback.format_exc(limit=5)},
        )
        raise
