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


def test_speaker_labels_in_exports_and_matched_slide_recompute(empty):
    """Speaker labels render in transcript/PPTX exports; video frames link to matching PDF slides."""
    import hashlib
    from pptx import Presentation
    from PIL import Image
    from app import duplicates

    # 1) Ingest a document with one slide (non-uniform phash)
    doc_bytes = b"%PDF-1.4 dummy deck"
    d_asset = upload(empty, "deck.pdf", doc_bytes, owner="anna", src="sharepoint").json()
    did = d_asset["id"]
    dbase = settings.DERIVED_DIR / did
    (dbase / "pages").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (320, 180), (240, 240, 240)).save(dbase / "pages" / "p1.webp", "WEBP")
    pb = (dbase / "pages" / "p1.webp").stat().st_size
    dm = {
        "schema_version": "1.0", "asset_id": did, "kind": "document",
        "original": {"path": f"originals/{did}/deck.pdf", "bytes": len(doc_bytes),
                     "sha256": hashlib.sha256(doc_bytes).hexdigest()},
        "metadata": {"title": "Deck", "author": None, "doc_number": None, "revision": None, "date": None, "language": None},
        "segments": [], "frames": [],
        "slides": [{"id": "p1", "page": 1, "text": "Matching deck slide", "text_sha256": hashlib.sha256(b"matching deck slide").hexdigest(),
                    "phash": "0f0f0f0f0f0f0f0f", "path": "pages/p1.webp", "bytes": pb}],
        "derived_files": [{"path": "pages/p1.webp", "bytes": pb, "kind": "page_image"}],
        "pipeline": {"version": "test", "model": None, "frame_threshold": None, "seconds": 0.1},
    }
    write_file(dbase / "manifest.json", json.dumps(dm).encode())
    ingest.ingest_manifest(did, recompute=False)

    # 2) Ingest a video whose frame shares phash with p1 and whose segments have text speaker labels (no audio files)
    vid_bytes = b"\x00\x00\x00\x18ftypmp42 talk"
    v_asset = upload(empty, "meeting.mp4", vid_bytes, owner="erik", src="ericsson_play").json()
    vid = v_asset["id"]
    vbase = settings.DERIVED_DIR / vid
    (vbase / "frames").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (320, 180), (240, 240, 240)).save(vbase / "frames" / "f1.webp", "WEBP")
    fb = (vbase / "frames" / "f1.webp").stat().st_size
    segs = [
        {"id": "s1", "start": 0.0, "end": 3.0, "text": "Hello from speaker one.", "frame_id": "f1", "speaker": "Speaker 1"},
        {"id": "s2", "start": 3.0, "end": 6.0, "text": "Reply from speaker two.", "frame_id": "f1", "speaker": "Speaker 2"},
        {"id": "s3", "start": 6.0, "end": 9.0, "text": "Follow-up from speaker three.", "frame_id": "f1", "speaker": "Speaker 3"},
    ]
    write_file(vbase / "transcript.json", json.dumps({"segments": segs}).encode())
    vm = {
        "schema_version": "1.0", "asset_id": vid, "kind": "video",
        "original": {"path": f"originals/{vid}/meeting.mp4", "bytes": len(vid_bytes),
                     "sha256": hashlib.sha256(vid_bytes).hexdigest()},
        "metadata": {"title": "Meeting", "author": None, "doc_number": None, "revision": None, "date": None,
                     "language": "en", "duration_seconds": 10.0},
        "segments": segs,
        "frames": [{"id": "f1", "t_start": 0.0, "t_end": 10.0, "path": "frames/f1.webp", "bytes": fb,
                    "phash": "0f0f0f0f0f0f0f0e", "matched_slide": None, "slide": 1, "source_frames": ["f1"]}],
        "slides": [],
        "derived_files": [
            {"path": "transcript.json", "bytes": (vbase / "transcript.json").stat().st_size, "kind": "transcript"},
            {"path": "frames/f1.webp", "bytes": fb, "kind": "frame"},
        ],
        "pipeline": {
            "version": "test", "model": "test", "frame_threshold": 12, "seconds": 0.2,
            "unique_slides": {"method": "test", "applied_as": "post_pass", "applied_at": None,
                              "source_frame_count": 1, "unique_slide_count": 1, "run_count": 1,
                              "source_frame_bytes": fb, "unique_slide_bytes": fb, "overlay_mask": None, "params": {}},
        },
    }
    write_file(vbase / "manifest.json", json.dumps(vm).encode())
    ingest.ingest_manifest(vid)

    # Check matched_slide populated via duplicates.recompute_matches()
    tl = empty.get(f"/api/assets/{vid}/timeline").json()
    assert tl["frames"][0]["matched_slide"] == f"{did}:p1"
    assert [s["speaker"] for s in tl["segments"]] == ["Speaker 1", "Speaker 2", "Speaker 3"]

    # Check no audio derived files tracked (text-only speaker separation)
    detail = empty.get(f"/api/assets/{vid}").json()
    assert detail["derived"]["bytes_by_kind"].get("audio", 0) == 0

    # Check exports include speaker labels
    txt = empty.get(f"/api/assets/{vid}/transcript.txt").text
    assert "Speaker 1: Hello from speaker one." in txt
    assert "Speaker 2: Reply from speaker two." in txt
    assert "Speaker 3: Follow-up from speaker three." in txt
    prs = Presentation(io.BytesIO(empty.get(f"/api/assets/{vid}/slides.pptx").content))
    note = prs.slides[1].notes_slide.notes_text_frame.text
    assert "Speaker 1: Hello from speaker one." in note and "Speaker 3: Follow-up from speaker three." in note

    # Check AI-ready JSON & JSONL exports carry speaker labels on transcript chunks and null on slides
    v_exp = empty.get(f"/api/assets/{vid}/export").json()
    assert [c["speaker"] for c in v_exp["chunks"]] == ["Speaker 1", "Speaker 2", "Speaker 3"]
    d_exp = empty.get(f"/api/assets/{did}/export").json()
    assert [c["speaker"] for c in d_exp["chunks"]] == [None]
    jsonl_chunks = {c["chunk_id"]: c for c in (json.loads(x) for x in empty.get("/api/export.jsonl").text.splitlines() if x.strip())}
    assert jsonl_chunks[f"{vid}:s1"]["speaker"] == "Speaker 1"
    assert jsonl_chunks[f"{vid}:s2"]["speaker"] == "Speaker 2"
    assert jsonl_chunks[f"{did}:p1"]["speaker"] is None


def _validate_api_schema(checks: list[tuple[str, object]]) -> None:
    """Validate `(defname, payload)` pairs against api.schema.json using Draft202012Validator."""
    script = textwrap.dedent("""
        import json, sys
        from pathlib import Path
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource

        contracts = Path(sys.argv[1])
        man = json.loads((contracts / "schemas/manifest.schema.json").read_text(encoding="utf-8"))
        api = json.loads((contracts / "schemas/api.schema.json").read_text(encoding="utf-8"))
        reg = Registry().with_resources([
            (man["$id"], Resource.from_contents(man)),
            ("manifest.schema.json", Resource.from_contents(man)),
            (api["$id"], Resource.from_contents(api)),
        ])
        for defname, payload in json.load(sys.stdin):
            v = Draft202012Validator({"$ref": f"{api['$id']}#/$defs/{defname}"}, registry=reg)
            errs = list(v.iter_errors(payload))
            assert not errs, f"{defname}: {errs[0].message}"
    """)
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
    except ImportError:
        import subprocess
        from pathlib import Path

        py = Path(settings.PIPELINE_PYTHON)
        assert py.is_file(), f"jsonschema missing and pipeline python not found at {py}"
        proc = subprocess.run(
            [str(py), "-c", script, str(settings.CONTRACTS_DIR)],
            input=json.dumps(checks),
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0, f"JSON Schema validation failed:\n{proc.stderr}\n{proc.stdout}"
        return

    man = json.loads((settings.CONTRACTS_DIR / "schemas/manifest.schema.json").read_text(encoding="utf-8"))
    api = json.loads((settings.CONTRACTS_DIR / "schemas/api.schema.json").read_text(encoding="utf-8"))
    reg = Registry().with_resources([
        (man["$id"], Resource.from_contents(man)),
        ("manifest.schema.json", Resource.from_contents(man)),
        (api["$id"], Resource.from_contents(api)),
    ])
    for defname, payload in checks:
        errs = list(Draft202012Validator({"$ref": f"{api['$id']}#/$defs/{defname}"}, registry=reg).iter_errors(payload))
        assert not errs, f"{defname}: {errs[0].message}"


def test_rich_diarization_export_roundtrip_and_fallbacks(empty):
    """Rich transcript.json diarization, overlap, and null-confidence round-trip + legacy/missing graceful fallbacks."""
    import hashlib
    from PIL import Image
    from dso_contracts.models import ExportAsset, ExportChunk

    # 1) Document asset (slide_text chunks must remain null for all speaker/diarization fields)
    doc_bytes = b"%PDF-1.4 slides"
    did = upload(empty, "slides.pdf", doc_bytes, owner="anna", src="sharepoint").json()["id"]
    dbase = settings.DERIVED_DIR / did
    (dbase / "pages").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (320, 180), (220, 220, 220)).save(dbase / "pages" / "p1.webp", "WEBP")
    pb = (dbase / "pages" / "p1.webp").stat().st_size
    dm = {
        "schema_version": "1.0", "asset_id": did, "kind": "document",
        "original": {"path": f"originals/{did}/slides.pdf", "bytes": len(doc_bytes),
                     "sha256": hashlib.sha256(doc_bytes).hexdigest()},
        "metadata": {"title": "Slides", "author": None, "doc_number": None, "revision": None, "date": None, "language": None},
        "segments": [], "frames": [],
        "slides": [{"id": "p1", "page": 1, "text": "Slide one text",
                    "text_sha256": hashlib.sha256(b"slide one text").hexdigest(),
                    "phash": "1111222233334444", "path": "pages/p1.webp", "bytes": pb}],
        "derived_files": [{"path": "pages/p1.webp", "bytes": pb, "kind": "page_image"}],
        "pipeline": {"version": "test", "model": None, "frame_threshold": None, "seconds": 0.1, "warnings": []},
    }
    write_file(dbase / "manifest.json", json.dumps(dm).encode())
    ingest.ingest_manifest(did, recompute=False)

    # 2) Video with rich neural diarization metadata: PRESENTER, DOCUMENTARY, UNKNOWN, overlap, and null confidence
    vid_bytes = b"\x00\x00\x00\x18ftypmp42 rich-diar"
    vid = upload(empty, "keynote.mp4", vid_bytes, owner="erik", src="ericsson_play").json()["id"]
    vbase = settings.DERIVED_DIR / vid
    (vbase / "frames").mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (320, 180), (40, 80, 120)).save(vbase / "frames" / "f1.webp", "WEBP")
    fb = (vbase / "frames" / "f1.webp").stat().st_size
    segs = [
        {"id": "s1", "start": 0.0, "end": 4.0, "text": "Welcome to the keynote.",
         "frame_id": "f1", "speaker": "Speaker 1 (Presenter)"},
        {"id": "s2", "start": 4.0, "end": 8.0, "text": "Video clip narrator line.",
         "frame_id": "f1", "speaker": "Speaker 2 (Documentary)"},
        {"id": "s3", "start": 8.0, "end": 11.5, "text": "Overlapping discussion turn.",
         "frame_id": "f1", "speaker": "Speaker 1 + Speaker 2 (Overlap)"},
        {"id": "s4", "start": 11.5, "end": 12.0, "text": "Quick question.",
         "frame_id": "f1", "speaker": "Speaker 3 (Unknown)"},
    ]
    speakers_meta = [
        {
            "speaker": "Speaker 1 (Presenter)",
            "speaker_id": "Speaker 1",
            "role": "PRESENTER",
            "segment_count": 2,
            "seconds_spoken": 7.5,
            "video_churn_ratio": 0.125,
            "overlap_seconds": 1.2,
            "overlap_segment_count": 1,
            "role_cues": {
                "static_seconds": 6.5, "video_seconds": 1.0,
                "static_blocks": 2, "static_share": 0.72, "active_span_seconds": 11.5,
            },
        },
        {
            "speaker": "Speaker 2 (Documentary)",
            "speaker_id": "Speaker 2",
            "role": "DOCUMENTARY",
            "segment_count": 1,
            "seconds_spoken": 4.0,
            "video_churn_ratio": 0.95,
            "overlap_seconds": 0.0,
            "overlap_segment_count": 0,
            "role_cues": {
                "static_seconds": 0.2, "video_seconds": 3.8,
                "static_blocks": 0, "static_share": 0.02, "active_span_seconds": 4.0,
            },
        },
        {
            "speaker": "Speaker 3 (Unknown)",
            "speaker_id": "Speaker 3",
            "role": "UNKNOWN",
            "segment_count": 1,
            "seconds_spoken": 0.5,
            "video_churn_ratio": 0.0,
            "overlap_seconds": 0.0,
            "overlap_segment_count": 0,
            "role_cues": {
                "static_seconds": 0.5, "video_seconds": 0.0,
                "static_blocks": 1, "static_share": 0.05, "active_span_seconds": 0.5,
            },
        },
    ]
    diar_meta = [
        {
            "segment_id": "s1", "speaker_id": "Speaker 1", "speaker_category": "PRESENTER",
            "speaker_confidence": 0.8412, "overlap": False, "overlap_seconds": 0.0,
            "overlap_ratio": 0.0, "overlap_speakers": [],
            "sub_turns": [{"start": 0.0, "end": 4.0, "speaker_id": "Speaker 1", "role": "PRESENTER", "overlap": False}],
        },
        {
            "segment_id": "s2", "speaker_id": "Speaker 2", "speaker_category": "DOCUMENTARY",
            "speaker_confidence": 0.625, "overlap": False, "overlap_seconds": 0.0,
            "overlap_ratio": 0.0, "overlap_speakers": [],
            "sub_turns": [{"start": 4.0, "end": 8.0, "speaker_id": "Speaker 2", "role": "DOCUMENTARY", "overlap": False}],
        },
        {
            "segment_id": "s3", "speaker_id": "Speaker 1", "speaker_category": "PRESENTER",
            "speaker_confidence": 0.41, "overlap": True, "overlap_seconds": 1.2,
            "overlap_ratio": 0.3429, "overlap_speakers": ["Speaker 1", "Speaker 2"],
            "sub_turns": [
                {"start": 8.0, "end": 9.8, "speaker_id": "Speaker 1", "role": "PRESENTER", "overlap": True},
                {"start": 9.8, "end": 11.5, "speaker_id": "Speaker 2", "role": "DOCUMENTARY", "overlap": True},
            ],
        },
        {
            "segment_id": "s4", "speaker_id": "Speaker 3", "speaker_category": "UNKNOWN",
            "speaker_confidence": None, "overlap": False, "overlap_seconds": 0.0,
            "overlap_ratio": 0.0, "overlap_speakers": [],
            "sub_turns": [{"start": 11.5, "end": 12.0, "speaker_id": "Speaker 3", "role": "UNKNOWN", "overlap": False}],
        },
    ]
    write_file(
        vbase / "transcript.json",
        json.dumps({"segments": segs, "speakers": speakers_meta, "diarization": diar_meta}).encode(),
    )
    vm = {
        "schema_version": "1.0", "asset_id": vid, "kind": "video",
        "original": {"path": f"originals/{vid}/keynote.mp4", "bytes": len(vid_bytes),
                     "sha256": hashlib.sha256(vid_bytes).hexdigest()},
        "metadata": {"title": "Keynote", "author": None, "doc_number": None, "revision": None, "date": None,
                     "language": "en", "duration_seconds": 12.0},
        "segments": segs,
        "frames": [{"id": "f1", "t_start": 0.0, "t_end": 12.0, "path": "frames/f1.webp", "bytes": fb,
                    "phash": "aaaa1111bbbb2222", "matched_slide": None}],
        "slides": [],
        "derived_files": [
            {"path": "transcript.json", "bytes": (vbase / "transcript.json").stat().st_size, "kind": "transcript"},
            {"path": "frames/f1.webp", "bytes": fb, "kind": "frame"},
        ],
        "pipeline": {"version": "test", "model": "test", "frame_threshold": 12, "seconds": 0.2, "warnings": []},
    }
    write_file(vbase / "manifest.json", json.dumps(vm).encode())
    ingest.ingest_manifest(vid, recompute=False)

    # 3) Verify /api/assets/{id}/export for video and document
    v_exp = empty.get(f"/api/assets/{vid}/export").json()
    d_exp = empty.get(f"/api/assets/{did}/export").json()
    ExportAsset.model_validate(v_exp)
    ExportAsset.model_validate(d_exp)

    assert v_exp["speakers"] == speakers_meta
    assert d_exp["speakers"] is None

    by_cid = {c["chunk_id"]: c for c in v_exp["chunks"]}
    assert by_cid[f"{vid}:s1"]["speaker_id"] == "Speaker 1"
    assert by_cid[f"{vid}:s1"]["speaker_category"] == "PRESENTER"
    assert by_cid[f"{vid}:s1"]["speaker_confidence"] == pytest.approx(0.8412)
    assert by_cid[f"{vid}:s1"]["overlap"] is False
    assert by_cid[f"{vid}:s1"]["overlap_speakers"] == []

    assert by_cid[f"{vid}:s2"]["speaker_id"] == "Speaker 2"
    assert by_cid[f"{vid}:s2"]["speaker_category"] == "DOCUMENTARY"
    assert by_cid[f"{vid}:s2"]["speaker_confidence"] == pytest.approx(0.625)

    assert by_cid[f"{vid}:s3"]["overlap"] is True
    assert by_cid[f"{vid}:s3"]["overlap_speakers"] == ["Speaker 1", "Speaker 2"]

    # Null confidence must stay null — never fabricated
    assert by_cid[f"{vid}:s4"]["speaker_id"] == "Speaker 3"
    assert by_cid[f"{vid}:s4"]["speaker_category"] == "UNKNOWN"
    assert by_cid[f"{vid}:s4"]["speaker_confidence"] is None
    assert by_cid[f"{vid}:s4"]["overlap"] is False

    # Slide chunks stay null for all speaker/diarization fields
    doc_chunk = d_exp["chunks"][0]
    for k in ("speaker", "speaker_id", "speaker_category", "speaker_confidence", "overlap", "overlap_speakers"):
        assert doc_chunk[k] is None

    # 4) Verify /api/export.jsonl round-trip + Pydantic + JSON Schema validation
    jsonl_resp = empty.get("/api/export.jsonl")
    assert jsonl_resp.status_code == 200
    jsonl_lines = [json.loads(ln) for ln in jsonl_resp.text.splitlines() if ln.strip()]
    for ln in jsonl_lines:
        ExportChunk.model_validate(ln)
    j_by_cid = {ln["chunk_id"]: ln for ln in jsonl_lines}
    assert j_by_cid[f"{vid}:s3"]["overlap"] is True
    assert j_by_cid[f"{vid}:s3"]["overlap_speakers"] == ["Speaker 1", "Speaker 2"]
    assert j_by_cid[f"{vid}:s4"]["speaker_confidence"] is None
    assert j_by_cid[f"{did}:p1"]["speaker_id"] is None

    schema_checks: list[tuple[str, object]] = [("ExportAsset", v_exp), ("ExportAsset", d_exp)] + [
        ("ExportChunk", ln) for ln in jsonl_lines
    ]

    # 5) Legacy transcript.json (with extra legacy keys and no diarization[]) and missing/corrupt transcript.json
    write_file(
        vbase / "transcript.json",
        json.dumps({
            "segments": segs,
            "speakers": [{"speaker": "Speaker 1", "path": "audio/speaker-1.wav", "bytes": 123,
                          "kind": "audio", "clip_start": 0.0, "clip_end": 4.0,
                          "segment_count": 2, "seconds_spoken": 7.5}],
        }).encode(),
    )
    legacy_exp = empty.get(f"/api/assets/{vid}/export").json()
    ExportAsset.model_validate(legacy_exp)
    assert legacy_exp["speakers"] == [{
        "speaker": "Speaker 1", "speaker_id": None, "role": None,
        "segment_count": 2, "seconds_spoken": 7.5,
        "video_churn_ratio": None, "overlap_seconds": None,
        "overlap_segment_count": None, "role_cues": None,
    }]
    for c in legacy_exp["chunks"]:
        for k in ("speaker_id", "speaker_category", "speaker_confidence", "overlap", "overlap_speakers"):
            assert c[k] is None

    (vbase / "transcript.json").unlink()
    missing_exp = empty.get(f"/api/assets/{vid}/export").json()
    ExportAsset.model_validate(missing_exp)
    assert missing_exp["speakers"] is None
    for c in missing_exp["chunks"]:
        for k in ("speaker_id", "speaker_category", "speaker_confidence", "overlap", "overlap_speakers"):
            assert c[k] is None

    write_file(vbase / "transcript.json", b"{not valid json")
    corrupt_exp = empty.get(f"/api/assets/{vid}/export").json()
    ExportAsset.model_validate(corrupt_exp)
    assert corrupt_exp["speakers"] is None

    schema_checks.extend([
        ("ExportAsset", legacy_exp),
        ("ExportAsset", missing_exp),
        ("ExportAsset", corrupt_exp),
    ])
    _validate_api_schema(schema_checks)
