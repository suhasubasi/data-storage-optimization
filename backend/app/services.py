"""Read-side logic: builds every API response from SQLite using the frozen contract models."""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Iterator

from dso_contracts import SAVINGS_FORMULA
from dso_contracts.models import (
    Asset, AssetDetail, AssetMetadata, DerivedSummary, DuplicateEvidence, DuplicateGroup, DuplicateLocation,
    DuplicateMember, DuplicateReport, ExportAsset, ExportChunk, ExportMatch, FrameView, HashRecord, Job, MediaRef,
    OffboardingReview, OffboardingRow, PipelineInfo, Provenance, RemovedItem, SearchHit, SearchResponse, Segment,
    SlideList, SlideMatch, SlideView, StorageReport, StorageScenario, StorageTotals, Timeline,
)

from . import db, duplicates
from .errors import not_found

EMPTY_META = {"title": None, "author": None, "doc_number": None, "revision": None, "date": None, "language": None}


# ---------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------
def original_url(row) -> str:
    return f"/files/originals/{row['id']}/{row['filename']}"


def derived_url(asset_id: str, path: str) -> str:
    return f"/files/derived/{asset_id}/{path}"


def get_asset_row(conn: sqlite3.Connection, asset_id: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None:
        raise not_found(f"Asset {asset_id} was not found.")
    return row


def _derived_totals(conn: sqlite3.Connection) -> dict[str, int]:
    return {r[0]: r[1] for r in conn.execute("SELECT asset_id, SUM(bytes) FROM derived_files GROUP BY asset_id")}


def asset_derived_bytes(conn, row, totals: dict[str, int] | None = None) -> int:
    if totals is None:
        files = conn.execute("SELECT COALESCE(SUM(bytes), 0) FROM derived_files WHERE asset_id = ?", (row["id"],)).fetchone()[0]
    else:
        files = totals.get(row["id"], 0)
    return int(files or 0) + int(row["manifest_bytes"] or 0)


def test_data_ids(conn) -> set[str]:
    """REC v1.1: assets labelled as generated test/sample data (asset_labels.test_data = 1)."""
    return {r[0] for r in conn.execute("SELECT asset_id FROM asset_labels WHERE test_data = 1")}


def to_asset(conn, row, totals: dict[str, int] | None = None, test_ids: set[str] | None = None) -> Asset:
    if test_ids is None:
        test_ids = test_data_ids(conn)
    return Asset(
        id=row["id"], filename=row["filename"], kind=row["kind"], bytes=row["bytes"], sha256=row["sha256"],
        source_system=row["source_system"], source_simulated=bool(row["source_simulated"]), owner=row["owner"],
        status=row["status"], created_at=row["created_at"], derived_bytes=asset_derived_bytes(conn, row, totals),
        original_url=original_url(row), test_data=row["id"] in test_ids,
    )


def unique_slides_info(row) -> dict | None:
    """pipeline.unique_slides of the ingested manifest, or None if the pass has not run."""
    if not row["pipeline_json"]:
        return None
    try:
        return (json.loads(row["pipeline_json"]) or {}).get("unique_slides")
    except ValueError:
        return None


def slide_numbers(frames) -> dict[str, int]:
    """frame path -> unique slide number, in order of first appearance (same numbering as the pass)."""
    out: dict[str, int] = {}
    for f in sorted(frames, key=lambda f: (f["t_start"], f["id"])):
        if f["path"] not in out:
            out[f["path"]] = len(out) + 1
    return out


def metadata_of(row) -> AssetMetadata | None:
    if row["manifest_bytes"] is None:
        return None
    return AssetMetadata.model_validate_json(row["metadata_json"])


def metadata_or_empty(row) -> AssetMetadata:
    return metadata_of(row) or AssetMetadata(**EMPTY_META)


def to_job(row) -> Job:
    return Job(id=row["id"], asset_id=row["asset_id"], status=row["status"], progress=row["progress"],
               stage=row["stage"], error=row["error"], started_at=row["started_at"], finished_at=row["finished_at"])


def provenance(row) -> Provenance:
    return Provenance(asset_id=row["id"], filename=row["filename"], sha256=row["sha256"],
                      source_system=row["source_system"], source_simulated=bool(row["source_simulated"]),
                      owner=row["owner"], original_url=original_url(row))


def frame_view(asset_id: str, f, slides: dict[str, int] | None = None) -> FrameView:
    return FrameView(id=f["id"], t_start=f["t_start"], t_end=f["t_end"], image_url=derived_url(asset_id, f["path"]),
                     bytes=f["bytes"], phash=f["phash"], matched_slide=f["matched_slide_id"],
                     slide=slides.get(f["path"]) if slides else None)


# ---------------------------------------------------------------------------------------------
# assets
# ---------------------------------------------------------------------------------------------
def list_assets(owner: str | None = None) -> list[Asset]:
    with db.read() as conn:
        totals = _derived_totals(conn)
        test_ids = test_data_ids(conn)
        if owner:
            rows = conn.execute("SELECT * FROM assets WHERE owner = ? ORDER BY created_at, id", (owner,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM assets ORDER BY created_at, id").fetchall()
        return [to_asset(conn, r, totals, test_ids) for r in rows]


def get_asset(asset_id: str) -> Asset:
    with db.read() as conn:
        return to_asset(conn, get_asset_row(conn, asset_id))


def latest_job_row(conn, asset_id: str):
    return conn.execute("SELECT * FROM jobs WHERE asset_id = ? ORDER BY rowid DESC LIMIT 1", (asset_id,)).fetchone()


def asset_detail(asset_id: str) -> AssetDetail:
    with db.read() as conn:
        row = get_asset_row(conn, asset_id)
        derived = None
        if row["manifest_bytes"] is not None:
            by_kind: dict[str, int] = {}
            files = conn.execute("SELECT kind, bytes FROM derived_files WHERE asset_id = ?", (asset_id,)).fetchall()
            for f in files:
                by_kind[f["kind"]] = by_kind.get(f["kind"], 0) + f["bytes"]
            by_kind["manifest"] = row["manifest_bytes"]
            count = lambda t: conn.execute(f"SELECT COUNT(*) FROM {t} WHERE asset_id = ?", (asset_id,)).fetchone()[0]  # noqa: E731
            us = unique_slides_info(row)
            derived = DerivedSummary(
                derived_bytes=asset_derived_bytes(conn, row), manifest_bytes=row["manifest_bytes"],
                file_count=len(files) + 1, segment_count=count("segments"), frame_count=count("frames"),
                slide_count=count("slides"), bytes_by_kind=by_kind,
                unique_slide_count=us.get("unique_slide_count") if us else None,
                source_frame_count=us.get("source_frame_count") if us else None)
        job = latest_job_row(conn, asset_id)
        return AssetDetail(
            asset=to_asset(conn, row), metadata=metadata_of(row), derived=derived,
            pipeline=PipelineInfo.model_validate_json(row["pipeline_json"]) if row["pipeline_json"] else None,
            latest_job=to_job(job) if job else None)


# ---------------------------------------------------------------------------------------------
# timeline + slides
# ---------------------------------------------------------------------------------------------
def timeline(asset_id: str) -> Timeline:
    with db.read() as conn:
        row = get_asset_row(conn, asset_id)
        meta = metadata_or_empty(row)
        segs = conn.execute('SELECT * FROM segments WHERE asset_id = ? ORDER BY "start", id', (asset_id,)).fetchall()
        frames = conn.execute("SELECT * FROM frames WHERE asset_id = ? ORDER BY t_start, id", (asset_id,)).fetchall()
        nums = slide_numbers(frames) if unique_slides_info(row) else None
        return Timeline(
            asset_id=asset_id, language=meta.language, duration_seconds=meta.duration_seconds,
            original_url=original_url(row),
            segments=[Segment(id=s["id"], start=s["start"], end=s["end"], text=s["text"], frame_id=s["frame_id"],
                              speaker=s["speaker"]) for s in segs],
            frames=[frame_view(asset_id, f, nums) for f in frames])


def _slide_matches_for(conn, asset_id: str) -> dict[str, list[SlideMatch]]:
    """slide local id -> matches. An exact copy that is not its group's representative inherits the
    representative's slide matches (identical bytes => identical pages). REC."""
    rep = duplicates.representatives(conn).get(asset_id, asset_id)
    assets = {r["id"]: r for r in conn.execute("SELECT id, filename, source_system FROM assets")}
    pages = {f"{r['asset_id']}:{r['id']}": r["page"] for r in conn.execute("SELECT asset_id, id, page FROM slides")}
    out: dict[str, list[SlideMatch]] = {}
    rows = conn.execute(
        "SELECT * FROM matches WHERE level = 'slide' AND (a_id GLOB ? OR b_id GLOB ?) ORDER BY type, score DESC, id",
        (f"{rep}:*", f"{rep}:*")).fetchall()
    for m in rows:
        mine, other = (m["a_id"], m["b_id"]) if m["a_id"].startswith(rep + ":") else (m["b_id"], m["a_id"])
        oaid, osid = other.split(":")
        if oaid not in assets or other not in pages:
            continue
        out.setdefault(mine.split(":")[1], []).append(SlideMatch(
            type=m["type"], other_asset_id=oaid, other_slide_id=osid, other_filename=assets[oaid]["filename"],
            other_page=pages[other], other_source_system=assets[oaid]["source_system"], score=m["score"],
            method=m["method"]))
    return out


def slide_views(conn, row) -> list[SlideView]:
    aid = row["id"]
    matches = _slide_matches_for(conn, aid)
    return [SlideView(
        id=s["id"], page=s["page"], text=s["text"],
        hashes=HashRecord(file_sha256=row["sha256"], text_sha256=s["text_sha256"], phash=s["phash"]),
        image_url=derived_url(aid, s["path"]), bytes=s["bytes"], matches=matches.get(s["id"], []))
        for s in conn.execute("SELECT * FROM slides WHERE asset_id = ? ORDER BY page", (aid,))]


def slide_list(asset_id: str) -> SlideList:
    with db.read() as conn:
        row = get_asset_row(conn, asset_id)
        return SlideList(asset_id=asset_id, metadata=metadata_of(row), slides=slide_views(conn, row))


# ---------------------------------------------------------------------------------------------
# search (FTS5)
# ---------------------------------------------------------------------------------------------
def fts_query(q: str) -> str | None:
    """User text -> safe FTS5 query: every word must appear (prefix match). No FTS syntax injection."""
    tokens = re.findall(r"\w+", q, flags=re.UNICODE)
    if not tokens:
        return None
    return " ".join(f'"{t}"*' for t in tokens)


def search(q: str, limit: int = 20) -> SearchResponse:
    query = fts_query(q)
    if query is None:
        return SearchResponse(query=q, total=0, hits=[])
    with db.read() as conn:
        total = conn.execute("SELECT COUNT(*) FROM search_fts WHERE search_fts MATCH ?", (query,)).fetchone()[0]
        rows = conn.execute(
            "SELECT asset_id, item_type, item_id, text, "
            "snippet(search_fts, 0, '<mark>', '</mark>', '…', 16) AS snip, bm25(search_fts) AS rank "
            "FROM search_fts WHERE search_fts MATCH ? ORDER BY rank LIMIT ?", (query, limit)).fetchall()
        assets: dict[str, sqlite3.Row] = {}
        hits = []
        for r in rows:
            aid = r["asset_id"]
            a = assets.get(aid) or conn.execute("SELECT * FROM assets WHERE id = ?", (aid,)).fetchone()
            if a is None:
                continue
            assets[aid] = a
            common = dict(asset_id=aid, filename=a["filename"], kind=a["kind"], source_system=a["source_system"],
                          owner=a["owner"], text=r["text"], snippet=r["snip"], item_id=r["item_id"],
                          score=round(-r["rank"], 4))
            if r["item_type"] == "asset":
                if a["kind"] == "video":
                    f = conn.execute("SELECT * FROM frames WHERE asset_id = ? ORDER BY t_start, id LIMIT 1", (aid,)).fetchone()
                    media = MediaRef(type="frame", asset_id=aid, item_id=f["id"], url=derived_url(aid, f["path"]),
                                     bytes=f["bytes"], t_start=f["t_start"], t_end=f["t_end"], page=None) if f else None
                    page = None
                else:
                    sl = conn.execute("SELECT * FROM slides WHERE asset_id = ? ORDER BY page LIMIT 1", (aid,)).fetchone()
                    media = MediaRef(type="slide", asset_id=aid, item_id=sl["id"], url=derived_url(aid, sl["path"]),
                                     bytes=sl["bytes"], t_start=None, t_end=None, page=sl["page"]) if sl else None
                    page = sl["page"] if sl else None
                hits.append(SearchHit(hit_type="asset", start=None, end=None, page=page, frame_id=None, media=media,
                                      **common))
            elif r["item_type"] == "segment":
                s = conn.execute('SELECT * FROM segments WHERE asset_id = ? AND id = ?', (aid, r["item_id"])).fetchone()
                f = conn.execute("SELECT * FROM frames WHERE asset_id = ? AND id = ?",
                                 (aid, s["frame_id"])).fetchone() if s and s["frame_id"] else None
                if f is not None:
                    media = MediaRef(type="frame", asset_id=aid, item_id=f["id"], url=derived_url(aid, f["path"]),
                                     bytes=f["bytes"], t_start=f["t_start"], t_end=f["t_end"], page=None)
                else:  # no key frame on screen: point to the original video at this time
                    media = MediaRef(type="original", asset_id=aid, item_id=None, url=original_url(a),
                                     bytes=a["bytes"], t_start=s["start"] if s else None, t_end=s["end"] if s else None,
                                     page=None)
                hits.append(SearchHit(hit_type="segment", start=s["start"] if s else None, end=s["end"] if s else None,
                                      page=None, frame_id=f["id"] if f is not None else None, media=media, **common))
            else:
                s = conn.execute("SELECT * FROM slides WHERE asset_id = ? AND id = ?", (aid, r["item_id"])).fetchone()
                media = MediaRef(type="slide", asset_id=aid, item_id=s["id"], url=derived_url(aid, s["path"]),
                                 bytes=s["bytes"], t_start=None, t_end=None, page=s["page"]) if s else None
                hits.append(SearchHit(hit_type="slide", start=None, end=None, page=s["page"] if s else None,
                                      frame_id=None, media=media, **common))
        return SearchResponse(query=q, total=total, hits=hits)


# ---------------------------------------------------------------------------------------------
# duplicates
# ---------------------------------------------------------------------------------------------
def _member(assets, slides, ref: str) -> DuplicateMember:
    aid, _, sid = ref.partition(":")
    a = assets[aid]
    s = slides.get(ref) if sid else None
    return DuplicateMember(asset_id=aid, filename=a["filename"], source_system=a["source_system"], owner=a["owner"],
                           bytes=a["bytes"], slide_id=sid or None, page=s["page"] if s else None,
                           image_url=derived_url(aid, s["path"]) if s else None)


def duplicate_report(type_filter: str | None = None) -> DuplicateReport:
    with db.read() as conn:
        assets = {r["id"]: r for r in conn.execute("SELECT * FROM assets")}
        slides = {f"{r['asset_id']}:{r['id']}": r for r in conn.execute("SELECT asset_id, id, page, path, text_sha256 FROM slides")}
        groups: list[DuplicateGroup] = []
        # exact files: one group per SHA-256 with >= 2 copies, earliest upload first
        by_sha: dict[str, list[sqlite3.Row]] = {}
        for a in sorted(assets.values(), key=lambda r: (r["created_at"], r["id"])):
            by_sha.setdefault(a["sha256"], []).append(a)
        for sha, members in by_sha.items():
            if len(members) < 2:
                continue
            groups.append(DuplicateGroup(
                id=f"g_exact_{sha[:12]}", type="exact_file", needs_review=False, score=1.0,
                evidence=DuplicateEvidence(method="sha256", sha256=sha),
                members=[_member(assets, slides, m["id"]) for m in members]))
        rows = conn.execute("SELECT * FROM matches WHERE level = 'slide' ORDER BY a_id, b_id").fetchall()
        # shared slides: connected components (same slide in 3 decks -> one group of 3)
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.setdefault(x, x) != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        shared = [m for m in rows if m["type"] == "shared" and m["a_id"] in slides and m["b_id"] in slides]
        for m in shared:
            ra, rb = find(m["a_id"]), find(m["b_id"])
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
        comps: dict[str, list] = {}
        for m in shared:
            comps.setdefault(find(m["a_id"]), []).append(m)
        for root, ms in sorted(comps.items()):
            refs = sorted({r for m in ms for r in (m["a_id"], m["b_id"])})
            dists = [json.loads(m["evidence"]).get("phash_distance") for m in ms]
            dists = [d for d in dists if d is not None]
            groups.append(DuplicateGroup(
                id=f"g_shared_{root.replace(':', '_')}", type="shared_slide", needs_review=False, score=1.0,
                evidence=DuplicateEvidence(method="text_sha256+phash", text_sha256=slides[refs[0]]["text_sha256"],
                                           phash_distance=max(dists) if dists else None),
                members=[_member(assets, slides, r) for r in refs]))
        # similar slides: one group per pair (similarity is not transitive), always needs review
        for m in rows:
            if m["type"] != "similar" or m["a_id"] not in slides or m["b_id"] not in slides:
                continue
            ev = json.loads(m["evidence"])
            groups.append(DuplicateGroup(
                id=f"g_similar_{m['a_id'].replace(':', '_')}_{m['b_id'].replace(':', '_')}", type="similar_slide",
                needs_review=True, score=m["score"], evidence=DuplicateEvidence(**ev),
                members=[_member(assets, slides, m["a_id"]), _member(assets, slides, m["b_id"])]))
        counts = {t: sum(g.type.value == t for g in groups) for t in ("exact_file", "shared_slide", "similar_slide")}
        if type_filter:
            groups = [g for g in groups if g.type.value == type_filter]
        return DuplicateReport(groups=groups, counts=counts)


# ---------------------------------------------------------------------------------------------
# storage report (CONTRACTS.md §6 — frozen formula)
# ---------------------------------------------------------------------------------------------
NOT_COUNTED = ["Backups", "Platform replication", "Archive tiers", "Compute cost", "Model weights", "Money"]
INFORMATION_LOST = ["Motion and live demos in video", "Gestures and body language",
                    "Tone of voice (unless the optional audio track is kept)", "Speaker identity (not in MVP)"]
NOTES = [
    "O = all original bytes in scope, every copy on every simulated system. D = all derived files + manifests. "
    "I = measured SQLite/FTS index size.",
    "D and I are counted in every scenario (conservative).",
    "Scenarios 1-3 are hypothetical and require human approval. The tool never deletes anything.",
    "Ericsson's own example (PDF p.2: ~1 GB → ~50 KB text + ~2 MB frames, 'roughly 99%') is their illustration, "
    "not our measurement.",
]
SCENARIO_TEXT = [
    (0, "today", "Scenario 0: today, real",
     "Nothing deleted. Derived data and the index are added on top of the originals, so the saving is negative.",
     "A = O + D + I"),
    (1, "replace_videos", "Scenario 1: replace videos",
     "If an approved process replaced each processed recording by its derived data.",
     "A = (O − processed video originals) + D + I"),
    (2, "remove_exact_duplicates", "Scenario 2: remove exact duplicates",
     "Keep one copy per SHA-256 group (the earliest upload). Shared or similar slides free nothing, because the files differ.",
     "A = (O − extra exact copies) + D + I"),
    (3, "both", "Scenario 3: both", "Scenarios 1 and 2 together, each file counted once.",
     "A = (O − processed video originals − extra exact copies, no double counting) + D + I"),
]


def compute_storage(assets: list[dict], derived_bytes: int, index_bytes: int, generated_at: str,
                    scope: str = "real_files", excluded: dict | None = None,
                    scope_note: str = "Scope: real uploaded files only (no generated test files in the library).",
                    ) -> StorageReport:
    """Pure function (unit-tested against contracts/fixtures/storage_report.json).

    assets: dicts with id, filename, kind, bytes, sha256, status, created_at.
    scope / excluded / scope_note: REC v1.1, which files are in O (generated test files are left out by default)."""
    O = sum(a["bytes"] for a in assets)
    D, I = derived_bytes, index_bytes
    ordered = sorted(assets, key=lambda a: (a["created_at"], a["id"]))
    by_sha: dict[str, list[dict]] = {}
    for a in ordered:
        by_sha.setdefault(a["sha256"], []).append(a)
    extra = [(c, g[0]["id"]) for g in by_sha.values() for c in g[1:]]

    def rem(a, reason, kept=None):
        return RemovedItem(asset_id=a["id"], filename=a["filename"], bytes=a["bytes"], reason=reason,
                           kept_copy_asset_id=kept)

    s1 = [rem(a, "replaced_by_derived") for a in ordered if a["kind"] == "video" and a["status"] == "ready"]
    s2 = [rem(c, "exact_duplicate", k) for c, k in extra]
    s3, seen = [], set()
    for r in s2 + s1:  # each file counted once
        if r.asset_id not in seen:
            seen.add(r.asset_id)
            s3.append(r)
    removed_by = {0: [], 1: s1, 2: s2, 3: s3}
    scenarios = []
    for sid, key, label, desc, formula in SCENARIO_TEXT:
        removed = removed_by[sid]
        kept = O - sum(r.bytes for r in removed)
        A = kept + D + I
        scenarios.append(StorageScenario(
            id=sid, key=key, label=label, description=desc, hypothetical=sid != 0, formula=formula,
            before_bytes=O, after_bytes=A, saved_bytes=O - A,
            savings_pct=round((O - A) / O * 100, 4) if O else None,
            kept_original_bytes=kept, derived_bytes=D, index_bytes=I, removed=removed))
    totals = StorageTotals(
        asset_count=len(assets), original_bytes=O,
        video_original_bytes=sum(a["bytes"] for a in assets if a["kind"] == "video"),
        document_original_bytes=sum(a["bytes"] for a in assets if a["kind"] == "document"),
        derived_bytes=D, index_bytes=I, extra_exact_copy_bytes=sum(c["bytes"] for c, _ in extra))
    return StorageReport(generated_at=generated_at, formula=SAVINGS_FORMULA, totals=totals, scenarios=scenarios,
                         not_counted=NOT_COUNTED, information_lost=INFORMATION_LOST, notes=[scope_note, *NOTES],
                         scope=scope, excluded_test_data=excluded or {"asset_count": 0, "original_bytes": 0,
                                                                      "derived_bytes": 0, "asset_ids": []})


def storage_report(include_test_data: bool = False) -> StorageReport:
    """Measured storage report. Default scope = real files only: assets labelled as generated test data
    (asset_labels.test_data = 1) are left out of O and D, so they are never presented as customer data.
    I is always the WHOLE database (it cannot be split per file); that is conservative."""
    I = db.index_bytes()  # measure first (checkpoint), then read
    with db.read() as conn:
        test_ids = test_data_ids(conn)
        rows = [dict(r) for r in conn.execute(
            "SELECT id, filename, kind, bytes, sha256, status, created_at, manifest_bytes FROM assets")]
        per_asset = _derived_totals(conn)

    def d_of(a: dict) -> int:
        return int(per_asset.get(a["id"], 0) or 0) + int(a["manifest_bytes"] or 0)

    in_scope = rows if include_test_data else [a for a in rows if a["id"] not in test_ids]
    left_out = [] if include_test_data else [a for a in rows if a["id"] in test_ids]
    excluded = {"asset_count": len(left_out), "original_bytes": sum(a["bytes"] for a in left_out),
                "derived_bytes": sum(d_of(a) for a in left_out),
                "asset_ids": sorted(a["id"] for a in left_out)}
    if include_test_data:
        scope_note = (f"Scope: all {len(rows)} files in the library, INCLUDING {len(test_ids & {a['id'] for a in rows})} "
                      "generated test files (not customer data).")
    elif left_out:
        scope_note = (f"Scope: real uploaded files only. {len(left_out)} generated test files "
                      f"({excluded['original_bytes']} B originals, {excluded['derived_bytes']} B derived) are left out. "
                      "I is still the whole database, including their rows (conservative).")
    else:
        scope_note = "Scope: real uploaded files only (no generated test files in the library)."
    return compute_storage(in_scope, sum(d_of(a) for a in in_scope), I, db.utc_now(),
                           scope="all_files" if include_test_data else "real_files", excluded=excluded,
                           scope_note=scope_note)


# ---------------------------------------------------------------------------------------------
# offboarding (CONTRACTS.md §7 — recommend only, never delete)
# ---------------------------------------------------------------------------------------------
def offboarding(owner: str) -> OffboardingReview:
    with db.read() as conn:
        mine = conn.execute("SELECT * FROM assets WHERE owner = ? ORDER BY created_at, id", (owner,)).fetchall()
        rows = []
        for a in mine:
            dups = conn.execute(
                "SELECT id, filename, source_system, owner FROM assets WHERE sha256 = ? AND id != ? AND owner != ? "
                "ORDER BY created_at, id", (a["sha256"], a["id"], owner)).fetchall()
            locs = [DuplicateLocation(asset_id=d["id"], filename=d["filename"], source_system=d["source_system"],
                                      owner=d["owner"]) for d in dups]
            if dups:
                b = dups[0]
                rec = "eligible_after_approval"
                reason = (f"Confirmed exact duplicate (same SHA-256) at {b['source_system']}: {b['filename']} "
                          f"(owner: {b['owner']})")
            else:
                rec, reason = "keep", "No exact copy owned by someone else. Shared or similar slides do not count."
            rows.append(OffboardingRow(asset_id=a["id"], filename=a["filename"], kind=a["kind"], bytes=a["bytes"],
                                       source_system=a["source_system"], recommendation=rec, reason=reason,
                                       duplicates_elsewhere=locs))
    eligible = [r for r in rows if r.recommendation.value == "eligible_after_approval"]
    return OffboardingReview(
        owner=owner, generated_at=db.utc_now(), deletes_performed=False, rows=rows,
        summary={"total": len(rows), "eligible": len(eligible), "keep": len(rows) - len(eligible),
                 "eligible_bytes": sum(r.bytes for r in eligible)})


# ---------------------------------------------------------------------------------------------
# export (AI-ready JSON / JSONL with provenance)
# ---------------------------------------------------------------------------------------------
def export_chunks(conn, row) -> list[ExportChunk]:
    aid = row["id"]
    meta = metadata_or_empty(row)
    prov = provenance(row)
    frames = {f["id"]: f for f in conn.execute("SELECT * FROM frames WHERE asset_id = ?", (aid,))}
    out = []
    for s in conn.execute('SELECT * FROM segments WHERE asset_id = ? ORDER BY "start", id', (aid,)):
        f = frames.get(s["frame_id"]) if s["frame_id"] else None
        out.append(ExportChunk(schema_version="1.0", chunk_id=f"{aid}:{s['id']}", kind="transcript_segment",
                               text=s["text"], start=s["start"], end=s["end"], page=None, frame_id=s["frame_id"],
                               slide_id=None, image_url=derived_url(aid, f["path"]) if f else None,
                               language=meta.language, metadata=meta, source=prov))
    for s in conn.execute("SELECT * FROM slides WHERE asset_id = ? ORDER BY page", (aid,)):
        out.append(ExportChunk(schema_version="1.0", chunk_id=f"{aid}:{s['id']}", kind="slide_text", text=s["text"],
                               start=None, end=None, page=s["page"], frame_id=None, slide_id=s["id"],
                               image_url=derived_url(aid, s["path"]), language=meta.language, metadata=meta,
                               source=prov))
    return out


def export_asset(asset_id: str) -> ExportAsset:
    with db.read() as conn:
        row = get_asset_row(conn, asset_id)
        frames = conn.execute("SELECT * FROM frames WHERE asset_id = ? ORDER BY t_start, id", (asset_id,)).fetchall()
        nums = slide_numbers(frames) if unique_slides_info(row) else None
        matches = conn.execute(
            "SELECT * FROM matches WHERE a_id = ? OR b_id = ? OR a_id GLOB ? OR b_id GLOB ? ORDER BY level, type, a_id, b_id",
            (asset_id, asset_id, f"{asset_id}:*", f"{asset_id}:*")).fetchall()
        return ExportAsset(
            schema_version="1.0", exported_at=db.utc_now(), source=provenance(row), kind=row["kind"],
            metadata=metadata_or_empty(row),
            pipeline=PipelineInfo.model_validate_json(row["pipeline_json"]) if row["pipeline_json"] else None,
            chunks=export_chunks(conn, row),
            frames=[frame_view(asset_id, f, nums) for f in frames],
            slides=slide_views(conn, row),
            matches=[ExportMatch(level=m["level"], type=m["type"], a=m["a_id"], b=m["b_id"], score=m["score"],
                                 method=m["method"]) for m in matches])


def export_jsonl() -> Iterator[str]:
    with db.read() as conn:
        rows = conn.execute("SELECT * FROM assets WHERE status = 'ready' ORDER BY created_at, id").fetchall()
        lines = [c.model_dump_json() + "\n" for r in rows for c in export_chunks(conn, r)]
    yield from lines
