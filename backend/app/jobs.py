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
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from dso_contracts.models import ErrorCode, Job

from . import db, ingest, progress, settings, whisper_settings
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
    # One transaction: a poller never sees the job 'failed' while the asset still says 'processing'.
    with db.write() as conn:
        conn.execute("UPDATE jobs SET status = 'failed', error = ?, finished_at = ? WHERE id = ?",
                     (message[:4000], db.utc_now(), job_id))
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
    finally:
        progress.clear(job_id)


def staging_root() -> Path:
    return settings.DERIVED_DIR / ".staging"


def trash_root() -> Path:
    return settings.DERIVED_DIR / ".trash"


def _rename(src: Path, dst: Path, tries: int = 40) -> None:
    """os.replace with retries: on Windows a folder cannot be renamed while a file inside is open
    (e.g. the API is serving a frame image at that moment)."""
    last: Exception | None = None
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError as e:
            last = e
            time.sleep(min(0.05 * (i + 1), 0.5))
    raise last  # type: ignore[misc]


def _rmtree_quiet(p: Path) -> None:
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)
        if p.exists():
            log.warning("could not fully remove %s (will retry at next start)", p)


def swap_in(asset_id: str, job_id: str, stage: Path) -> Path | None:
    """Make the finished staging folder the live derived folder. Returns where the previous
    folder was moved (to delete after a successful ingest), or None if there was none."""
    final = settings.DERIVED_DIR / asset_id
    old = None
    if final.exists():
        trash_root().mkdir(parents=True, exist_ok=True)
        old = trash_root() / f"{asset_id}-{job_id}"
        _rename(final, old)
    try:
        _rename(stage, final)
    except Exception:
        if old is not None:
            _rename(old, final)  # put the previous, working files back
        raise
    return old


def swap_back(asset_id: str, job_id: str, old: Path | None) -> None:
    """Undo swap_in after a failed ingest: the previous files come back, the new ones are discarded."""
    final = settings.DERIVED_DIR / asset_id
    if old is None:
        return
    failed = trash_root() / f"{asset_id}-{job_id}-failed"
    _rename(final, failed)
    _rename(old, final)
    _rmtree_quiet(failed)


def _run_job(job_id: str, asset_id: str, kind: str, original_path: str) -> None:
    """Runs the pipeline into a STAGING folder. The live derived folder (and so the Recording /
    Document pages) is untouched until the new run has finished and its manifest is valid; then the
    folders are swapped and ingested. If anything fails, the previous ready data stays as it was."""
    started = time.time()
    _update_job(job_id, status="running", stage="starting", started_at=db.utc_now())
    _set_asset_status(asset_id, "processing")
    input_path = settings.DATA_DIR / original_path
    stage = staging_root() / f"{asset_id}-{job_id}"
    if not input_path.exists():
        return _fail(job_id, asset_id, f"The original file is missing on disk ({original_path}). "
                                       "Fixture demo assets cannot be processed; upload a real file.")
    if not Path(settings.PIPELINE_PYTHON).exists():
        return _fail(job_id, asset_id, f"Pipeline Python not found at {settings.PIPELINE_PYTHON}. "
                                       "Set DSO_PIPELINE_PYTHON or create pipeline/.venv.")
    _rmtree_quiet(stage)
    stage.mkdir(parents=True, exist_ok=True)
    try:
        cmd = pipeline_command(asset_id, kind, input_path, stage)
        env = whisper_settings.pipeline_env(dict(os.environ))  # saved model + device (env vars still win)
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
                p = _read_json(stage / "progress.json", started)
                if p and (p.get("stage"), p.get("progress")) != last:
                    last = (p.get("stage"), p.get("progress"))
                    try:
                        prog = min(max(float(p.get("progress") or 0), 0.0), 0.99)
                    except (TypeError, ValueError):
                        prog = 0.0
                    try:
                        sp = p.get("stage_progress")
                        sp = None if sp is None else min(max(float(sp), 0.0), 1.0)
                    except (TypeError, ValueError):
                        sp = None
                    _update_job(job_id, progress=prog, stage=str(p.get("stage") or "running")[:200])
                    # Rate sample for the time-left ESTIMATE (elapsed when this real progress was seen).
                    progress.record_sample(job_id, prog, sp, time.time() - started)
                time.sleep(POLL_S)
            out.seek(0)
            tail = out.read().decode("utf-8", "replace")[-2000:].strip()
        manifest = stage / "manifest.json"
        if proc.returncode != 0:
            err = _read_json(stage / "error.json", started)
            reason = (err.get("message") or err.get("error") or json.dumps(err)) if err else (tail or "no output")
            return _fail(job_id, asset_id, f"Pipeline failed (exit {proc.returncode}): {reason}")
        if not manifest.exists() or manifest.stat().st_mtime + 1 < started:
            return _fail(job_id, asset_id, "Pipeline exited OK but did not write a new manifest.json.")
        try:
            ingest.load_manifest(manifest)  # validate BEFORE touching the live folder
        except ingest.IngestError as e:
            return _fail(job_id, asset_id, f"Could not ingest manifest.json: {e}")
        _update_job(job_id, stage="ingesting", progress=0.99)
        progress.record_sample(job_id, 0.99, None, time.time() - started)  # new step: no per-step fraction
        try:
            old = swap_in(asset_id, job_id, stage)
        except Exception as e:  # noqa: BLE001
            return _fail(job_id, asset_id, f"Could not switch to the new files ({type(e).__name__}: {e}); "
                                           "the previous files are still in use.")
        try:
            ingest.ingest_manifest(asset_id)
        except ingest.IngestError as e:
            swap_back(asset_id, job_id, old)
            return _fail(job_id, asset_id, f"Could not ingest manifest.json: {e}")
        except Exception:
            swap_back(asset_id, job_id, old)
            raise
        if old is not None:
            _rmtree_quiet(old)
        _update_job(job_id, status="done", progress=1.0, stage="done", error=None, finished_at=db.utc_now())
    finally:
        _rmtree_quiet(stage)  # no-op after a successful swap (the folder moved)


def clean_stale_staging() -> None:
    """On startup: staging / trash folders of jobs that cannot be running any more (own temp data only)."""
    for root in (staging_root(), trash_root()):
        if root.is_dir():
            for p in root.iterdir():
                if p.is_dir():
                    _rmtree_quiet(p)


def fail_stale_jobs() -> None:
    """On startup: jobs left 'queued'/'running' by a previous server process can't be running now."""
    with db.write() as conn:
        stale = conn.execute("SELECT id, asset_id FROM jobs WHERE status IN ('queued', 'running')").fetchall()
    for j in stale:
        _fail(j["id"], j["asset_id"], "The server restarted while this job was running. Start it again.")
