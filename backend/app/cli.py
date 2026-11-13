"""Backend admin commands (reproducible DB setup; the DB file itself is git-ignored).

    python -m app.cli init-db                  # create data/dso.sqlite from contracts/schema.sql
    python -m app.cli load-fixtures [--reset]  # demo dataset from contracts/fixtures (5 assets, 4 manifests)
    python -m app.cli ingest a_1234abcd        # (re)ingest data/derived/<id>/manifest.json
    python -m app.cli recompute-duplicates     # rebuild the matches table
    python -m app.cli add-file ../data/samples/deck.pdf --source sharepoint --owner bjorn [--process]
                                               # same as POST /api/assets (copies the file; source untouched)
"""
from __future__ import annotations

import argparse
from pathlib import Path

from . import db, duplicates, ingest, settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init-db")
    lf = sub.add_parser("load-fixtures")
    lf.add_argument("--reset", action="store_true", help="delete ONLY data/dso.sqlite first (never originals)")
    ig = sub.add_parser("ingest")
    ig.add_argument("asset_id")
    ig.add_argument("--manifest", type=Path, default=None)
    sub.add_parser("recompute-duplicates")
    af = sub.add_parser("add-file")
    af.add_argument("path", type=Path)
    af.add_argument("--source", required=True, choices=["sharepoint", "onedrive", "ericsson_play"])
    af.add_argument("--owner", required=True)
    af.add_argument("--name", default=None, help="file name to store (default: the file's own name)")
    af.add_argument("--process", action="store_true", help="run the pipeline now and wait")
    a = p.parse_args(argv)

    if a.cmd == "init-db":
        db.init_db()
        print(f"DB ready: {settings.DB_PATH}")
    elif a.cmd == "load-fixtures":
        ids = ingest.load_fixtures(reset=a.reset)
        print(f"Loaded fixtures {', '.join(ids)} into {settings.DB_PATH}")
    elif a.cmd == "ingest":
        db.init_db()
        m = ingest.ingest_manifest(a.asset_id, a.manifest)
        print(f"Ingested {m.asset_id}: {len(m.segments)} segments, {len(m.frames)} frames, {len(m.slides)} slides")
    elif a.cmd == "recompute-duplicates":
        db.init_db()
        print(f"{duplicates.recompute_matches()} match rows")
    elif a.cmd == "add-file":
        from . import jobs, uploads
        with open(a.path, "rb") as f:
            aid = uploads.save_original(f, a.name or a.path.name, a.source, a.owner)
        print(f"Added {aid} ({a.name or a.path.name}, {a.source}, owner {a.owner})")
        if a.process:
            job = jobs.start_job(aid)
            import time
            while (j := jobs.get_job(job.id)).status.value in ("queued", "running"):
                time.sleep(0.5)
            print(f"Job {j.id}: {j.status.value}" + (f" - {j.error}" if j.error else ""))
            return 0 if j.status.value == "done" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
