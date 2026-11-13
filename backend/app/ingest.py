"""Manifest ingest (CONTRACTS.md §3) and the fixture demo-data loader.

The pipeline writes data/derived/<asset_id>/manifest.json; we validate it with the frozen
dso_contracts.models.Manifest, MEASURE manifest.json on disk (it cannot list its own size) and
store everything in SQLite. The pipeline never writes the database.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydantic import ValidationError

from dso_contracts.models import Manifest

from . import db, duplicates, settings


class IngestError(Exception):
    pass


def load_manifest(path: Path) -> Manifest:
    try:
        return Manifest.model_validate_json(path.read_bytes())
    except FileNotFoundError as e:
        raise IngestError(f"manifest.json not found at {path}") from e
    except ValidationError as e:
        raise IngestError(f"manifest.json does not match the contract: {e.error_count()} problem(s): "
                          f"{e.errors()[0]['loc']} {e.errors()[0]['msg']}") from e


def _write_manifest(conn: sqlite3.Connection, m: Manifest, manifest_bytes: int) -> None:
    aid = m.asset_id
    for table in ("segments", "frames", "slides", "derived_files"):
        conn.execute(f"DELETE FROM {table} WHERE asset_id = ?", (aid,))
    # Chat rows (REC v1.2) belong to the attached meeting chat, not to the manifest: keep them on re-processing.
    conn.execute("DELETE FROM search_fts WHERE asset_id = ? AND item_type != 'chat'", (aid,))

    conn.execute(
        "UPDATE assets SET metadata_json = ?, manifest_bytes = ?, pipeline_json = ?, status = 'ready' WHERE id = ?",
        (m.metadata.model_dump_json(), manifest_bytes, m.pipeline.model_dump_json(), aid),
    )
    conn.executemany(
        'INSERT INTO segments (asset_id, id, "start", "end", text, frame_id, speaker) VALUES (?,?,?,?,?,?,?)',
        [(aid, s.id, s.start, s.end, s.text, s.frame_id, s.speaker) for s in m.segments],
    )
    conn.executemany(
        "INSERT INTO frames (asset_id, id, t_start, t_end, path, bytes, phash, matched_slide_id) VALUES (?,?,?,?,?,?,?,?)",
        [(aid, f.id, f.t_start, f.t_end, f.path, f.bytes, f.phash, f.matched_slide) for f in m.frames],
    )
    conn.executemany(
        "INSERT INTO slides (asset_id, id, page, text, text_sha256, phash, path, bytes) VALUES (?,?,?,?,?,?,?,?)",
        [(aid, s.id, s.page, s.text, s.text_sha256, s.phash, s.path, s.bytes) for s in m.slides],
    )
    conn.executemany(
        "INSERT OR REPLACE INTO derived_files (asset_id, path, kind, bytes) VALUES (?,?,?,?)",
        [(aid, d.path, d.kind.value, d.bytes) for d in m.derived_files],
    )
    conn.executemany(
        "INSERT INTO search_fts (text, asset_id, item_type, item_id) VALUES (?,?,?,?)",
        [(s.text, aid, "segment", s.id) for s in m.segments if s.text.strip()]
        + [(s.text, aid, "slide", s.id) for s in m.slides if s.text.strip()],
    )
    index_asset_metadata(conn, aid)


# ---------------------------------------------------------------------------------------------
# Title / file name / metadata in search (REC v1.1). Only values really present on the asset:
# no spelling fixes, no invented keywords.
# ---------------------------------------------------------------------------------------------
META_ITEM_ID = "meta"


def asset_search_text(filename: str, metadata: dict) -> str:
    parts: list[str] = []
    for v in (metadata.get("title"), metadata.get("author"), metadata.get("doc_number"), metadata.get("revision"),
              filename):
        v = (v or "").strip() if isinstance(v, str) else ""
        if v and v not in parts:
            parts.append(v)
    return " · ".join(parts)


def index_asset_metadata(conn: sqlite3.Connection, asset_id: str) -> bool:
    """(Re)write the one 'asset' FTS row of a processed asset. Returns True if a row was written."""
    conn.execute("DELETE FROM search_fts WHERE asset_id = ? AND item_type = 'asset'", (asset_id,))
    row = conn.execute("SELECT filename, metadata_json, manifest_bytes FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None or row["manifest_bytes"] is None:
        return False
    try:
        meta = json.loads(row["metadata_json"] or "{}")
    except ValueError:
        meta = {}
    text = asset_search_text(row["filename"], meta if isinstance(meta, dict) else {})
    if not text:
        return False
    conn.execute("INSERT INTO search_fts (text, asset_id, item_type, item_id) VALUES (?,?,?,?)",
                 (text, asset_id, "asset", META_ITEM_ID))
    return True


def reindex_asset_metadata() -> int:
    """Re-index title/file name/metadata for every processed asset (no pipeline run). Idempotent."""
    with db.write() as conn:
        ids = [r["id"] for r in conn.execute("SELECT id FROM assets WHERE manifest_bytes IS NOT NULL ORDER BY id")]
        return sum(index_asset_metadata(conn, aid) for aid in ids)


def ingest_manifest(asset_id: str, manifest_path: Path | None = None, *, recompute: bool = True) -> Manifest:
    """Validate + ingest one manifest. Raises IngestError on any mismatch (asset is not changed then)."""
    path = manifest_path or (settings.DERIVED_DIR / asset_id / "manifest.json")
    m = load_manifest(path)
    manifest_bytes = path.stat().st_size  # measured, counted as derived data (D)
    if m.asset_id != asset_id:
        raise IngestError(f"manifest.json is for {m.asset_id}, expected {asset_id}")
    with db.write() as conn:
        row = conn.execute("SELECT kind, sha256 FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise IngestError(f"asset {asset_id} does not exist")
        if row["kind"] != m.kind.value:
            raise IngestError(f"manifest kind '{m.kind.value}' does not match asset kind '{row['kind']}'")
        if row["sha256"] != m.original.sha256:
            raise IngestError("manifest original.sha256 does not match the uploaded file's SHA-256")
        _write_manifest(conn, m, manifest_bytes)
    if recompute:
        duplicates.recompute_matches()
    return m
