"""Generate coherent mock fixtures in contracts/fixtures/ from ONE small fake dataset.

Fixture generator only (not product code). Stream 1 builds UI on these files; Stream 2 can ingest
fixtures/manifests/*.json if Stream 3 slips. The storage-report part is a REFERENCE calculation of the
frozen savings formula (see CONTRACTS.md) that Stream 2 may copy into a unit test.

Run:  python contracts/scripts/make_fixtures.py   (stdlib only)
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "fixtures"
NOW = "2026-11-13T10:00:00Z"
FORMULA = "Savings % = (O − A) / O × 100"


def sha(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


def ph(s: str) -> str:
    return sha("phash" + s)[:16]


def norm_sha(text: str) -> str:
    import unicodedata
    t = " ".join(unicodedata.normalize("NFKC", text).lower().split())
    return hashlib.sha256(t.encode()).hexdigest()


def dump(name: str, obj) -> int:
    p = FIX / name
    p.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(obj, indent=2, ensure_ascii=False) + "\n"
    p.write_text(data, encoding="utf-8")
    return len(data.encode("utf-8"))


EMPTY_META = {"title": None, "author": None, "doc_number": None, "revision": None, "date": None, "language": None}

# ---- fake library (simulated source systems) --------------------------------------------
DECK_SHA = sha("ran-deck-bytes")
ASSETS = [
    dict(id="a_01", filename="event-recording.mp4", kind="video", bytes=734_003_200, sha256=sha("video-bytes"),
         source_system="ericsson_play", owner="anna", status="ready", created_at="2026-11-13T08:00:00Z"),
    dict(id="a_02", filename="ran-deck.pdf", kind="document", bytes=2_400_000, sha256=DECK_SHA,
         source_system="sharepoint", owner="bjorn", status="ready", created_at="2026-11-13T08:01:00Z"),
    dict(id="a_03", filename="ran-deck (1).pdf", kind="document", bytes=2_400_000, sha256=DECK_SHA,
         source_system="onedrive", owner="carl", status="ready", created_at="2026-11-13T08:02:00Z"),
    dict(id="a_04", filename="5g-overview.pdf", kind="document", bytes=1_850_000, sha256=sha("5g-bytes"),
         source_system="onedrive", owner="carl", status="ready", created_at="2026-11-13T08:03:00Z"),
    dict(id="a_05", filename="carl-notes.pdf", kind="document", bytes=310_000, sha256=sha("notes-bytes"),
         source_system="onedrive", owner="carl", status="uploaded", created_at="2026-11-13T08:04:00Z"),
]
BY_ID = {a["id"]: a for a in ASSETS}
for a in ASSETS:
    a["source_simulated"] = True
    a["original_url"] = f"/files/originals/{a['id']}/{a['filename']}"

DECK_PAGES = [
    "RAN Evolution Roadmap 2027",
    "Handover optimisation: fewer dropped calls in dense cells",
    "Energy saving: sleep modes for idle radio units",
    "Results: 12% lower power per site in field trial",
]
FIVEG_PAGES = [
    "Handover optimisation: fewer dropped calls in dense cells",   # shared with ran-deck p2
    "Energy saving: sleep modes for idle radio units",            # shared with ran-deck p3
    "Results: 14% lower power per site in field trial",           # similar to ran-deck p4 (revision)
]


def doc_manifest(aid: str, pages: list[str], meta: dict) -> dict:
    a = BY_ID[aid]
    slides, derived = [], []
    for i, text in enumerate(pages, start=1):
        b = 58_000 + 1_000 * i
        slides.append({"id": f"p{i}", "page": i, "text": text, "text_sha256": norm_sha(text),
                       "phash": ph(text if "lower power" not in text else "results-page" + aid[-1]),
                       "path": f"pages/p{i}.webp", "bytes": b})
        derived.append({"path": f"pages/p{i}.webp", "bytes": b, "kind": "page_image"})
    return {"schema_version": "1.0", "asset_id": aid, "kind": "document",
            "original": {"path": f"originals/{aid}/{a['filename']}", "bytes": a["bytes"], "sha256": a["sha256"]},
            "metadata": meta, "segments": [], "frames": [], "slides": slides, "derived_files": derived,
            "pipeline": {"version": "0.1", "model": None, "frame_threshold": None, "seconds": 1.8, "warnings": []}}


def video_manifest() -> dict:
    a = BY_ID["a_01"]
    frames = [
        {"id": "f1", "t_start": 0.0, "t_end": 95.0, "path": "frames/f1.webp", "bytes": 41_200, "phash": ph("f1"), "matched_slide": None},
        {"id": "f2", "t_start": 95.0, "t_end": 410.0, "path": "frames/f2.webp", "bytes": 48_211, "phash": ph("f2"), "matched_slide": None},
        {"id": "f3", "t_start": 410.0, "t_end": 1220.0, "path": "frames/f3.webp", "bytes": 52_900, "phash": ph("f3"), "matched_slide": None},
        {"id": "f4", "t_start": 1220.0, "t_end": 1800.0, "path": "frames/f4.webp", "bytes": 47_050, "phash": ph("f4"), "matched_slide": None},
    ]
    segs = [
        (0.0, 6.5, "Welcome everyone to the RAN evolution session.", "f1"),
        (96.2, 104.8, "As you see here, handover optimisation reduces dropped calls in dense cells.", "f2"),
        (104.8, 112.0, "We tested this in three cities last spring.", "f2"),
        (412.3, 420.1, "The next topic is energy saving with sleep modes for idle radio units.", "f3"),
        (1221.0, 1230.4, "In the field trial we measured twelve percent lower power per site.", "f4"),
    ]
    segments = [{"id": f"s{i}", "start": s, "end": e, "text": t, "frame_id": f, "speaker": None}
                for i, (s, e, t, f) in enumerate(segs, start=1)]
    derived = [{"path": "transcript.json", "bytes": 51_200, "kind": "transcript"}] + \
              [{"path": f["path"], "bytes": f["bytes"], "kind": "frame"} for f in frames]
    meta = dict(EMPTY_META, title="RAN evolution session", language="en", duration_seconds=1800.0)
    return {"schema_version": "1.0", "asset_id": "a_01", "kind": "video",
            "original": {"path": f"originals/a_01/{a['filename']}", "bytes": a["bytes"], "sha256": a["sha256"]},
            "metadata": meta, "segments": segments, "frames": frames, "slides": [], "derived_files": derived,
            "pipeline": {"version": "0.1", "model": "faster-whisper small int8", "frame_threshold": 12, "seconds": 640.0, "warnings": []}}


deck_meta = dict(EMPTY_META, title="RAN Evolution Roadmap", author="B. Berg", doc_number="1/221 02-FGB 101", revision="A", date="2026-09-30")
MANIFESTS = {
    "a_01": video_manifest(),
    "a_02": doc_manifest("a_02", DECK_PAGES, deck_meta),
    "a_03": doc_manifest("a_03", DECK_PAGES, deck_meta),
    "a_04": doc_manifest("a_04", FIVEG_PAGES, dict(EMPTY_META, title="5G overview", revision="B")),
}
MANIFEST_BYTES = {aid: dump(f"manifests/{aid}.manifest.json", m) for aid, m in MANIFESTS.items()}


def derived_bytes(aid: str) -> int:
    if aid not in MANIFESTS:
        return 0
    return sum(f["bytes"] for f in MANIFESTS[aid]["derived_files"]) + MANIFEST_BYTES[aid]


def asset_row(aid: str) -> dict:
    a = dict(BY_ID[aid])
    a["derived_bytes"] = derived_bytes(aid)
    keys = ["id", "filename", "kind", "bytes", "sha256", "source_system", "source_simulated", "owner",
            "status", "created_at", "derived_bytes", "original_url"]
    return {**{k: a[k] for k in keys}, "test_data": False}  # REC v1.1


def furl(aid: str, path: str) -> str:
    return f"/files/derived/{aid}/{path}"


# ---- simple API fixtures --------------------------------------------------------------------
dump("health.json", {"status": "ok", "version": "1.0.0"})
dump("assets.json", {"assets": [asset_row(a["id"]) for a in ASSETS]})
dump("asset_upload_response.json", asset_row("a_05"))
JOB = {"id": "j_01", "asset_id": "a_01", "status": "done", "progress": 1.0, "stage": "done", "error": None,
       "started_at": "2026-11-13T08:05:00Z", "finished_at": "2026-11-13T08:15:40Z"}
dump("job.json", JOB)
dump("job_running.json", {"id": "j_02", "asset_id": "a_05", "status": "running", "progress": 0.4,
                          "stage": "rendering pages", "error": None, "started_at": "2026-11-13T10:00:00Z", "finished_at": None})
dump("error.json", {"error": {"code": "not_found", "message": "Asset a_99 was not found.", "details": None}})


def summary(aid: str) -> dict:
    m = MANIFESTS[aid]
    by_kind: dict[str, int] = {}
    for f in m["derived_files"]:
        by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + f["bytes"]
    by_kind["manifest"] = MANIFEST_BYTES[aid]
    return {"derived_bytes": derived_bytes(aid), "manifest_bytes": MANIFEST_BYTES[aid],
            "file_count": len(m["derived_files"]) + 1, "segment_count": len(m["segments"]),
            "frame_count": len(m["frames"]), "slide_count": len(m["slides"]), "bytes_by_kind": by_kind,
            "unique_slide_count": None, "source_frame_count": None}  # REC v1.1: unique-slide pass not run on fixtures


dump("asset_detail_video.json", {"asset": asset_row("a_01"), "metadata": MANIFESTS["a_01"]["metadata"],
                                 "derived": summary("a_01"), "pipeline": {**MANIFESTS["a_01"]["pipeline"], "unique_slides": None}, "latest_job": JOB})
dump("asset_detail_document.json", {"asset": asset_row("a_02"), "metadata": MANIFESTS["a_02"]["metadata"],
                                    "derived": summary("a_02"), "pipeline": {**MANIFESTS["a_02"]["pipeline"], "unique_slides": None}, "latest_job": None})


def frame_view(aid: str, f: dict) -> dict:
    return {"id": f["id"], "t_start": f["t_start"], "t_end": f["t_end"], "image_url": furl(aid, f["path"]),
            "bytes": f["bytes"], "phash": f["phash"], "matched_slide": f["matched_slide"], "slide": None}


vm = MANIFESTS["a_01"]
dump("timeline.json", {"asset_id": "a_01", "language": "en", "duration_seconds": 1800.0,
                       "original_url": BY_ID["a_01"]["original_url"], "segments": vm["segments"],
                       "frames": [frame_view("a_01", f) for f in vm["frames"]]})

# ---- duplicates (slide matches use the kept copy a_02 as representative of exact group a_02/a_03)
SLIDE_MATCHES = [  # (a_ref, b_ref, type, method, score, evidence)
    ("a_02:p2", "a_04:p1", "shared", "text_sha256+phash", 1.0, {"phash_distance": 0}),
    ("a_02:p3", "a_04:p2", "shared", "text_sha256+phash", 1.0, {"phash_distance": 1}),
    ("a_02:p4", "a_04:p3", "similar", "text_ratio", 0.96, {"phash_distance": 6, "text_similarity": 0.96}),
]


def slide_of(ref: str) -> dict:
    aid, sid = ref.split(":")
    return next(s for s in MANIFESTS[aid]["slides"] if s["id"] == sid)


def member(aid: str, sid: str | None = None) -> dict:
    a = BY_ID[aid]
    s = slide_of(f"{aid}:{sid}") if sid else None
    return {"asset_id": aid, "filename": a["filename"], "source_system": a["source_system"], "owner": a["owner"],
            "bytes": a["bytes"], "slide_id": sid, "page": s["page"] if s else None,
            "image_url": furl(aid, s["path"]) if s else None}


groups = [{"id": "g_exact_1", "type": "exact_file", "needs_review": False, "score": 1.0,
           "evidence": {"method": "sha256", "sha256": DECK_SHA, "text_sha256": None, "phash_distance": None, "text_similarity": None},
           "members": [member("a_02"), member("a_03")]}]
for i, (ra, rb, typ, method, score, ev) in enumerate(SLIDE_MATCHES, start=1):
    sa = slide_of(ra)
    groups.append({"id": f"g_slide_{i}", "type": f"{typ}_slide", "needs_review": typ == "similar", "score": score,
                   "evidence": {"method": method, "sha256": None,
                                "text_sha256": sa["text_sha256"] if typ == "shared" else None,
                                "phash_distance": ev.get("phash_distance"), "text_similarity": ev.get("text_similarity")},
                   "members": [member(*ra.split(":")), member(*rb.split(":"))]})
dump("duplicates.json", {"groups": groups, "counts": {
    t: sum(g["type"] == t for g in groups) for t in ("exact_file", "shared_slide", "similar_slide")}})


def slide_views(aid: str) -> list[dict]:
    out = []
    for s in MANIFESTS[aid]["slides"]:
        ref = f"{aid}:{s['id']}"
        matches = []
        for ra, rb, typ, method, score, _ in SLIDE_MATCHES:
            if ref in (ra, rb):
                other = rb if ref == ra else ra
                oaid, osid = other.split(":")
                matches.append({"type": typ, "other_asset_id": oaid, "other_slide_id": osid,
                                "other_filename": BY_ID[oaid]["filename"], "other_page": slide_of(other)["page"],
                                "other_source_system": BY_ID[oaid]["source_system"], "score": score, "method": method})
        out.append({"id": s["id"], "page": s["page"], "text": s["text"],
                    "hashes": {"file_sha256": BY_ID[aid]["sha256"], "text_sha256": s["text_sha256"], "phash": s["phash"]},
                    "image_url": furl(aid, s["path"]), "bytes": s["bytes"], "matches": matches})
    return out


dump("slides.json", {"asset_id": "a_02", "metadata": MANIFESTS["a_02"]["metadata"], "slides": slide_views("a_02")})

# ---- search ---------------------------------------------------------------------------------
seg = vm["segments"][1]
fr = next(f for f in vm["frames"] if f["id"] == seg["frame_id"])
sl = slide_of("a_02:p2")
dump("search.json", {"query": "handover", "total": 2, "hits": [
    {"hit_type": "segment", "asset_id": "a_01", "filename": "event-recording.mp4", "kind": "video",
     "source_system": "ericsson_play", "owner": "anna", "text": seg["text"],
     "snippet": "As you see here, <mark>handover</mark> optimisation reduces dropped calls…",
     "start": seg["start"], "end": seg["end"], "page": None, "item_id": seg["id"], "frame_id": fr["id"],
     "media": {"type": "frame", "asset_id": "a_01", "item_id": fr["id"], "url": furl("a_01", fr["path"]),
               "bytes": fr["bytes"], "t_start": fr["t_start"], "t_end": fr["t_end"], "page": None},
     "score": 7.1},
    {"hit_type": "slide", "asset_id": "a_02", "filename": "ran-deck.pdf", "kind": "document",
     "source_system": "sharepoint", "owner": "bjorn", "text": sl["text"],
     "snippet": "<mark>Handover</mark> optimisation: fewer dropped calls in dense cells",
     "start": None, "end": None, "page": sl["page"], "item_id": sl["id"], "frame_id": None,
     "media": {"type": "slide", "asset_id": "a_02", "item_id": sl["id"], "url": furl("a_02", sl["path"]),
               "bytes": sl["bytes"], "t_start": None, "t_end": None, "page": sl["page"]},
     "score": 6.4},
]})

# ---- offboarding (leaver = carl). Eligible only if an exact copy exists owned by someone else.
def off_row(aid: str) -> dict:
    a = BY_ID[aid]
    dups = [b for b in ASSETS if b["sha256"] == a["sha256"] and b["id"] != aid and b["owner"] != a["owner"]]
    locs = [{"asset_id": b["id"], "filename": b["filename"], "source_system": b["source_system"], "owner": b["owner"]} for b in dups]
    if dups:
        b = dups[0]
        rec, reason = "eligible_after_approval", f"Confirmed exact duplicate (same SHA-256) at {b['source_system']}: {b['filename']} (owner: {b['owner']})"
    else:
        rec, reason = "keep", "No exact copy owned by someone else. Shared or similar slides do not count."
    return {"asset_id": aid, "filename": a["filename"], "kind": a["kind"], "bytes": a["bytes"],
            "source_system": a["source_system"], "recommendation": rec, "reason": reason, "duplicates_elsewhere": locs}


rows = [off_row(a["id"]) for a in ASSETS if a["owner"] == "carl"]
dump("offboarding.json", {"owner": "carl", "generated_at": NOW, "deletes_performed": False, "rows": rows, "summary": {
    "total": len(rows), "eligible": sum(r["recommendation"] == "eligible_after_approval" for r in rows),
    "keep": sum(r["recommendation"] == "keep" for r in rows),
    "eligible_bytes": sum(r["bytes"] for r in rows if r["recommendation"] == "eligible_after_approval")}})

# ---- storage report: REFERENCE implementation of the frozen formula ------------------------
INDEX_BYTES = 1_228_800  # fixture value; backend measures the real SQLite file size
O = sum(a["bytes"] for a in ASSETS)
D = sum(derived_bytes(a["id"]) for a in ASSETS)
ready_videos = [a for a in ASSETS if a["kind"] == "video" and a["status"] == "ready"]
groups_by_sha: dict[str, list[dict]] = {}
for a in sorted(ASSETS, key=lambda x: (x["created_at"], x["id"])):
    groups_by_sha.setdefault(a["sha256"], []).append(a)
extra_copies = [(c, g[0]["id"]) for g in groups_by_sha.values() for c in g[1:]]


def scenario(sid: int, key: str, label: str, desc: str, formula: str, removed: list[dict]) -> dict:
    removed_bytes = sum(r["bytes"] for r in removed)
    kept = O - removed_bytes
    A = kept + D + INDEX_BYTES
    return {"id": sid, "key": key, "label": label, "description": desc, "hypothetical": sid != 0,
            "formula": formula, "before_bytes": O, "after_bytes": A, "saved_bytes": O - A,
            "savings_pct": round((O - A) / O * 100, 4) if O else None,
            "kept_original_bytes": kept, "derived_bytes": D, "index_bytes": INDEX_BYTES, "removed": removed}


def rem(a: dict, reason: str, kept: str | None = None) -> dict:
    return {"asset_id": a["id"], "filename": a["filename"], "bytes": a["bytes"], "reason": reason, "kept_copy_asset_id": kept}


s1 = [rem(a, "replaced_by_derived") for a in ready_videos]
s2 = [rem(c, "exact_duplicate", k) for c, k in extra_copies]
s3, seen = [], set()
for r in s2 + s1:  # each file counted once
    if r["asset_id"] not in seen:
        seen.add(r["asset_id"]); s3.append(r)
dump("storage_report.json", {
    "generated_at": NOW, "formula": FORMULA,
    "totals": {"asset_count": len(ASSETS), "original_bytes": O,
               "video_original_bytes": sum(a["bytes"] for a in ASSETS if a["kind"] == "video"),
               "document_original_bytes": sum(a["bytes"] for a in ASSETS if a["kind"] == "document"),
               "derived_bytes": D, "index_bytes": INDEX_BYTES,
               "extra_exact_copy_bytes": sum(c["bytes"] for c, _ in extra_copies)},
    "scenarios": [
        scenario(0, "today", "Scenario 0: today, real", "Nothing deleted. Derived data and the index are added on top of the originals, so the saving is negative.", "A = O + D + I", []),
        scenario(1, "replace_videos", "Scenario 1: replace videos", "If an approved process replaced each processed recording by its derived data.", "A = (O − processed video originals) + D + I", s1),
        scenario(2, "remove_exact_duplicates", "Scenario 2: remove exact duplicates", "Keep one copy per SHA-256 group (the earliest upload). Shared or similar slides free nothing, because the files differ.", "A = (O − extra exact copies) + D + I", s2),
        scenario(3, "both", "Scenario 3: both", "Scenarios 1 and 2 together, each file counted once.", "A = (O − processed video originals − extra exact copies, no double counting) + D + I", s3),
    ],
    "not_counted": ["Backups", "Platform replication", "Archive tiers", "Compute cost", "Model weights", "Money"],
    "information_lost": ["Motion and live demos in video", "Gestures and body language", "Tone of voice (unless the optional audio track is kept)", "Speaker identity (not in MVP)"],
    "scope": "real_files",
    "excluded_test_data": {"asset_count": 0, "original_bytes": 0, "derived_bytes": 0, "asset_ids": []},
    "notes": ["Scope: real uploaded files only (no generated test files in the library).",
              "O = all original bytes in scope, every copy on every simulated system. D = all derived files + manifests. I = measured SQLite/FTS index size.",
              "D and I are counted in every scenario (conservative).",
              "Scenarios 1-3 are hypothetical and require human approval. The tool never deletes anything.",
              "Ericsson's own example (PDF p.2: ~1 GB → ~50 KB text + ~2 MB frames, 'roughly 99%') is their illustration, not our measurement."],
})

# ---- export ---------------------------------------------------------------------------------
def prov(aid: str) -> dict:
    a = BY_ID[aid]
    return {k: a[k] for k in ("filename", "sha256", "source_system", "source_simulated", "owner", "original_url")} | {"asset_id": aid}


def chunks(aid: str) -> list[dict]:
    m = MANIFESTS[aid]
    out = []
    for s in m["segments"]:
        f = next((x for x in m["frames"] if x["id"] == s["frame_id"]), None)
        out.append({"schema_version": "1.0", "chunk_id": f"{aid}:{s['id']}", "kind": "transcript_segment", "text": s["text"],
                    "start": s["start"], "end": s["end"], "page": None, "frame_id": s["frame_id"], "slide_id": None,
                    "image_url": furl(aid, f["path"]) if f else None, "language": m["metadata"]["language"],
                    "metadata": m["metadata"], "source": prov(aid)})
    for s in m["slides"]:
        out.append({"schema_version": "1.0", "chunk_id": f"{aid}:{s['id']}", "kind": "slide_text", "text": s["text"],
                    "start": None, "end": None, "page": s["page"], "frame_id": None, "slide_id": s["id"],
                    "image_url": furl(aid, s["path"]), "language": m["metadata"]["language"],
                    "metadata": m["metadata"], "source": prov(aid)})
    return out


exp_matches = [{"level": "file", "type": "exact", "a": "a_02", "b": "a_03", "score": 1.0, "method": "sha256"}] + \
    [{"level": "slide", "type": t, "a": ra, "b": rb, "score": sc, "method": me} for ra, rb, t, me, sc, _ in SLIDE_MATCHES]
dump("export_asset.json", {"schema_version": "1.0", "exported_at": NOW, "source": prov("a_02"), "kind": "document",
                           "metadata": MANIFESTS["a_02"]["metadata"], "pipeline": {**MANIFESTS["a_02"]["pipeline"], "unique_slides": None},
                           "chunks": chunks("a_02"), "frames": [], "slides": slide_views("a_02"), "matches": exp_matches})
lines = [json.dumps(c, ensure_ascii=False) for aid in ("a_01", "a_02") for c in chunks(aid)]
(FIX / "export.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("fixtures written to", FIX)
