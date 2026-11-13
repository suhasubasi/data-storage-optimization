"""MP4 -> compressed key frames (WebP, tied to timestamps) + local timed transcript, linked by time.

Key frames: ffmpeg samples the video at video.sample_fps (scaled to max frame_max_width_px wide) and
streams raw frames through a pipe (no temp images). A frame is kept when, versus the LAST KEPT frame,
its pHash distance >= frame_change_min_phash_distance OR >= frame_change_min_pixel_fraction of a
160x90 gray thumbnail changed by > frame_change_pixel_level; it is saved as WebP. The image we hash is exactly
the image we keep, so time and picture always match. Each kept frame covers [t_start, t_end)
(t_end = next kept frame or video end). A segment's frame_id = frame on screen when the segment
STARTS, so "as you see here" points at the right slide.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Iterator

import numpy as np
from PIL import Image

from .common import Status, phash_distance, phash_file, phash_hex, write_json_atomic
from .transcribe import transcribe


_THUMB = (160, 90)


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if p.returncode != 0:
        tail = (p.stderr or "").strip().splitlines()[-5:]
        raise RuntimeError(f"{cmd[0]} failed: " + " | ".join(tail))
    return p


def probe(path: Path) -> dict[str, Any]:
    p = _run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    return json.loads(p.stdout)


def _duration(info: dict[str, Any]) -> float:
    vals = [info.get("format", {}).get("duration")] + [s.get("duration") for s in info.get("streams", [])]
    for v in vals:
        try:
            if v is not None and float(v) > 0:
                return float(v)
        except ValueError:
            pass
    return 0.0


def _scaled_size(info: dict[str, Any], max_w: int) -> tuple[int, int] | None:
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if not v or not v.get("width") or not v.get("height"):
        return None
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list") or []:
        if "rotation" in sd:
            rot = abs(int(sd["rotation"])) % 180
    if rot == 90:  # ffmpeg auto-rotates, so the output is portrait
        w, h = h, w
    out_w = min(max_w, w)
    out_w -= out_w % 2
    out_h = max(2, int(round(h * out_w / w / 2)) * 2)
    return out_w, out_h


def _gray_thumb(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L").resize(_THUMB, Image.BILINEAR), dtype=np.int16)


def _key_frames(input_path: Path, size: tuple[int, int], fps: float, min_dist: int, hash_size: int,
                min_pixel_fraction: float, pixel_level: int) -> Iterator[tuple[float, Image.Image]]:
    """Yield (t_seconds, image) for every kept frame. The first frame is always kept.

    A frame counts as a NEW slide/scene if, compared with the last kept frame,
      pHash distance >= min_dist                                  (layout / picture changed), OR
      share of pixels changed by > pixel_level (160x90 gray) >= min_pixel_fraction  (text changed).
    The second rule exists because same-template slides (same background, different text) often have
    a pHash distance below 12 and would otherwise be merged into one frame.
    """
    w, h = size
    frame_bytes = w * h * 3
    cmd = [
        "ffmpeg", "-nostdin", "-v", "error", "-i", str(input_path), "-an",
        "-vf", f"fps={fps},scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    last: str | None = None
    last_thumb: np.ndarray | None = None
    k = 0
    try:
        assert proc.stdout is not None
        while True:
            buf = proc.stdout.read(frame_bytes)
            if len(buf) < frame_bytes:
                break
            img = Image.frombytes("RGB", (w, h), buf)
            hsh = phash_hex(img, hash_size)
            thumb = _gray_thumb(img)
            if (
                last is None
                or phash_distance(hsh, last) >= min_dist
                or (min_pixel_fraction > 0 and float((np.abs(thumb - last_thumb) > pixel_level).mean()) >= min_pixel_fraction)
            ):
                last, last_thumb = hsh, thumb
                yield round(k / fps, 3), img
            k += 1
    finally:
        if proc.stdout:
            proc.stdout.close()
        err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
        rc = proc.wait()
    if rc != 0 and k == 0:
        raise RuntimeError("ffmpeg frame sampling failed: " + " | ".join(err.strip().splitlines()[-5:]))


def frame_for(t: float, frames: list[dict[str, Any]]) -> str | None:
    """Frame on screen at time t: t_start <= t < t_end (last frame if t is at/after the end)."""
    if not frames:
        return None
    for fr in frames:
        if fr["t_start"] <= t < fr["t_end"]:
            return fr["id"]
    return frames[-1]["id"] if t >= frames[-1]["t_start"] else frames[0]["id"]


def process_video(input_path: Path, out_dir: Path, thresholds: dict[str, Any], status: Status) -> dict[str, Any]:
    vcfg = thresholds.get("video", {})
    fps = float(vcfg.get("sample_fps", 1))
    min_dist = int(vcfg.get("frame_change_min_phash_distance", 12))
    min_pix = float(vcfg.get("frame_change_min_pixel_fraction", 0.01))
    pix_level = int(vcfg.get("frame_change_pixel_level", 24))
    max_w = int(vcfg.get("frame_max_width_px", 1280))
    fmt = vcfg.get("frame_format", "webp")
    hash_size = int(thresholds.get("phash", {}).get("hash_size", 8))
    warnings: list[str] = []

    status.progress("probing", 0.0)
    info = probe(input_path)
    duration = _duration(info)
    streams = info.get("streams", [])
    has_video = any(s.get("codec_type") == "video" for s in streams)
    has_audio = any(s.get("codec_type") == "audio" for s in streams)
    tags = {k.lower(): v for k, v in (info.get("format", {}).get("tags") or {}).items()}
    if not has_video and not has_audio:
        raise RuntimeError("no video or audio stream found (not a playable MP4?)")

    frames: list[dict[str, Any]] = []
    derived: list[dict[str, Any]] = []
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    size = _scaled_size(info, max_w) if has_video else None
    if size:
        status.progress("extracting key frames", 0.05)
        kept: list[tuple[float, Path]] = []
        for t, img in _key_frames(input_path, size, fps, min_dist, hash_size, min_pix, pix_level):
            dest = frames_dir / f"f{len(kept) + 1}.{fmt}"
            img.save(dest, format=fmt.upper(), quality=75, method=4)
            kept.append((t, dest))
            if duration > 0:
                status.progress("extracting key frames", 0.05 + 0.25 * min(t / duration, 1.0))
        end = duration if duration > 0 else (kept[-1][0] + 1.0 / fps if kept else 0.0)
        for i, (t, dest) in enumerate(kept):
            rel = f"frames/{dest.name}"
            nbytes = dest.stat().st_size
            t_end = kept[i + 1][0] if i + 1 < len(kept) else max(end, t)
            frames.append({
                "id": f"f{i + 1}",
                "t_start": t,
                "t_end": round(t_end, 3),
                "path": rel,
                "bytes": nbytes,
                "phash": phash_file(dest, hash_size),  # hash of the kept file on disk
                "matched_slide": None,  # STRETCH, always null in P0
            })
            derived.append({"path": rel, "bytes": nbytes, "kind": "frame"})
        if not frames:
            warnings.append("video stream had no decodable frames")
    else:
        warnings.append("no video stream found; no key frames")

    result = None
    if has_audio:
        # Temp WAV lives in a temp dir inside out_dir (same disk); always deleted, never listed.
        with tempfile.TemporaryDirectory(prefix=".tmp-", dir=out_dir) as tmpname:
            wav = Path(tmpname) / "audio.wav"
            status.progress("extracting audio", 0.3)
            _run(["ffmpeg", "-nostdin", "-v", "error", "-y", "-i", str(input_path), "-vn",
                  "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)])
            status.progress("transcribing", 0.35)
            result = transcribe(wav, duration, thresholds,
                                lambda p: status.progress("transcribing", 0.35 + 0.6 * p))
    else:
        warnings.append("no audio stream found; transcript is empty")

    segments: list[dict[str, Any]] = []
    if result is not None:
        for i, (s, e, text) in enumerate(result.segments):
            segments.append({
                "id": f"s{i + 1}", "start": s, "end": max(e, s), "text": text,
                "frame_id": frame_for(s, frames), "speaker": None,
            })
        if not segments:
            warnings.append("no speech detected")

    language = result.language if result else None
    model_label = result.model_label if result else None

    status.progress("writing transcript", 0.97)
    transcript_rel = "transcript.json"
    write_json_atomic(out_dir / transcript_rel, {
        "language": language,
        "model": model_label,
        "duration_seconds": round(duration, 3),
        "segments": segments,
    })
    derived.insert(0, {"path": transcript_rel, "bytes": (out_dir / transcript_rel).stat().st_size, "kind": "transcript"})

    metadata = {
        "title": (tags.get("title") or "").strip() or None,
        "author": (tags.get("artist") or tags.get("author") or "").strip() or None,
        "doc_number": None,
        "revision": None,
        "date": (tags.get("creation_time") or tags.get("date") or "").strip() or None,
        "language": language,
        "duration_seconds": round(duration, 3),
    }
    return {
        "metadata": metadata,
        "segments": segments,
        "frames": frames,
        "slides": [],
        "derived_files": derived,
        "model": model_label,
        "frame_threshold": min_dist,
        "warnings": warnings,
    }
