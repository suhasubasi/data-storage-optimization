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
    conn.execute("DELETE FROM search_fts WHERE asset_id = ?", (aid,))

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


# ---------------------------------------------------------------------------------------------
# Demo data: contracts/fixtures (until the pipeline produces real manifests)
# ---------------------------------------------------------------------------------------------
def load_fixtures(reset: bool = False) -> list[str]:
    """Load contracts/fixtures/assets.json + manifests/*.json into the DB.

    The fixture originals and derived images do not exist on disk; sizes come from the fixtures
    (this is a demo dataset, not a measurement). Returns the asset ids loaded.
    """
    if reset:
        reset_database()
    db.init_db()
    fx = settings.FIXTURES_DIR
    assets = json.loads((fx / "assets.json").read_text(encoding="utf-8"))["assets"]
    with db.write() as conn:
        for a in assets:
            for table in ("segments", "frames", "slides", "derived_files", "jobs"):
                conn.execute(f"DELETE FROM {table} WHERE asset_id = ?", (a["id"],))
            conn.execute("DELETE FROM search_fts WHERE asset_id = ?", (a["id"],))
            conn.execute("DELETE FROM assets WHERE id = ?", (a["id"],))
            conn.execute(
                "INSERT INTO assets (id, filename, kind, bytes, sha256, source_system, source_simulated, owner, "
                "status, original_path, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (a["id"], a["filename"], a["kind"], a["bytes"], a["sha256"], a["source_system"],
                 1 if a["source_simulated"] else 0, a["owner"], "uploaded",
                 f"originals/{a['id']}/{a['filename']}", a["created_at"]),
            )
    loaded = []
    for a in assets:
        mp = fx / "manifests" / f"{a['id']}.manifest.json"
        if mp.exists():
            ingest_manifest(a["id"], mp, recompute=False)
        else:
            with db.write() as conn:
                conn.execute("UPDATE assets SET status = ? WHERE id = ?", (a["status"], a["id"]))
        loaded.append(a["id"])
    duplicates.recompute_matches()
    return loaded


def reset_database() -> None:
    """Remove ONLY the backend's own SQLite database files (never originals or derived files)."""
    with db.WRITE_LOCK:
        for suffix in ("", "-wal", "-shm"):
            p = settings.DB_PATH.with_name(settings.DB_PATH.name + suffix)
            if p.exists():
                p.unlink()
