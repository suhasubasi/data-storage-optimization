import hashlib
import os
import stat
import sys
import textwrap
import time

import pytest

from app import settings

FAKE_PIPELINE = textwrap.dedent('''
    """Fake dso_pipeline for backend tests: writes one page + manifest.json (last), like Stream 3 will."""
    import argparse, hashlib, json, os, sys, time
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd")
    q = sub.add_parser("process")
    for a in ("--asset-id", "--kind", "--input", "--out"): q.add_argument(a, required=True)
    a = p.parse_args()
    data = open(a.input, "rb").read()
    os.makedirs(os.path.join(a.out, "pages"), exist_ok=True)
    json.dump({"stage": "rendering pages", "progress": 0.5}, open(os.path.join(a.out, "progress.json"), "w"))
    if b"SLOW" in data: time.sleep(1.5)
    if b"FAIL" in data:
        json.dump({"message": "PDF is encrypted"}, open(os.path.join(a.out, "error.json"), "w"))
        print("boom", file=sys.stderr); sys.exit(3)
    img = os.path.join(a.out, "pages", "p1.webp"); open(img, "wb").write(b"RIFF....WEBP" * 10)
    text = "Quarterly antenna tilt review for the northern region"
    norm = " ".join(text.lower().split())
    m = {"schema_version": "1.0", "asset_id": a.asset_id, "kind": a.kind,
         "original": {"path": "originals/%s/%s" % (a.asset_id, os.path.basename(a.input)), "bytes": len(data),
                      "sha256": hashlib.sha256(data).hexdigest()},
         "metadata": {"title": None, "author": None, "doc_number": None, "revision": None, "date": None, "language": None},
         "segments": [], "frames": [],
         "slides": [{"id": "p1", "page": 1, "text": text, "text_sha256": hashlib.sha256(norm.encode()).hexdigest(),
                     "phash": "8f3c1a2b4d5e6f70", "path": "pages/p1.webp", "bytes": os.path.getsize(img)}],
         "derived_files": [{"path": "pages/p1.webp", "bytes": os.path.getsize(img), "kind": "page_image"}],
         "pipeline": {"version": "fake", "model": None, "frame_threshold": None, "seconds": 0.1, "warnings": []}}
    tmp = os.path.join(a.out, "manifest.json.tmp"); json.dump(m, open(tmp, "w")); os.replace(tmp, os.path.join(a.out, "manifest.json"))
''')


@pytest.fixture
def fake_pipeline(tmp_path, monkeypatch):
    pkg = tmp_path / "dso_pipeline"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "__main__.py").write_text(FAKE_PIPELINE)
    monkeypatch.setattr(settings, "PIPELINE_PYTHON", sys.executable)
    monkeypatch.setattr(settings, "PIPELINE_CWD", tmp_path)


def upload(client, name="deck.pdf", data=b"%PDF-1.4 hello", owner="anna", src="sharepoint"):
    return client.post("/api/assets", files={"file": (name, data, "application/octet-stream")},
                       data={"source_system": src, "owner": owner})


def wait_job(client, job_id, timeout=20):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] in ("done", "failed"):
            return j
        time.sleep(0.1)
    raise AssertionError("job did not finish")


def test_upload_saves_untouched_readonly_original(empty):
    data = os.urandom(4096)
    r = upload(empty, "My Deck.PDF", data)
    assert r.status_code == 201
    a = r.json()
    assert a["kind"] == "document" and a["status"] == "uploaded" and a["bytes"] == 4096
    assert a["sha256"] == hashlib.sha256(data).hexdigest() and a["source_simulated"] is True
    p = settings.ORIGINALS_DIR / a["id"] / "My Deck.PDF"
    assert p.read_bytes() == data and not (p.stat().st_mode & stat.S_IWUSR)
    assert a["original_url"] == f"/files/originals/{a['id']}/My Deck.PDF"
    r = empty.get(a["original_url"], headers={"Range": "bytes=0-9"})
    assert r.status_code == 206 and r.content == data[:10]


def test_upload_validation(empty):
    r = upload(empty, "notes.txt")
    assert r.status_code == 415 and r.json()["error"]["code"] == "unsupported_file_type"
    r = empty.post("/api/assets", files={"file": ("a.pdf", b"x")}, data={"source_system": "dropbox", "owner": "x"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = empty.post("/api/assets", files={"file": ("a.pdf", b"x")}, data={"source_system": "onedrive"})
    assert r.status_code == 422
    r = upload(empty, owner="   ")
    assert r.status_code == 422


def test_identical_upload_twice_is_two_assets_and_exact_duplicate(empty):
    a = upload(empty, "deck.pdf", b"%PDF same").json()
    b = upload(empty, "deck (1).pdf", b"%PDF same", owner="bo", src="onedrive").json()
    assert a["id"] != b["id"]
    g = empty.get("/api/duplicates").json()["groups"]
    assert len(g) == 1 and g[0]["type"] == "exact_file"
    assert [m["asset_id"] for m in g[0]["members"]] == [a["id"], b["id"]]


def test_process_job_runs_pipeline_and_ingests(empty, fake_pipeline):
    a = upload(empty).json()
    r = empty.post(f"/api/assets/{a['id']}/process")
    assert r.status_code == 202 and r.json()["status"] in ("queued", "running")
    j = wait_job(empty, r.json()["id"])
    assert j["status"] == "done" and j["progress"] == 1.0 and j["error"] is None and j["finished_at"]
    d = empty.get(f"/api/assets/{a['id']}").json()
    assert d["asset"]["status"] == "ready" and d["derived"]["slide_count"] == 1 and d["latest_job"]["id"] == j["id"]
    man = settings.DERIVED_DIR / a["id"] / "manifest.json"
    assert d["derived"]["manifest_bytes"] == man.stat().st_size
    hits = empty.get("/api/search", params={"q": "antenna tilt"}).json()["hits"]
    assert hits and hits[0]["page"] == 1 and hits[0]["media"]["url"] == f"/files/derived/{a['id']}/pages/p1.webp"
    assert empty.get(hits[0]["media"]["url"]).status_code == 200
    assert empty.get(f"/files/derived/{a['id']}/manifest.json").status_code == 200
    # original is untouched after processing
    assert (settings.ORIGINALS_DIR / a["id"] / "deck.pdf").read_bytes() == b"%PDF-1.4 hello"


def test_failed_pipeline_is_reported_honestly(empty, fake_pipeline):
    a = upload(empty, data=b"%PDF FAIL").json()
    j = wait_job(empty, empty.post(f"/api/assets/{a['id']}/process").json()["id"])
    assert j["status"] == "failed" and "PDF is encrypted" in j["error"] and "exit 3" in j["error"]
    assert empty.get(f"/api/assets/{a['id']}").json()["asset"]["status"] == "failed"


def test_second_process_while_running_is_conflict(empty, fake_pipeline):
    a = upload(empty, data=b"%PDF SLOW").json()
    j = empty.post(f"/api/assets/{a['id']}/process").json()
    r = empty.post(f"/api/assets/{a['id']}/process")
    assert r.status_code == 409 and r.json()["error"]["code"] == "conflict"
    assert wait_job(empty, j["id"])["status"] == "done"
    assert empty.post(f"/api/assets/{a['id']}/process").status_code == 202  # re-processing a ready asset is allowed


def test_missing_pipeline_python_fails_job(empty, monkeypatch):
    monkeypatch.setattr(settings, "PIPELINE_PYTHON", "/nonexistent/python")
    a = upload(empty).json()
    j = wait_job(empty, empty.post(f"/api/assets/{a['id']}/process").json()["id"])
    assert j["status"] == "failed" and "Pipeline Python not found" in j["error"]


def test_process_unknown_asset(empty):
    assert empty.post("/api/assets/a_nope/process").status_code == 404


def test_file_serving_is_confined(demo):
    assert demo.get("/files/derived/a_01/../../dso.sqlite").status_code == 404
    assert demo.get("/files/derived/a_01/%2e%2e/%2e%2e/dso.sqlite").status_code == 404
    r = demo.get("/files/originals/a_01/event-recording.mp4")  # demo data: no real file on disk
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
