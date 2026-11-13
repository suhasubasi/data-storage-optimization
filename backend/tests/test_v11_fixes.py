"""v1.1 fixes: title search, real-files storage scope, text/PPTX/PDF exports, safe re-process."""
import io
import json
import os
import sys
import textwrap
import time

import pytest

from app import db, ingest, settings
from conftest import write_file

from test_upload_jobs import upload, wait_job


# ---------------------------------------------------------------------------------------------
# search: title / file name / metadata
# ---------------------------------------------------------------------------------------------
def test_title_and_filename_are_searchable(demo):
    hits = demo.get("/api/search", params={"q": "event recording"}).json()["hits"]
    assert [(h["hit_type"], h["asset_id"]) for h in hits] == [("asset", "a_01")]
    h = hits[0]
    assert h["item_id"] == "meta" and "<mark>" in h["snippet"] and h["media"]["item_id"] == "f1"
    assert h["start"] is None and h["frame_id"] is None
    # metadata title of a_01 ('RAN evolution session') also matches, and the transcript still does
    kinds = {(x["hit_type"], x["asset_id"]) for x in demo.get("/api/search", params={"q": "evolution session"}).json()["hits"]}
    assert ("asset", "a_01") in kinds and ("segment", "a_01") in kinds


def test_title_search_negative_controls(demo):
    # unprocessed file (a_05, carl-notes.pdf) is not indexed; a word in no title/text finds nothing
    assert demo.get("/api/search", params={"q": "carl notes"}).json()["total"] == 0
    assert demo.get("/api/search", params={"q": "openprose"}).json()["total"] == 0


def test_reindex_is_idempotent(demo):
    ingest.reindex_asset_metadata()
    ingest.reindex_asset_metadata()
    with db.read() as conn:
        rows = conn.execute("SELECT asset_id, COUNT(*) FROM search_fts WHERE item_type = 'asset' GROUP BY asset_id").fetchall()
    assert {r[0]: r[1] for r in rows} == {"a_01": 1, "a_02": 1, "a_03": 1, "a_04": 1}


# ---------------------------------------------------------------------------------------------
# storage report scope
# ---------------------------------------------------------------------------------------------
def _label(aid: str) -> None:
    with db.write() as conn:
        conn.execute("INSERT INTO asset_labels (asset_id, test_data, note) VALUES (?, 1, 'generated')", (aid,))


def test_storage_defaults_to_real_files_and_toggle_includes_test_data(demo):
    before = demo.get("/api/storage/report", params={"include_test_data": "true"}).json()
    assert before["scope"] == "all_files" and before["totals"]["derived_bytes"] == 913_523
    _label("a_03")
    assets = {a["id"]: a for a in demo.get("/api/assets").json()["assets"]}
    assert assets["a_03"]["test_data"] is True and assets["a_02"]["test_data"] is False
    r = demo.get("/api/storage/report").json()
    assert r["scope"] == "real_files"
    assert r["excluded_test_data"]["asset_ids"] == ["a_03"]
    assert r["excluded_test_data"]["original_bytes"] == 2_400_000
    assert r["totals"]["original_bytes"] == before["totals"]["original_bytes"] - 2_400_000
    assert r["totals"]["asset_count"] == before["totals"]["asset_count"] - 1
    a03_derived = assets["a_03"]["derived_bytes"]
    assert r["totals"]["derived_bytes"] == 913_523 - a03_derived
    # a_03 was the extra exact copy; without it there is nothing to remove in scenario 2
    s = {x["key"]: x for x in r["scenarios"]}
    assert s["remove_exact_duplicates"]["removed"] == []
    assert r["notes"][0].startswith("Scope: real uploaded files only. 1 generated test files")
    for x in r["scenarios"]:
        assert x["after_bytes"] == x["kept_original_bytes"] + x["derived_bytes"] + x["index_bytes"]
    again = demo.get("/api/storage/report", params={"include_test_data": "true"}).json()
    assert again["totals"]["original_bytes"] == before["totals"]["original_bytes"]
    assert again["excluded_test_data"]["asset_count"] == 0


# ---------------------------------------------------------------------------------------------
# exports
# ---------------------------------------------------------------------------------------------
def test_transcript_txt_is_plain_text_in_order(demo):
    r = demo.get("/api/assets/a_01/transcript.txt")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    assert 'filename="event-recording.transcript.txt"' in r.headers["content-disposition"]
    body = r.text
    assert not body.lstrip().startswith("{")
    lines = [ln for ln in body.splitlines() if ln.startswith("[")]
    assert len(lines) == 5 and lines[0].startswith("[00:00:00 - ") and "Welcome everyone" in lines[0]
    assert "Speaker names are not identified" in body
    assert demo.get("/api/assets/a_01/export", params={"format": "txt"}).text == body  # never silently JSON
    assert demo.get("/api/assets/a_01/export").json()["chunks"]  # default still JSON
    flowing = demo.get("/api/assets/a_01/transcript.txt", params={"timestamps": "false"}).text
    assert "[00:" not in flowing and "Welcome everyone" in flowing
    doc = demo.get("/api/assets/a_02/transcript.txt").text
    assert "--- Page 1 ---" in doc
    assert demo.get("/api/assets/a_05/transcript.txt").status_code == 409  # not processed
    assert demo.get("/api/assets/a_01/export", params={"format": "xml"}).status_code == 422


def test_slide_deck_needs_the_unique_slide_pass(demo):
    r = demo.get("/api/assets/a_01/slides.pptx")
    assert r.status_code == 409 and "unique-slide pass" in r.json()["error"]["message"]


def _video_with_unique_slides(client):
    """A tiny processed recording whose frames already went through the unique-slide pass:
    4 time ranges, 3 unique images (the talk goes back to slide 1)."""
    from PIL import Image

    data = b"\x00\x00\x00\x18ftypmp42 tiny test video"
    a = upload(client, "talk.mp4", data, owner="erik", src="ericsson_play").json()
    aid = a["id"]
    base = settings.DERIVED_DIR / aid
    colors = {"frames/f1.webp": (200, 30, 30), "frames/f2.webp": (30, 200, 30), "frames/f4.webp": (30, 30, 200)}
    sizes = {}
    for rel, c in colors.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (320, 180), c).save(p, "WEBP")
        sizes[rel] = p.stat().st_size
    runs = [("f1", 0, 10, "frames/f1.webp", 1), ("f2", 10, 20, "frames/f2.webp", 2),
            ("f3", 20, 30, "frames/f1.webp", 1), ("f4", 30, 40, "frames/f4.webp", 3)]
    frames = [{"id": i, "t_start": s, "t_end": e, "path": p, "bytes": sizes[p], "phash": "0" * 16,
               "matched_slide": None, "slide": k, "source_frames": [i]} for i, s, e, p, k in runs]
    segs = [{"id": f"s{n + 1}", "start": t, "end": t + 5, "text": txt, "frame_id": fid, "speaker": None}
            for n, (t, txt, fid) in enumerate([(1, "first slide words", "f1"), (12, "second slide words", "f2"),
                                               (25, "back on the first", "f3"), (33, "third slide words", "f4")])]
    write_file(base / "transcript.json", json.dumps({"segments": segs}).encode())
    derived = [{"path": "transcript.json", "bytes": (base / "transcript.json").stat().st_size, "kind": "transcript"}] + [
        {"path": p, "bytes": b, "kind": "frame"} for p, b in sizes.items()]
    import hashlib
    m = {"schema_version": "1.0", "asset_id": aid, "kind": "video",
         "original": {"path": f"originals/{aid}/talk.mp4", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
         "metadata": {"title": "Tiny Deck Talk", "author": None, "doc_number": None, "revision": None, "date": None,
                      "language": "en", "duration_seconds": 40.0},
         "segments": segs, "frames": frames, "slides": [], "derived_files": derived,
         "pipeline": {"version": "test", "model": "test", "frame_threshold": 12, "seconds": 1.0,
                      "unique_slides": {"method": "test", "applied_as": "post_pass", "applied_at": None,
                                        "source_frame_count": 4, "unique_slide_count": 3, "run_count": 4,
                                        "source_frame_bytes": sum(sizes.values()), "unique_slide_bytes": sum(sizes.values()),
                                        "overlay_mask": None, "params": {}}}}
    write_file(base / "manifest.json", json.dumps(m).encode())
    ingest.ingest_manifest(aid)
    return aid


def test_timeline_and_detail_show_unique_slides(empty):
    aid = _video_with_unique_slides(empty)
    tl = empty.get(f"/api/assets/{aid}/timeline").json()
    assert [f["slide"] for f in tl["frames"]] == [1, 2, 1, 3]
    d = empty.get(f"/api/assets/{aid}").json()["derived"]
    assert d["unique_slide_count"] == 3 and d["source_frame_count"] == 4 and d["frame_count"] == 4
    assert d["bytes_by_kind"]["frame"] == sum(f["bytes"] for f in {f["image_url"]: f for f in tl["frames"]}.values())
    hits = empty.get("/api/search", params={"q": "tiny deck"}).json()["hits"]
    assert hits and hits[0]["hit_type"] == "asset" and hits[0]["asset_id"] == aid


def test_pptx_has_one_slide_per_unique_slide(empty):
    from pptx import Presentation

    aid = _video_with_unique_slides(empty)
    r = empty.get(f"/api/assets/{aid}/slides.pptx")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxmlformats")
    prs = Presentation(io.BytesIO(r.content))
    slides = list(prs.slides)
    assert len(slides) == 1 + 3  # intro + 3 unique slides (not 4 time ranges)
    notes = [s.notes_slide.notes_text_frame.text for s in slides[1:]]
    assert "00:00:00-00:00:10, 00:00:20-00:00:30" in notes[0]
    assert "first slide words back on the first" in notes[0] and "second slide words" in notes[1]
    assert all(any(sh.shape_type == 13 for sh in s.shapes) for s in slides[1:])  # 13 = picture


def test_pdf_has_one_page_per_unique_slide(empty):
    aid = _video_with_unique_slides(empty)
    r = empty.get(f"/api/assets/{aid}/slides.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF-1.4") and r.content.rstrip().endswith(b"%%EOF")
    assert r.content.count(b"/Type /Page ") == 4 and b"/Count 4" in r.content
    assert r.content.count(b"/Subtype /Image") == 3


def test_derived_route_never_serves_staging(empty):
    write_file(settings.DERIVED_DIR / ".staging" / "a_x-j_1" / "manifest.json", b"{}")
    assert empty.get("/files/derived/.staging/a_x-j_1/manifest.json").status_code == 404


# ---------------------------------------------------------------------------------------------
# safe re-process: the live files stay until the new run succeeded
# ---------------------------------------------------------------------------------------------
FAKE = textwrap.dedent('''
    import argparse, hashlib, json, os, sys, time
    p = argparse.ArgumentParser(); sub = p.add_subparsers(dest="cmd")
    q = sub.add_parser("process")
    for a in ("--asset-id", "--kind", "--input", "--out"): q.add_argument(a, required=True)
    a = p.parse_args()
    mode = os.environ.get("FAKE_MODE", "ok")
    data = open(a.input, "rb").read()
    os.makedirs(os.path.join(a.out, "pages"), exist_ok=True)
    json.dump({"stage": "rendering pages", "progress": 0.5}, open(os.path.join(a.out, "progress.json"), "w"))
    time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
    if mode == "fail":
        json.dump({"message": "simulated failure"}, open(os.path.join(a.out, "error.json"), "w")); sys.exit(4)
    word = os.environ.get("FAKE_WORD", "alpha")
    img = os.path.join(a.out, "pages", "p1.webp"); open(img, "wb").write(word.encode() * 20)
    text = "page about " + word
    m = {"schema_version": "1.0", "asset_id": a.asset_id, "kind": a.kind,
         "original": {"path": "originals/x", "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()},
         "metadata": {"title": None, "author": None, "doc_number": None, "revision": None, "date": None, "language": None},
         "segments": [], "frames": [],
         "slides": [{"id": "p1", "page": 1, "text": text, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
                     "phash": "8f3c1a2b4d5e6f70", "path": "pages/p1.webp", "bytes": os.path.getsize(img)}],
         "derived_files": [{"path": "pages/p1.webp", "bytes": os.path.getsize(img), "kind": "page_image"}],
         "pipeline": {"version": "fake", "model": None, "frame_threshold": None, "seconds": 0.1}}
    if mode == "badmanifest": m["asset_id"] = "a_other"
    json.dump(m, open(os.path.join(a.out, "manifest.json"), "w"))
''')


@pytest.fixture
def fake2(tmp_path, monkeypatch):
    pkg = tmp_path / "dso_pipeline"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "__main__.py").write_text(FAKE)
    monkeypatch.setattr(settings, "PIPELINE_PYTHON", sys.executable)
    monkeypatch.setattr(settings, "PIPELINE_CWD", tmp_path)
    return monkeypatch


def _no_leftovers():
    for root in (settings.DERIVED_DIR / ".staging", settings.DERIVED_DIR / ".trash"):
        assert not root.exists() or not any(root.iterdir()), list(root.iterdir())


def test_reprocess_keeps_old_files_while_running_and_after_failure(empty, fake2):
    a = upload(empty, data=b"%PDF-1.4 v").json()
    aid = a["id"]
    assert wait_job(empty, empty.post(f"/api/assets/{aid}/process").json()["id"])["status"] == "done"
    live = settings.DERIVED_DIR / aid
    img_url = f"/files/derived/{aid}/pages/p1.webp"
    first = empty.get(img_url).content
    mtime = (live / "manifest.json").stat().st_mtime_ns

    # running re-process: the live folder is not touched, images keep loading
    fake2.setenv("FAKE_MODE", "fail")
    fake2.setenv("FAKE_SLEEP", "1.0")
    j = empty.post(f"/api/assets/{aid}/process").json()
    time.sleep(0.5)
    assert empty.get(img_url).content == first
    assert (live / "manifest.json").stat().st_mtime_ns == mtime
    assert empty.get("/api/search", params={"q": "alpha"}).json()["total"] >= 1
    j = wait_job(empty, j["id"])
    assert j["status"] == "failed" and "simulated failure" in j["error"]
    # failure: previous ready data is still there and still served
    assert empty.get(f"/api/assets/{aid}").json()["asset"]["status"] == "ready"
    assert empty.get(img_url).content == first and (live / "manifest.json").stat().st_mtime_ns == mtime
    _no_leftovers()

    # a manifest that does not validate for this asset is rejected BEFORE the swap
    fake2.setenv("FAKE_MODE", "badmanifest")
    fake2.setenv("FAKE_SLEEP", "0")
    j = wait_job(empty, empty.post(f"/api/assets/{aid}/process").json()["id"])
    assert j["status"] == "failed" and empty.get(img_url).content == first
    _no_leftovers()

    # success: swapped in atomically, old folder cleaned up
    fake2.setenv("FAKE_MODE", "ok")
    fake2.setenv("FAKE_WORD", "bravo")
    assert wait_job(empty, empty.post(f"/api/assets/{aid}/process").json()["id"])["status"] == "done"
    assert empty.get(img_url).content == b"bravo" * 20
    assert empty.get("/api/search", params={"q": "bravo"}).json()["total"] >= 1
    assert empty.get("/api/search", params={"q": "alpha"}).json()["total"] == 0
    _no_leftovers()
