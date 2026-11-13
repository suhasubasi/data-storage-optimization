"""Unique-slide pass: turn the extracted key frames of a recording into ONE image per unique slide.

Why: key-frame extraction keeps a frame whenever the picture changed (pHash >= 12 OR >= 1 % of a
160x90 thumbnail changed). On talks with a live webcam picture-in-picture, the moving speaker alone
triggers the pixel rule, so the same slide is saved many times. This pass removes those repeats
WITHOUT re-running Whisper and without dropping a slide that is really different.

Rules (conservative; nothing is decided by on-screen duration alone):
  * Frames stay in time order; on-screen time of a frame = [t_start, t_end) from extraction.
  * Live-overlay mask: a pixel area that changes in >= overlay_min_change_freq of ALL consecutive
    frame pairs (a webcam box) is ignored when comparing, but only if it is one compact region of at
    most overlay_max_area_fraction of the picture. Otherwise nothing is masked.
  * Two frames show the SAME slide only if BOTH hold (outside the mask):
      - every block_px x block_px block of a 320x180 gray thumbnail has <= max_block_change_fraction
        of its pixels changed by > pixel_level (cursor, scroll dots, webcam spill: yes; a changed
        heading, a new bullet, a moved highlight: no), and
      - pHash distance of the masked picture <= max_phash_distance (tighter than extraction's 12).
  * A frame is merged into the slide on screen before it if it is the same; otherwise, if it is the
    same as an earlier unique slide (the talk went back to it), it reuses that image; otherwise it
    becomes a NEW unique slide, however short it was on screen.
  * Each unique slide keeps the member frame that was on screen longest (earliest on a tie).

Output: a timeline of contiguous runs. Each run keeps the id of its FIRST source frame (so ids stay
'f<n>' and time-ordered), points at the unique slide's image, and lists its source_frames, so the
choice is auditable. A segment's frame_id = run on screen when the segment starts (same rule as before).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .common import phash_hex

METHOD = "masked-block-diff+masked-phash v1"
DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "thumb_width": 320,
    "thumb_height": 180,
    "block_px": 20,
    "pixel_level": 24,
    "max_block_change_fraction": 0.05,
    "max_phash_distance": 6,
    "overlay_min_change_freq": 0.3,
    "overlay_min_hot_fraction": 0.002,
    "overlay_max_area_fraction": 0.15,
    "overlay_margin_px": 8,
    "overlay_min_frames": 30,
}


def config(thresholds: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    cfg.update({k: v for k, v in (thresholds.get("unique_slides") or {}).items() if not k.startswith("_")})
    return cfg


def _hd(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def frame_for(t: float, frames: list[dict[str, Any]]) -> str | None:
    """Frame on screen at time t: t_start <= t < t_end (last frame if t is at/after the end)."""
    if not frames:
        return None
    for fr in frames:
        if fr["t_start"] <= t < fr["t_end"]:
            return fr["id"]
    return frames[-1]["id"] if t >= frames[-1]["t_start"] else frames[0]["id"]


def _thumbs(paths: list[Path], w: int, h: int) -> np.ndarray:
    out = np.empty((len(paths), h, w), dtype=np.int16)
    for i, p in enumerate(paths):
        with Image.open(p) as im:
            out[i] = np.asarray(im.convert("L").resize((w, h), Image.BILINEAR), dtype=np.int16)
    return out


def detect_overlay(th: np.ndarray, cfg: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any] | None]:
    """Mask (True = ignore) for one compact, constantly changing area such as a webcam box."""
    n, h, w = th.shape
    mask = np.zeros((h, w), dtype=bool)
    if n < int(cfg["overlay_min_frames"]):
        return mask, None
    lvl = int(cfg["pixel_level"])
    freq = np.zeros((h, w), dtype=np.float64)
    for i in range(n - 1):
        freq += np.abs(th[i + 1] - th[i]) > lvl
    freq /= max(1, n - 1)
    hot = freq >= float(cfg["overlay_min_change_freq"])
    if hot.mean() < float(cfg["overlay_min_hot_fraction"]):
        return mask, None
    from scipy import ndimage  # dependency of imagehash

    lab, count = ndimage.label(ndimage.binary_dilation(hot, iterations=2))
    if count == 0:
        return mask, None
    sizes = ndimage.sum(hot, lab, range(1, count + 1))
    big = 1 + int(np.argmax(sizes))
    ys, xs = np.nonzero(lab == big)
    m = int(cfg["overlay_margin_px"])
    x0, x1 = max(0, int(xs.min()) - m), min(w - 1, int(xs.max()) + m)
    y0, y1 = max(0, int(ys.min()) - m), min(h - 1, int(ys.max()) + m)
    area = (x1 - x0 + 1) * (y1 - y0 + 1) / (w * h)
    if area > float(cfg["overlay_max_area_fraction"]):
        return mask, None  # not a small overlay -> compare the whole picture (conservative)
    mask[y0:y1 + 1, x0:x1 + 1] = True
    return mask, {
        "box": [round(x0 / w, 4), round(y0 / h, 4), round((x1 + 1) / w, 4), round((y1 + 1) / h, 4)],
        "area_fraction": round(area, 4),
    }


def _masked_phash(path: Path, box: list[float] | None, hash_size: int) -> str:
    with Image.open(path) as im:
        img = im.convert("RGB")
    if box:
        W, H = img.size
        a = np.asarray(img).copy()
        a[int(box[1] * H):int(np.ceil(box[3] * H)), int(box[0] * W):int(np.ceil(box[2] * W))] = 128
        img = Image.fromarray(a)
    return phash_hex(img, hash_size)


class _Comparer:
    def __init__(self, th: np.ndarray, mask: np.ndarray, cfg: dict[str, Any]):
        self.th, self.keep = th, ~mask
        n, h, w = th.shape
        c = int(cfg["block_px"])
        self.c, self.gh, self.gw = c, h // c, w // c
        self.h, self.w = self.gh * c, self.gw * c
        self.lvl = int(cfg["pixel_level"])
        kc = self.keep[: self.h, : self.w].reshape(self.gh, c, self.gw, c).sum((1, 3)).astype(np.float64)
        self.valid = kc >= 0.5 * c * c  # blocks mostly outside the mask
        self.kc = np.maximum(kc, 1)

    def block_max(self, i: int, js: list[int]) -> np.ndarray:
        """Largest changed-pixel share over all valid blocks, frame i vs each frame in js."""
        if not js:
            return np.zeros(0)
        a = self.th[i, : self.h, : self.w]
        b = self.th[js, : self.h, : self.w]
        d = (np.abs(b - a) > self.lvl) & self.keep[: self.h, : self.w]
        s = d.reshape(len(js), self.gh, self.c, self.gw, self.c).sum((2, 4)) / self.kc
        s[:, ~self.valid] = 0
        return s.reshape(len(js), -1).max(axis=1)


def plan(frames: list[dict[str, Any]], base: Path, cfg: dict[str, Any], hash_size: int = 8) -> dict[str, Any]:
    """Decide the unique slides for time-ordered key frames whose images live under base/<path>."""
    frames = sorted(frames, key=lambda f: (f["t_start"], f["id"]))
    n = len(frames)
    if n == 0:
        return {"runs": [], "slides": [], "overlay": None}
    paths = [base / f["path"] for f in frames]
    th = _thumbs(paths, int(cfg["thumb_width"]), int(cfg["thumb_height"]))
    mask, overlay = detect_overlay(th, cfg)
    mph = [_masked_phash(p, overlay["box"] if overlay else None, hash_size) for p in paths]
    cmp = _Comparer(th, mask, cfg)
    max_blk, max_ph = float(cfg["max_block_change_fraction"]), int(cfg["max_phash_distance"])

    seeds: list[int] = []        # first frame of each unique slide (comparison anchor, avoids drift)
    members: list[list[int]] = []
    runs: list[dict[str, Any]] = []  # {"slide": k, "frames": [idx...]}
    cur: int | None = None
    for i in range(n):
        if cur is not None:
            if _hd(mph[seeds[cur]], mph[i]) <= max_ph and cmp.block_max(seeds[cur], [i])[0] <= max_blk:
                members[cur].append(i)
                runs[-1]["frames"].append(i)
                continue
        cand = [k for k in range(len(seeds)) if k != cur and _hd(mph[seeds[k]], mph[i]) <= max_ph]
        hit = None
        if cand:
            bm = cmp.block_max(i, [seeds[k] for k in cand])
            ok = [(float(v), k) for v, k in zip(bm, cand) if v <= max_blk]
            if ok:
                hit = min(ok)[1]  # closest earlier slide
        if hit is None:
            seeds.append(i)
            members.append([i])
            hit = len(seeds) - 1
        else:
            members[hit].append(i)
        if runs and runs[-1]["slide"] == hit:
            runs[-1]["frames"].append(i)
        else:
            runs.append({"slide": hit, "frames": [i]})
        cur = hit

    dur = [max(0.0, float(f["t_end"]) - float(f["t_start"])) for f in frames]
    slides = []
    for k, mem in enumerate(members):
        rep = max(mem, key=lambda j: (dur[j], -j))
        slides.append({
            "slide": k + 1, "representative": frames[rep]["id"], "path": frames[rep]["path"],
            "seconds_on_screen": round(sum(dur[j] for j in mem), 3),
            "members": [frames[j]["id"] for j in mem],
        })
    out_runs = []
    for r in runs:
        fs = [frames[j] for j in r["frames"]]
        out_runs.append({
            "id": fs[0]["id"], "t_start": fs[0]["t_start"], "t_end": fs[-1]["t_end"], "slide": r["slide"] + 1,
            "source_frames": [f["id"] for f in fs],
        })
    return {"runs": out_runs, "slides": slides, "overlay": overlay}


def apply(frames: list[dict[str, Any]], base: Path, cfg: dict[str, Any], hash_size: int = 8) -> dict[str, Any]:
    """Plan + build the new manifest frame list. Does not touch any file."""
    by_id = {f["id"]: f for f in frames}
    p = plan(frames, base, cfg, hash_size)
    slide = {s["slide"]: s for s in p["slides"]}
    new_frames = []
    for r in p["runs"]:
        rep = by_id[slide[r["slide"]]["representative"]]
        new_frames.append({
            "id": r["id"], "t_start": r["t_start"], "t_end": r["t_end"], "path": rep["path"],
            "bytes": rep["bytes"], "phash": rep["phash"], "matched_slide": None,
            "slide": r["slide"], "source_frames": r["source_frames"],
        })
    keep_paths = sorted({s["path"] for s in p["slides"]})
    drop_paths = sorted({f["path"] for f in frames} - set(keep_paths))
    info = {
        "method": METHOD,
        "source_frame_count": len(frames),
        "unique_slide_count": len(p["slides"]),
        "run_count": len(p["runs"]),
        "source_frame_bytes": sum(f["bytes"] for f in {f["path"]: f for f in frames}.values()),
        "unique_slide_bytes": sum(by_id[s["representative"]]["bytes"] for s in p["slides"]),
        "overlay_mask": p["overlay"],
        "params": {k: cfg[k] for k in DEFAULTS if k != "enabled"},
    }
    return {"frames": new_frames, "slides": p["slides"], "keep_paths": keep_paths, "drop_paths": drop_paths,
            "info": info}
