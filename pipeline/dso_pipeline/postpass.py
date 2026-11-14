"""Unique-slide pass on an ALREADY processed recording (no re-transcription, original untouched).

Two separate steps so the live app never points at a missing picture:
  1. `unique-slides`: reads manifest.json + frames/, writes the remapped transcript.json and then
     manifest.json (atomically, last). No file is deleted. The previous manifest and the full
     decision list are saved under --audit-dir.
  2. `prune-frames`: only after the backend has ingested the new manifest. Removes frame images in
     frames/ that the CURRENT manifest no longer references, after checking every referenced image
     is present with the right size and SHA-256. Never touches anything outside <out>/frames/.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dso_contracts.models import Manifest

from . import diarize, unique_slides
from .common import load_thresholds, sha256_file, write_json_atomic

IMAGE_SUFFIXES = {".webp", ".png", ".jpg", ".jpeg"}


class PostPassError(RuntimeError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _load(out_dir: Path, asset_id: str) -> dict[str, Any]:
    mp = out_dir / "manifest.json"
    if not mp.is_file():
        raise PostPassError(f"no manifest.json in {out_dir}")
    raw = json.loads(mp.read_text(encoding="utf-8"))
    Manifest.model_validate(raw)
    if raw["asset_id"] != asset_id:
        raise PostPassError(f"manifest is for {raw['asset_id']}, expected {asset_id}")
    return raw


def _check_frame_files(out_dir: Path, m: dict[str, Any]) -> dict[str, str]:
    """Every frame image the manifest lists must exist with the listed size. Returns path -> sha256."""
    listed = {d["path"]: d["bytes"] for d in m["derived_files"]}
    shas: dict[str, str] = {}
    for f in m["frames"]:
        p = out_dir / f["path"]
        if not p.is_file():
            raise PostPassError(f"frame image missing: {f['path']}")
        size = p.stat().st_size
        if size != f["bytes"] or listed.get(f["path"]) != size:
            raise PostPassError(f"frame image size does not match manifest: {f['path']}")
        if f["path"] not in shas:
            shas[f["path"]] = sha256_file(p)
    return shas


def run_unique_slides(asset_id: str, out_dir: Path, audit_dir: Path | None = None,
                      dry_run: bool = False, force: bool = False) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    m = _load(out_dir, asset_id)
    if m["kind"] != "video":
        raise PostPassError("unique-slide pass is for recordings (kind 'video') only")
    prev_us = (m["pipeline"] or {}).get("unique_slides")
    if prev_us and not force:
        raise PostPassError("unique-slide pass was already applied to this manifest")
    if not m["frames"]:
        raise PostPassError("this recording has no key frames")
    shas = _check_frame_files(out_dir, m)

    cfg = unique_slides.config(load_thresholds())
    hash_size = int(load_thresholds().get("phash", {}).get("hash_size", 8))
    r = unique_slides.apply(m["frames"], out_dir, cfg, hash_size)
    runs = r["frames"]

    # Remap segments: frame on screen when the segment STARTS. Text and times are copied unchanged.
    segments = [{**s, "frame_id": unique_slides.frame_for(s["start"], runs)} for s in m["segments"]]

    # Integrity checks before anything is written.
    ids = {f["id"] for f in runs}
    assert len(ids) == len(runs), "run ids must be unique"
    for a, b in zip(runs, runs[1:]):
        if not (a["t_start"] < b["t_start"] and abs(a["t_end"] - b["t_start"]) < 1e-6):
            raise PostPassError(f"time ranges not contiguous at {a['id']} -> {b['id']}")
    if not runs:
        raise PostPassError("no slide image was found, so nothing was changed")
    if runs[0]["t_start"] != m["frames"][0]["t_start"] or abs(runs[-1]["t_end"] - m["frames"][-1]["t_end"]) > 1e-6:
        raise PostPassError("time ranges do not cover the same span as before")
    covered = [fid for f in runs for fid in f["source_frames"]]
    if sorted(covered) != sorted(f["id"] for f in m["frames"]):
        raise PostPassError("every original key frame must belong to exactly one time range")
    for old, new in zip(m["segments"], segments):
        if (old["id"], old["start"], old["end"], old["text"]) != (new["id"], new["start"], new["end"], new["text"]):
            raise PostPassError("transcript text/time changed (must never happen)")
        if new["frame_id"] not in ids:
            raise PostPassError(f"segment {new['id']} points at an unknown frame")

    # Flatten source_frames across re-runs so the complete original frame audit trail is preserved.
    orig_src = {f["id"]: (f.get("source_frames") or [f["id"]]) for f in m["frames"]}
    for rf in runs:
        flat: list[str] = []
        seen_ids: set[str] = set()
        for fid in rf["source_frames"]:
            for oid in orig_src.get(fid, [fid]):
                if oid not in seen_ids:
                    flat.append(oid)
                    seen_ids.add(oid)
        rf["source_frames"] = flat

    keep = set(r["keep_paths"])
    derived = [d for d in m["derived_files"] if d["kind"] != "frame" or d["path"] in keep]
    info = {**r["info"], "applied_as": "post_pass", "applied_at": _utc_now()}
    if prev_us:
        info["source_frame_count"] = max(int(prev_us.get("source_frame_count", 0)), int(info["source_frame_count"]))
        info["source_frame_bytes"] = max(int(prev_us.get("source_frame_bytes", 0)), int(info["source_frame_bytes"]))
    summary = {
        "asset_id": asset_id,
        "source_frames": info["source_frame_count"],
        "unique_slides": info["unique_slide_count"],
        "time_ranges": info["run_count"],
        "source_frame_bytes": info["source_frame_bytes"],
        "unique_slide_bytes": info["unique_slide_bytes"],
        "frames_to_prune": len(r["drop_paths"]),
        "overlay_mask": info["overlay_mask"],
        "dry_run": dry_run,
    }
    if dry_run:
        return summary

    # Remove old slide-*.webp crop paths from shas check if upgrading an already-cropped manifest.
    crop_overwritten = {f"frames/slide-{int(s['slide'])}.webp" for s in r["slides"]} if force else set()
    unique_slides.write_crops(r, out_dir, hash_size)
    runs = r["frames"]
    keep = set(r["keep_paths"])
    derived = [d for d in m["derived_files"] if d["kind"] != "frame" or d["path"] in keep]
    have = {d["path"] for d in derived}
    for rel in sorted(keep):
        if rel not in have:
            derived.append({"path": rel, "bytes": (out_dir / rel).stat().st_size, "kind": "frame"})
    info = {**r["info"], "applied_as": "post_pass", "applied_at": info["applied_at"]}
    if prev_us:
        info["source_frame_count"] = max(int(prev_us.get("source_frame_count", 0)), int(info["source_frame_count"]))
        info["source_frame_bytes"] = max(int(prev_us.get("source_frame_bytes", 0)), int(info["source_frame_bytes"]))
    summary["unique_slide_bytes"] = info["unique_slide_bytes"]
    summary["frames_to_prune"] = len(r["drop_paths"])

    # Audit trail first (outside the derived folder, so it never mixes into derived bytes).
    if audit_dir is not None:
        audit_dir.mkdir(parents=True, exist_ok=True)
        stamp = info["applied_at"].replace(":", "").replace("-", "").replace(".", "")
        shutil.copyfile(out_dir / "manifest.json", audit_dir / f"{asset_id}-manifest-before-{stamp}.json")
        write_json_atomic(audit_dir / f"{asset_id}-unique-slides-{stamp}.json", {
            "summary": summary, "info": info, "slides": r["slides"],
            "frame_sha256_before": shas, "drop_paths": r["drop_paths"],
            "verification": r["verification"],
        })

    transcript_path = out_dir / "transcript.json"
    if transcript_path.is_file():
        t = json.loads(transcript_path.read_text(encoding="utf-8"))
        t_by_id = {s["id"]: s for s in t.get("segments", [])}
        if [s["id"] for s in t.get("segments", [])] != [s["id"] for s in segments] or any(
                t_by_id[s["id"]]["text"] != s["text"] for s in segments):
            raise PostPassError("transcript.json does not match manifest segments")
        t["segments"] = segments
        write_json_atomic(transcript_path, t)
    for d in derived:  # re-measure (transcript.json changed: only frame_id references)
        d["bytes"] = (out_dir / d["path"]).stat().st_size
    new_frames = []
    for f in runs:
        f = dict(f)
        f["bytes"] = (out_dir / f["path"]).stat().st_size
        new_frames.append(f)

    new = {**m, "segments": segments, "frames": new_frames, "derived_files": derived,
           "pipeline": {**m["pipeline"], "unique_slides": info}}
    Manifest.model_validate(new)
    write_json_atomic(out_dir / "manifest.json", new)  # LAST
    for p in keep:
        if p in shas and p not in crop_overwritten and sha256_file(out_dir / p) != shas[p]:
            raise PostPassError(f"kept image changed on disk: {p}")
    summary["manifest_bytes"] = (out_dir / "manifest.json").stat().st_size
    return summary


def prune_frames(asset_id: str, out_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    m = _load(out_dir, asset_id)
    if not (m["pipeline"] or {}).get("unique_slides"):
        raise PostPassError("refusing to prune: the unique-slide pass has not been applied to this manifest")
    _check_frame_files(out_dir, m)
    referenced = {f["path"] for f in m["frames"]} | {d["path"] for d in m["derived_files"]}
    frames_dir = out_dir / "frames"
    removed, removed_bytes = [], 0
    if frames_dir.is_dir():
        for p in sorted(frames_dir.iterdir()):
            rel = f"frames/{p.name}"
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in IMAGE_SUFFIXES and rel not in referenced:
                removed.append(rel)
                removed_bytes += p.stat().st_size
                if not dry_run:
                    p.unlink()
    return {"asset_id": asset_id, "removed_files": len(removed), "removed_bytes": removed_bytes,
            "kept_files": len({f["path"] for f in m["frames"]}), "dry_run": dry_run}


def run_speakers(asset_id: str, video_path: Path, out_dir: Path, dry_run: bool = False) -> dict[str, Any]:
    """Identify speakers ('Speaker 1', 'Speaker 2', ...) as text labels without re-running Whisper or saving audio."""
    out_dir = out_dir.resolve()
    video_path = video_path.resolve()
    if not video_path.is_file():
        raise PostPassError(f"original video not found: {video_path}")
    m = _load(out_dir, asset_id)
    if m["kind"] != "video":
        raise PostPassError("speakers pass is for recordings (kind 'video') only")
    if not m["segments"]:
        return {"asset_id": asset_id, "speaker_count": 0, "speakers": [], "dry_run": dry_run}

    with tempfile.TemporaryDirectory(prefix=".tmp-spk-", dir=out_dir) as tmpname:
        wav = Path(tmpname) / "audio.wav"
        p = subprocess.run(
            ["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(video_path), "-vn",
             "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        if p.returncode != 0:
            raise PostPassError(f"ffmpeg audio extraction failed: {(p.stderr or '').strip()[-400:]}")
        segments = [dict(s) for s in m["segments"]]
        diar = diarize.diarize_wav(
            wav, segments, video_path=video_path, include_roles=True
        )
        if dry_run:
            return {"asset_id": asset_id, "speaker_count": len(diar["speakers"]),
                    "speakers": diar["speakers"], "dry_run": True}

    # Remove any legacy voice-sample WAVs so only text speaker labels remain.
    audio_dir = out_dir / "audio"
    if audio_dir.is_dir():
        for old in audio_dir.glob("speaker-*.wav"):
            old.unlink()
        try:
            audio_dir.rmdir()
        except OSError:
            pass

    transcript_path = out_dir / "transcript.json"
    if transcript_path.is_file():
        t = json.loads(transcript_path.read_text(encoding="utf-8"))
        t["segments"] = segments
        t["speakers"] = diar["speakers"]
        if diar.get("diarization") is not None:
            t["diarization"] = diar["diarization"]
        write_json_atomic(transcript_path, t)

    derived = [d for d in m["derived_files"] if d["kind"] != "audio"]
    for d in derived:
        d["bytes"] = (out_dir / d["path"]).stat().st_size

    new = {**m, "segments": segments, "derived_files": derived}
    Manifest.model_validate(new)
    write_json_atomic(out_dir / "manifest.json", new)
    return {
        "asset_id": asset_id,
        "speaker_count": len(diar["speakers"]),
        "speakers": diar["speakers"],
        "manifest_bytes": (out_dir / "manifest.json").stat().st_size,
        "dry_run": False,
    }
