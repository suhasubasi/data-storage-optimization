"""Real job progress: elapsed time and an ESTIMATE of time left, from the measured rate so far.

Nothing here invents progress. The percent comes from the pipeline's progress.json (each step reports
its real fraction; fixed step weights map it to 0..1, see pipeline/dso_pipeline/video.py). The time
left is only an estimate: we assume the rest goes at the same average speed as the part already done.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

# Hide the estimate until there is enough real progress to measure a rate.
ETA_MIN_PROGRESS = 0.03
ETA_MIN_ELAPSED_S = 10.0

_LOCK = threading.Lock()
# job_id -> {"stage_progress": float | None, "progress": float, "sample_monotonic": float, "sample_elapsed_s": float}
# In memory only (jobs run in this server process; after a restart running jobs are failed anyway).
_LIVE: dict[str, dict] = {}


def estimate_eta_s(elapsed_at_sample: float, progress: float, since_sample: float = 0.0) -> float | None:
    """Seconds left = time per unit of progress so far * progress still to do, minus the time that
    has passed since that progress was measured. None while there is too little data."""
    if progress < ETA_MIN_PROGRESS or elapsed_at_sample < ETA_MIN_ELAPSED_S or progress >= 1.0:
        return None
    left = elapsed_at_sample * (1.0 - progress) / progress - max(since_sample, 0.0)
    return round(max(left, 0.0), 1)


def parse_utc(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def elapsed_s(started_at: str | None, finished_at: str | None, now: datetime | None = None) -> float | None:
    start = parse_utc(started_at)
    if start is None:
        return None
    end = parse_utc(finished_at) or now or datetime.now(timezone.utc)
    return round(max((end - start).total_seconds(), 0.0), 1)


def record_sample(job_id: str, progress: float, stage_progress: float | None, elapsed: float) -> None:
    """Called by the job runner each time the pipeline writes a new progress.json."""
    with _LOCK:
        _LIVE[job_id] = {"progress": progress, "stage_progress": stage_progress,
                         "sample_monotonic": time.monotonic(), "sample_elapsed_s": elapsed}


def clear(job_id: str) -> None:
    with _LOCK:
        _LIVE.pop(job_id, None)


def live_fields(job_id: str, status: str, progress: float, started_at: str | None,
                finished_at: str | None) -> dict:
    """elapsed_s / eta_s / stage_progress for the Job response."""
    el = elapsed_s(started_at, finished_at)
    with _LOCK:
        live = dict(_LIVE.get(job_id) or {})
    stage_progress = live.get("stage_progress") if status == "running" else None
    eta = None
    if status == "running" and el is not None:
        if live:
            eta = estimate_eta_s(live["sample_elapsed_s"], live["progress"],
                                 time.monotonic() - live["sample_monotonic"])
        else:
            eta = estimate_eta_s(el, progress)
    return {"elapsed_s": el, "eta_s": eta, "stage_progress": stage_progress}
