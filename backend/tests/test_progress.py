"""Real job progress: elapsed time, time-left ESTIMATE math, and the Job fields while a job runs."""
import sys
import textwrap
import time
from datetime import datetime, timezone

import pytest

from app import progress, settings

from test_upload_jobs import upload, wait_job


def test_eta_hidden_until_enough_progress():
    assert progress.estimate_eta_s(60.0, 0.02) is None      # < 3 % done
    assert progress.estimate_eta_s(5.0, 0.5) is None        # < 10 s measured
    assert progress.estimate_eta_s(100.0, 1.0) is None      # finished
    assert progress.estimate_eta_s(10.0, 0.03) == pytest.approx(323.3, abs=0.1)


def test_eta_from_measured_rate():
    # 20 % took 6 minutes -> the remaining 80 % take about 24 minutes at the same speed.
    assert progress.estimate_eta_s(360.0, 0.2) == 1440.0
    # Time that passed since the sample counts down the estimate, never below 0.
    assert progress.estimate_eta_s(360.0, 0.2, since_sample=40.0) == 1400.0
    assert progress.estimate_eta_s(360.0, 0.9, since_sample=999.0) == 0.0


def test_elapsed_seconds():
    now = datetime(2026, 11, 13, 10, 0, 30, tzinfo=timezone.utc)
    assert progress.elapsed_s("2026-11-13T10:00:00.000Z", None, now) == 30.0
    assert progress.elapsed_s("2026-11-13T10:00:00.000Z", "2026-11-13T10:05:00.500Z", now) == 300.5
    assert progress.elapsed_s(None, None, now) is None
    assert progress.elapsed_s("not a date", None, now) is None


def test_live_fields_only_estimate_while_running():
    progress.record_sample("j_t1", 0.5, 0.25, 120.0)
    try:
        f = progress.live_fields("j_t1", "running", 0.5, "2026-11-13T10:00:00Z", None)
        assert f["stage_progress"] == 0.25 and f["eta_s"] is not None and f["eta_s"] <= 120.0
        done = progress.live_fields("j_t1", "done", 1.0, "2026-11-13T10:00:00Z", "2026-11-13T10:04:00Z")
        assert done == {"elapsed_s": 240.0, "eta_s": None, "stage_progress": None}
    finally:
        progress.clear("j_t1")


SLOW_PIPELINE = textwrap.dedent('''
    """Fake pipeline (test only): reports real-looking stage progress, then fails on purpose."""
    import argparse, json, os, sys, time
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd")
    q = sub.add_parser("process")
    for a in ("--asset-id", "--kind", "--input", "--out"): q.add_argument(a, required=True)
    a = p.parse_args()
    os.makedirs(a.out, exist_ok=True)
    json.dump({"stage": "transcribing", "progress": 0.5, "stage_progress": 0.25},
              open(os.path.join(a.out, "progress.json"), "w"))
    time.sleep(3)
    json.dump({"message": "stop here (test)"}, open(os.path.join(a.out, "error.json"), "w")); sys.exit(4)
''')


@pytest.fixture
def slow_pipeline(tmp_path, monkeypatch):
    pkg = tmp_path / "dso_pipeline"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "__main__.py").write_text(SLOW_PIPELINE)
    monkeypatch.setattr(settings, "PIPELINE_PYTHON", sys.executable)
    monkeypatch.setattr(settings, "PIPELINE_CWD", tmp_path)
    monkeypatch.setattr(progress, "ETA_MIN_ELAPSED_S", 0.0)  # the test job is short


def test_running_job_reports_stage_progress_elapsed_and_eta(empty, slow_pipeline):
    a = upload(empty, data=b"%PDF-1.4 slow").json()
    job = empty.post(f"/api/assets/{a['id']}/process").json()
    seen = None
    end = time.time() + 15
    while time.time() < end:
        j = empty.get(f"/api/jobs/{job['id']}").json()
        if j["status"] == "running" and j.get("stage_progress") is not None:
            seen = j
            break
        time.sleep(0.1)
    assert seen, "running job never showed its stage progress"
    assert seen["stage"] == "transcribing" and seen["progress"] == 0.5 and seen["stage_progress"] == 0.25
    assert seen["elapsed_s"] is not None and seen["elapsed_s"] >= 0
    assert seen["eta_s"] is not None and seen["eta_s"] >= 0
    final = wait_job(empty, job["id"])
    assert final["status"] == "failed" and final["eta_s"] is None and final["stage_progress"] is None
    assert final["elapsed_s"] is not None
