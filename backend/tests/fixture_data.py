"""TEST-ONLY loader for the contract example data in contracts/fixtures.

These example files are synthetic and exist only so the automated tests can check the API against the
contracts. They are never loaded into a real database: the app has no command for it any more.
"""
from __future__ import annotations

import json

from app import db, duplicates, settings
from app.ingest import ingest_manifest

FIXTURES_DIR = settings.REPO_ROOT / "contracts" / "fixtures"


def load_fixtures(reset: bool = False) -> list[str]:
    """Load contracts/fixtures/assets.json + manifests/*.json into the DB.

    The fixture originals and derived images do not exist on disk; sizes come from the fixtures
    (this is a demo dataset, not a measurement). Returns the asset ids loaded.
    """
    if reset:
        reset_database()
    db.init_db()
    fx = FIXTURES_DIR
    assets = json.loads((fx / "assets.json").read_text(encoding="utf-8"))["assets"]
    with db.write() as conn:
        for a in assets:
            for table in ("segments", "frames", "slides", "derived_files", "jobs"):
                conn.execute(f"DELETE FROM {table} WHERE asset_id = ?", (a["id"],))
            conn.execute("DELETE FROM search_fts WHERE asset_id = ?", (a["id"],))
            conn.execute("DELETE FROM asset_labels WHERE asset_id = ?", (a["id"],))
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
