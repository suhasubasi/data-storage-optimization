"""Duplicate engine (CONTRACTS.md §5). Hashes come from the pipeline (per file); cross-file
matching runs here over SQLite and is written to the `matches` table.

Classes:
  exact_file    same file SHA-256 (file name never decides)
  shared_slide  same normalised-text SHA-256 AND pHash distance <= shared_slide_max_phash_distance
  similar_slide close pHash or text ratio >= min, but not shared -> needs_review, never exact

Noise rules (REC, from CONTRACTS.md): never match an asset with itself; pairs stored once with
a_id < b_id; slide matching uses ONE representative per exact-file group (earliest upload), so
`deck.pdf` and `deck (1).pdf` don't produce repeated slide groups; pages whose normalised text is
shorter than min_normalised_text_chars_for_text_match can't match by text (so never `shared`).
Extra REC (backend-only noise rules, easy to switch off):
- pHash-only matches are skipped for near-uniform images (blank pages), else every blank page in
  every deck would be "similar".
- PHASH_ONLY_NEEDS_SHORT_TEXT: when BOTH pages have enough text, the text decides; a close pHash
  alone does not make them "similar". On real samples, unrelated text slides in the same template
  had pHash distance 8-10 (threshold 12) and flooded the review list. pHash-only still flags
  image-heavy / scanned pages, where text can't decide.
"""
from __future__ import annotations

import json
import re
import unicodedata
from difflib import SequenceMatcher
from itertools import combinations

from . import db, settings

PHASH_BITS = 64
PHASH_ONLY_NEEDS_SHORT_TEXT = True


def thresholds() -> dict:
    t = json.loads(settings.THRESHOLDS.read_text(encoding="utf-8"))["duplicates"]
    return {
        "shared_max": int(t["shared_slide_max_phash_distance"]),
        "similar_max": int(t["similar_slide_max_phash_distance"]),
        "min_ratio": float(t["similar_slide_min_text_ratio"]),
        "min_chars": int(t["min_normalised_text_chars_for_text_match"]),
    }


def normalise(text: str) -> str:
    """NFKC -> lowercase -> collapse whitespace -> strip (same rule as the pipeline's text hash)."""
    return " ".join(unicodedata.normalize("NFKC", text).lower().split())


def phash_distance(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def _near_uniform(ph: str) -> bool:
    ones = bin(int(ph, 16)).count("1")
    return ones <= 2 or ones >= PHASH_BITS - 2


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]{3,}", normalise(text or ""))}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _is_exported_slide_deck(filename: str | None) -> bool:
    low = (filename or "").strip().lower()
    return low.endswith((".slides.pptx", ".slides.pdf"))


def representatives(conn) -> dict[str, str]:
    """asset_id -> representative asset_id of its exact-file (SHA-256) group.

    The representative is the earliest upload in the group that has ingested slides
    (falls back to the earliest upload)."""
    rows = conn.execute("SELECT id, sha256, created_at FROM assets ORDER BY created_at, id").fetchall()
    with_slides = {r[0] for r in conn.execute("SELECT DISTINCT asset_id FROM slides")}
    groups: dict[str, list[str]] = {}
    for r in rows:
        groups.setdefault(r["sha256"], []).append(r["id"])
    rep: dict[str, str] = {}
    for ids in groups.values():
        chosen = next((i for i in ids if i in with_slides), ids[0])
        for i in ids:
            rep[i] = chosen
    return rep


def compare_slides(a: dict, b: dict, t: dict) -> tuple[str, str, float, dict] | None:
    """Return (type, method, score, evidence) or None. a/b have text, text_sha256, phash."""
    na, nb = normalise(a["text"]), normalise(b["text"])
    text_ok = len(na) >= t["min_chars"] and len(nb) >= t["min_chars"]
    d = phash_distance(a["phash"], b["phash"])
    if text_ok and a["text_sha256"] == b["text_sha256"] and d <= t["shared_max"]:
        return "shared", "text_sha256+phash", 1.0, {
            "method": "text_sha256+phash", "sha256": None, "text_sha256": a["text_sha256"],
            "phash_distance": d, "text_similarity": None}
    ratio = None
    if text_ok:
        sm = SequenceMatcher(None, na, nb, autojunk=False)
        if sm.real_quick_ratio() >= t["min_ratio"] and sm.quick_ratio() >= t["min_ratio"]:
            ratio = sm.ratio()
    if ratio is not None and ratio >= t["min_ratio"]:
        return "similar", "text_ratio", round(ratio, 4), {
            "method": "text_ratio", "sha256": None, "text_sha256": None,
            "phash_distance": d, "text_similarity": round(ratio, 4)}
    if text_ok and PHASH_ONLY_NEEDS_SHORT_TEXT:
        return None
    if d <= t["similar_max"] and not (_near_uniform(a["phash"]) or _near_uniform(b["phash"])):
        return "similar", "phash", round(1 - d / PHASH_BITS, 4), {
            "method": "phash", "sha256": None, "text_sha256": None,
            "phash_distance": d, "text_similarity": round(ratio, 4) if ratio is not None else None}
    return None


def recompute_matches() -> int:
    """Rebuild the whole `matches` table from assets + slides. Returns number of rows."""
    t = thresholds()
    with db.write() as conn:
        conn.execute("DELETE FROM matches")
        rows: list[tuple] = []
        # 1) exact files: every pair inside a SHA-256 group
        by_sha: dict[str, list[str]] = {}
        for r in conn.execute("SELECT id, sha256 FROM assets ORDER BY id"):
            by_sha.setdefault(r["sha256"], []).append(r["id"])
        for sha, ids in by_sha.items():
            for x, y in combinations(sorted(ids), 2):
                ev = {"method": "sha256", "sha256": sha, "text_sha256": None, "phash_distance": None, "text_similarity": None}
                rows.append((x, y, "file", "exact", "sha256", 1.0, json.dumps(ev)))
        # 2) slides: only representatives of exact-file groups, never within one asset
        rep = representatives(conn)
        reps = sorted(set(rep.values()))
        slides = [dict(r) for r in conn.execute(
            "SELECT asset_id, id, page, text, text_sha256, phash FROM slides WHERE asset_id IN (%s) ORDER BY asset_id, page"
            % ",".join("?" * len(reps)), reps)] if reps else []
        for a, b in combinations(slides, 2):
            if a["asset_id"] == b["asset_id"]:
                continue
            res = compare_slides(a, b, t)
            if res is None:
                continue
            typ, method, score, ev = res
            ra, rb = sorted([f"{a['asset_id']}:{a['id']}", f"{b['asset_id']}:{b['id']}"])
            rows.append((ra, rb, "slide", typ, method, score, json.dumps(ev)))
        conn.executemany(
            "INSERT INTO matches (a_id, b_id, level, type, method, score, evidence) VALUES (?,?,?,?,?,?,?)", rows)
        # 3) video frames -> matching document slide by pHash + transcript token affinity (sets frames.matched_slide_id)
        # Exclude self-exported .slides.pptx / .slides.pdf decks so they never hijack source-of-truth matches.
        raw_doc_slides = conn.execute(
            """
            SELECT s.asset_id, s.id, s.page, s.phash, s.text, a.filename, a.created_at, a.metadata_json
            FROM slides s
            JOIN assets a ON a.id = s.asset_id
            ORDER BY a.created_at, s.asset_id, s.page
            """
        ).fetchall()
        doc_slides: list[dict] = []
        for s in raw_doc_slides:
            if _is_exported_slide_deck(s["filename"]) or _near_uniform(s["phash"]):
                continue
            try:
                meta = json.loads(s["metadata_json"] or "{}")
            except ValueError:
                meta = {}
            doc_slides.append({
                "ref": f"{s['asset_id']}:{s['id']}",
                "asset_id": s["asset_id"],
                "page": s["page"],
                "phash": s["phash"],
                "tokens": _tokens(s["text"]),
                "has_doc_no": 0 if meta.get("doc_number") else 1,
                "has_rev": 0 if meta.get("revision") else 1,
                "created_at": s["created_at"] or "",
            })
        doc_slides.sort(key=lambda s: (s["has_doc_no"], s["has_rev"], s["created_at"], s["asset_id"], s["page"]))
        for idx, s in enumerate(doc_slides):
            s["prio"] = idx

        all_frames = [
            dict(r)
            for r in conn.execute("SELECT asset_id, id, path, phash FROM frames ORDER BY asset_id, t_start, id")
        ]
        if all_frames:
            frames_by_video: dict[str, list[dict]] = {}
            for f in all_frames:
                frames_by_video.setdefault(f["asset_id"], []).append(f)

            segs_by_video_frame: dict[tuple[str, str], list[str]] = {}
            for seg in conn.execute("SELECT asset_id, frame_id, text FROM segments WHERE frame_id IS NOT NULL"):
                segs_by_video_frame.setdefault((seg["asset_id"], seg["frame_id"]), []).append(seg["text"])

            strict_max = min(int(t["similar_max"]), 10)
            relaxed_max = max(int(t["similar_max"]), 14)
            frame_updates: list[tuple[str | None, str, str]] = []

            for vid, vframes in frames_by_video.items():
                if not doc_slides:
                    for f in vframes:
                        frame_updates.append((None, vid, f["id"]))
                    continue

                # Pool spoken transcript tokens across all time ranges sharing the same unique slide path
                tokens_by_path: dict[str, set[str]] = {}
                for f in vframes:
                    txt = " ".join(segs_by_video_frame.get((vid, f["id"]), ()))
                    tokens_by_path.setdefault(f["path"], set()).update(_tokens(txt))

                # Anchor decks: documents with >= 1 strong pHash match (<= strict_max) in this recording
                anchor_decks = {
                    s["asset_id"]
                    for f in vframes
                    if f["phash"] and not _near_uniform(f["phash"])
                    for s in doc_slides
                    if phash_distance(f["phash"], s["phash"]) <= strict_max
                }

                for f in vframes:
                    fph = f["phash"]
                    best_ref: str | None = None
                    best_key: tuple[int, float, int] | None = None
                    ftoks = tokens_by_path.get(f["path"], set())
                    if fph and not _near_uniform(fph):
                        for s in doc_slides:
                            d = phash_distance(fph, s["phash"])
                            if d > 18:
                                continue
                            in_anchor = s["asset_id"] in anchor_decks
                            jac = _jaccard(ftoks, s["tokens"])
                            matched = (
                                d <= strict_max
                                or (d <= 12 and (in_anchor or len(s["tokens"]) >= 3))
                                or (d <= relaxed_max and (in_anchor or jac >= 0.05))
                                or (d <= 18 and ((in_anchor and jac >= 0.04) or jac >= 0.20))
                            )
                            if not matched:
                                continue
                            eff_d = d - (1 if in_anchor and d > strict_max else 0)
                            cand_key = (eff_d, -round(jac, 4), s["prio"])
                            if best_key is None or cand_key < best_key:
                                best_key = cand_key
                                best_ref = s["ref"]
                    frame_updates.append((best_ref, vid, f["id"]))

            conn.executemany(
                "UPDATE frames SET matched_slide_id = ? WHERE asset_id = ? AND id = ?",
                frame_updates,
            )
        return len(rows)
