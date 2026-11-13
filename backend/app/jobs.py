"""Job runner (CONTRACTS.md §4): background thread runs the pipeline as a SEPARATE PROCESS
using the pipeline's own venv, so heavy ML deps (faster-whisper, ffmpeg bindings) never enter the
backend venv:

    <DSO_PIPELINE_PYTHON> -m dso_pipeline process --asset-id a_01 --kind video|document \
        --input data/originals/a_01/<file> --out data/derived/a_01

Exit 0 + manifest.json present = done -> ingest. Non-zero = failed (reason from error.json or
stderr). progress.json gives real progress; we never fake it.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from dso_contracts.models import ErrorCode, Job

from . import db, ingest, settings
from .errors import ApiError
from .services import get_asset_row, to_job

log = logging.getLogger("dso.jobs")
POLL_S = 0.5


def new_job_id() -> str:
    return "j_" + uuid.uuid4().hex[:10]


def start_job(asset_id: str) -> Job:
    with db.write() as conn:
        row = get_asset_row(conn, asset_id)
        busy = conn.execute("SELECT id FROM jobs WHERE asset_id = ? AND status IN ('queued', 'running')",
                            (asset_id,)).fetchone()
        if busy:
            raise ApiError(ErrorCode.conflict, f"A job for {asset_id} is already running ({busy['id']}).",
                           {"job_id": busy["id"]})
        job_id = new_job_id()
        conn.execute("INSERT INTO jobs (id, asset_id, status, progress, stage) VALUES (?, ?, 'queued', 0, 'queued')",
                     (job_id, asset_id))
        conn.execute("UPDATE assets SET status = 'queued' WHERE id = ?", (asset_id,))
        job = to_job(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())
        kind, original_path = row["kind"], row["original_path"]
    threading.Thread(target=run_job, args=(job_id, asset_id, kind, original_path), daemon=True,
                     name=f"job-{job_id}").start()
    return job


def get_job(job_id: str) -> Job:
    with db.read() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise ApiError(ErrorCode.not_found, f"Job {job_id} was not found.")
        return to_job(row)


def _update_job(job_id: str, **fields) -> None:
    cols = ", ".join(f"{k} = ?" for k in fields)
    with db.write() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", (*fields.values(), job_id))


def _set_asset_status(asset_id: str, status: str) -> None:
    with db.write() as conn:
        conn.execute("UPDATE assets SET status = ? WHERE id = ?", (status, asset_id))


def _read_json(path: Path, newer_than: float) -> dict | None:
    """Read a status file only if it was written during THIS run (ignores stale files)."""
    try:
        if path.stat().st_mtime + 1 < newer_than:
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"message": str(data)}
    except (OSError, ValueError):
        return None


def _fail(job_id: str, asset_id: str, message: str) -> None:
    log.warning("job %s failed: %s", job_id, message)
    _update_job(job_id, status="failed", error=message[:4000], finished_at=db.utc_now())
    with db.write() as conn:
        had = conn.execute("SELECT manifest_bytes FROM assets WHERE id = ?", (asset_id,)).fetchone()
        # REC: if an earlier run was ingested, its data stays valid -> asset stays 'ready'.
        conn.execute("UPDATE assets SET status = ? WHERE id = ?",
                     ("ready" if had and had["manifest_bytes"] is not None else "failed", asset_id))


def pipeline_command(asset_id: str, kind: str, input_path: Path, out_dir: Path) -> list[str]:
    return [settings.PIPELINE_PYTHON, "-m", "dso_pipeline", "process", "--asset-id", asset_id, "--kind", kind,
            "--input", str(input_path), "--out", str(out_dir)]


def run_job(job_id: str, asset_id: str, kind: str, original_path: str) -> None:
    try:
        _run_job(job_id, asset_id, kind, original_path)
    except Exception as e:  # never leave a job 'running' forever
        log.exception("job %s crashed", job_id)
        _fail(job_id, asset_id, f"Backend error while running the job: {type(e).__name__}: {e}")


def _run_job(job_id: str, asset_id: str, kind: str, original_path: str) -> None:
    started = time.time()
    _update_job(job_id, status="running", stage="starting", started_at=db.utc_now())
    _set_asset_status(asset_id, "processing")
    input_path = settings.DATA_DIR / original_path
    out_dir = settings.DERIVED_DIR / asset_id
    if not input_path.exists():
        return _fail(job_id, asset_id, f"The original file is missing on disk ({original_path}). "
                                       "Fixture demo assets cannot be processed; upload a real file.")
    if not Path(settings.PIPELINE_PYTHON).exists():
        return _fail(job_id, asset_id, f"Pipeline Python not found at {settings.PIPELINE_PYTHON}. "
                                       "Set DSO_PIPELINE_PYTHON or create pipeline/.venv.")
    cmd = pipeline_command(asset_id, kind, input_path, out_dir)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(settings.PIPELINE_CWD), env.get("PYTHONPATH")) if p)
    with tempfile.TemporaryFile() as out:
        proc = subprocess.Popen(cmd, cwd=settings.PIPELINE_CWD if settings.PIPELINE_CWD.exists() else None,
                                stdout=out, stderr=subprocess.STDOUT, env=env)
        last = None
        while proc.poll() is None:
            if time.time() - started > settings.PIPELINE_TIMEOUT_S:
                proc.kill()
                proc.wait()
                return _fail(job_id, asset_id, f"Pipeline timed out after {int(settings.PIPELINE_TIMEOUT_S)} s.")
            p = _read_json(out_dir / "progress.json", started)
            if p and (p.get("stage"), p.get("progress")) != last:
                last = (p.get("stage"), p.get("progress"))
                try:
                    prog = min(max(float(p.get("progress") or 0), 0.0), 0.99)
                except (TypeError, ValueError):
                    prog = 0.0
                _update_job(job_id, progress=prog, stage=str(p.get("stage") or "running")[:200])
            time.sleep(POLL_S)
        out.seek(0)
        tail = out.read().decode("utf-8", "replace")[-2000:].strip()
    manifest = out_dir / "manifest.json"
    if proc.returncode != 0:
        err = _read_json(out_dir / "error.json", started)
        reason = (err.get("message") or err.get("error") or json.dumps(err)) if err else (tail or "no output")
        return _fail(job_id, asset_id, f"Pipeline failed (exit {proc.returncode}): {reason}")
    if not manifest.exists() or manifest.stat().st_mtime + 1 < started:
        return _fail(job_id, asset_id, "Pipeline exited OK but did not write a new manifest.json.")
    _update_job(job_id, stage="ingesting", progress=0.99)
    try:
        ingest.ingest_manifest(asset_id, manifest)
    except ingest.IngestError as e:
        return _fail(job_id, asset_id, f"Could not ingest manifest.json: {e}")
    _update_job(job_id, status="done", progress=1.0, stage="done", error=None, finished_at=db.utc_now())


def fail_stale_jobs() -> None:
    """On startup: jobs left 'queued'/'running' by a previous server process can't be running now."""
    with db.write() as conn:
        stale = conn.execute("SELECT id, asset_id FROM jobs WHERE status IN ('queued', 'running')").fetchall()
    for j in stale:
        _fail(j["id"], j["asset_id"], "The server restarted while this job was running. Start it again.")
