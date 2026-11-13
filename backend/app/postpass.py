"""Backend side of the unique-slide post-pass for an already processed recording.

Order (so the app never points at a missing picture, and nothing is lost if a step fails):
  1. pipeline `unique-slides`  -> new transcript.json + manifest.json (no file deleted; old manifest + decision
                                 list saved in data/audit/unique-slides/). Speech-to-text is NOT run again.
  2. ingest the new manifest  -> DB now references only the unique-slide images
  3. verify the DB            -> every segment's frame exists, belongs to this asset, every image is on disk
  4. pipeline `prune-frames`  -> removes the now unreferenced redundant frame images (derived data only;
                                 the original video is never touched)
"""
from __future__ import annotations

import json
import os
import subprocess

from dso_contracts.models import ErrorCode

from . import db, ingest, settings
from .errors import ApiError


def _pipeline(*args: str) -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(settings.PIPELINE_CWD), env.get("PYTHONPATH")) if p)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    p = subprocess.run([settings.PIPELINE_PYTHON, "-m", "dso_pipeline", *args], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env,
                       cwd=settings.PIPELINE_CWD if settings.PIPELINE_CWD.exists() else None)
    if p.returncode != 0:
        raise ApiError(ErrorCode.pipeline_failed, (p.stderr or p.stdout).strip()[-2000:] or f"exit {p.returncode}")
    return json.loads(p.stdout.strip().splitlines()[-1])


def verify_timeline(asset_id: str) -> dict:
    with db.read() as conn:
        frames = conn.execute("SELECT * FROM frames WHERE asset_id = ? ORDER BY t_start, id", (asset_id,)).fetchall()
        segs = conn.execute('SELECT * FROM segments WHERE asset_id = ? ORDER BY "start", id', (asset_id,)).fetchall()
        listed = {r["path"] for r in conn.execute("SELECT path FROM derived_files WHERE asset_id = ? AND kind = 'frame'",
                                                  (asset_id,))}
    ids = {f["id"]: f for f in frames}
    base = settings.DERIVED_DIR / asset_id
    problems = []
    for a, b in zip(frames, frames[1:]):
        if abs(a["t_end"] - b["t_start"]) > 1e-6:
            problems.append(f"gap/overlap {a['id']}->{b['id']}")
    for f in frames:
        if not (base / f["path"]).is_file():
            problems.append(f"missing image {f['path']}")
        if f["path"] not in listed:
            problems.append(f"image not in derived_files {f['path']}")
    for s in segs:
        f = ids.get(s["frame_id"])
        if f is None:
            problems.append(f"segment {s['id']} -> unknown frame {s['frame_id']}")
        elif not (f["t_start"] <= s["start"] < f["t_end"] or f is frames[-1]):
            problems.append(f"segment {s['id']} not inside {f['id']}")
    return {"frames": len(frames), "unique_images": len({f['path'] for f in frames}), "segments": len(segs),
            "problems": problems[:20], "problem_count": len(problems)}


def apply_unique_slides(asset_id: str, dry_run: bool = False) -> dict:
    with db.read() as conn:
        row = conn.execute("SELECT kind, status, manifest_bytes FROM assets WHERE id = ?", (asset_id,)).fetchone()
        busy = conn.execute("SELECT id FROM jobs WHERE asset_id = ? AND status IN ('queued', 'running')",
                            (asset_id,)).fetchone()
    if row is None:
        raise ApiError(ErrorCode.not_found, f"Asset {asset_id} was not found.")
    if row["kind"] != "video" or row["manifest_bytes"] is None or row["status"] != "ready":
        raise ApiError(ErrorCode.conflict, "Only a processed ('ready') recording can get the unique-slide pass.")
    if busy:
        raise ApiError(ErrorCode.conflict, f"A job for {asset_id} is running ({busy['id']}); try again when it ends.")
    out = str(settings.DERIVED_DIR / asset_id)
    audit = str(settings.DATA_DIR / "audit" / "unique-slides")
    args = ["unique-slides", "--asset-id", asset_id, "--out", out, "--audit-dir", audit]
    res = {"pass": _pipeline(*args, *(["--dry-run"] if dry_run else []))}
    if dry_run:
        return res
    ingest.ingest_manifest(asset_id)
    res["verify_before_prune"] = verify_timeline(asset_id)
    if res["verify_before_prune"]["problem_count"]:
        res["prune"] = "skipped: timeline check found problems (nothing deleted)"
        return res
    res["prune"] = _pipeline("prune-frames", "--asset-id", asset_id, "--out", out)
    ingest.reindex_asset_metadata()
    res["verify_after_prune"] = verify_timeline(asset_id)
    return res
