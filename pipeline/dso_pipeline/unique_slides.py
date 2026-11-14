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
        heading, a new bullet, a moved highlight: no). A block partly under the mask is judged on its
        unmasked pixels only; a partial block at the right/bottom edge is checked too, and
      - pHash distance of the masked picture <= max_phash_distance (tighter than extraction's 12).
  * A frame is merged into the slide on screen before it if it is the same; otherwise, if it is the
    same as an earlier unique slide (the talk went back to it), it reuses that image; otherwise it
    becomes a NEW unique slide, however short it was on screen.
  * Each unique slide keeps the member frame that was on screen longest (earliest on a tie), but only
    if that image passes both checks against EVERY member; otherwise it keeps the slide's first frame
    (which every member was matched against). The per-member check is returned as "verification".

Output: a timeline of contiguous runs. Each run keeps the id of its FIRST source frame (so ids stay
'f<n>' and time-ordered), points at the unique slide's image, and lists its source_frames, so the
choice is auditable. A segment's frame_id = run on screen when the segment starts (same rule as before).
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image

from .common import phash_hex

METHOD = "masked-block-diff+masked-phash v2 (representative verified)"
METHOD_V3 = "slides-only v3: shared-screen crop, document test, block diff, last frame, zero duplicates"
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
    # v3 "slides_only" (default). "v2" = the older pass that keeps every distinct picture (faces too).
    "mode": "slides_only",
    "v3_width": 640,
    "v3_height": 360,
    "v3_block_px": 16,
    "v3_layout_edge_min_frames": 0.6,
    "v3_live_window_s": 15.0,
    "v3_live_min_pairs": 4,
    "v3_live_min_change_freq": 0.5,
    "v3_max_live_fraction": 0.45,
    "v3_min_sharpness": 0.20,
    "v3_return_max_phash_distance": 12,
    # Document test on the shared-screen area. Slides span solid/gradient backgrounds, clean
    # text/code/diagrams, strong panels with text, and half- or hero-photo slides with crisp edges.
    "v3_min_dominant": 0.15,
    "v3_min_ink": 0.006,
    "v3_max_ink": 0.42,
    "v3_max_photo": 0.70,
    "v3_flat_min_fraction": 0.88,
    "v3_flat_max_smooth": 0.018,
    "v3_flat_min_ink": 0.011,
    "v3_flat_sparse_min_photo": 0.03,
    "v3_ui_min_dominant": 0.55,
    "v3_ui_max_smooth": 0.055,
    "v3_ui_min_ink": 0.019,
    "v3_ui_min_ink60": 0.010,
    "v3_panel_min_dominant": 0.50,
    "v3_panel_min_ink": 0.028,
    "v3_panel_min_ink80": 0.013,
    "v3_photo_min_ink60": 0.023,
    "v3_photo_min_ink80": 0.013,
    "v3_fullframe_photo_min_ink60": 0.028,
    "v3_fullframe_photo_min_ink80": 0.014,
    "v3_pip_photo_min_ink60": 0.021,
    "v3_pip_photo_min_ink80": 0.011,
    "v3_pip_wire_min_ink40": 0.065,
    # Localized corner/edge PIP overlay verification before masking _is_document.
    "v3_overlay_max_edge_dist": 0.12,
    "v3_overlay_max_bg_freq": 0.15,
    "v3_overlay_min_contrast": 2.5,
    "v3_overlay_block_fraction": 0.25,
    # Rail learned from the clear frames, then applied where the same edge is faint.
    "v3_rail_learn_strength": 0.40,
    "v3_rail_apply_strength": 0.22,
    "v3_rail_min_votes": 4,
    "v3_rail_min_agree": 0.60,
    # Pull the crop this far inside the rail so a moving face on the edge
    # is not part of the slide. 2% is about 12 px on the comparison picture.
    "v3_rail_gutter": 0.02,
    # A cursor or a meeting-control icon is smaller than a changed word.
    # Differences smaller than this share of the picture are ignored.
    "v3_ignore_speck_fraction": 0.001,
    # Embedded video playback, ad bursts, & fleeting transitions inside camera/video churn.
    "v3_video_churn_window_s": 20.0,
    "v3_video_churn_min_frames": 10,
    "v3_video_churn_max_member_s": 10.0,
    "v3_churn_burst_window_s": 15.0,
    "v3_churn_burst_max_frame_s": 4.5,
    "v3_churn_burst_cut_fraction": 0.15,
    "v3_churn_burst_min_cuts": 3,
    "v3_churn_burst_min_fast_fraction": 0.75,
    "v3_churn_burst_nondoc_window_s": 22.0,
    "v3_churn_burst_min_nondoc": 2,
    "v3_churn_burst_hi_cuts": 12,
    "v3_churn_burst_min_shot_diff": 0.02,
    # Short progressive build-in steps / brief pop-over before a settled anchor slide.
    "v3_build_max_seconds": 4.0,
    "v3_build_min_anchor_seconds": 45.0,
    "v3_build_min_same_blocks": 0.80,
    "v3_popover_min_same_blocks": 0.65,
    "v3_crop_quality": 75,
    "v3_crop_max_width": 1280,
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
        n, h, w = th.shape
        c = int(cfg["block_px"])
        if c < 1:
            raise ValueError("block_px must be positive")
        self.c, self.gh, self.gw = c, (h + c - 1) // c, (w + c - 1) // c
        self.h, self.w = self.gh * c, self.gw * c
        self.th = np.pad(th, ((0, 0), (0, self.h - h), (0, self.w - w)))
        self.keep = np.pad(~mask, ((0, self.h - h), (0, self.w - w)), constant_values=False)
        self.lvl = int(cfg["pixel_level"])
        kc = self.keep[: self.h, : self.w].reshape(self.gh, c, self.gw, c).sum((1, 3)).astype(np.float64)
        self.valid = kc > 0  # every unmasked pixel counts, including partial edge blocks
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

    def checks(rep: int, mem: list[int]):
        """(member, block change, pHash distance) of every member against rep, in chunks (bounded memory)."""
        for start in range(0, len(mem), 64):
            chunk = mem[start:start + 64]
            for j, block in zip(chunk, cmp.block_max(rep, chunk)):
                yield j, float(block), _hd(mph[rep], mph[j])

    slides = []
    verification = []
    for k, mem in enumerate(members):
        rep = max(mem, key=lambda j: (dur[j], -j))
        # "Same slide" is not transitive: B ~ A and C ~ A do not make B ~ C. Every member was checked
        # against the seed (first frame), so if the longest-shown frame does not cover every member,
        # the seed's image is kept instead. Then every member is re-checked against the final image.
        if rep != seeds[k] and any(b > max_blk or ph > max_ph for _, b, ph in checks(rep, mem)):
            rep = seeds[k]
        for j, b, ph in checks(rep, mem):
            if b > max_blk or ph > max_ph:  # cannot happen (the seed matched every member); never hide it
                raise ValueError(f"unique slide {k + 1}: image {frames[rep]['id']} does not cover {frames[j]['id']}")
            verification.append({"frame_id": frames[j]["id"], "representative": frames[rep]["id"],
                                 "max_block_change_fraction": round(b, 4), "phash_distance": ph})
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
    return {"runs": out_runs, "slides": slides, "overlay": overlay, "verification": verification}


# ---------------------------------------------------------------------------------------------
# v3 "slides only". Keeps ONLY slides and documents. Face cams, webcam tiles and stage cameras
# are not kept.
#   1. Per frame, find the shared-screen area: drop black letterbox bars and a narrow side rail
#      (the participant strip). When many clear frames agree on that rail, a darker slide
#      whose edge is only faint is cropped there too. Compare and store only that area.
#   2. Document test: the area must be mostly one paper color, with some text, and not a photograph.
#      A full-frame camera (no rail to remove) is kept only when it is a title card.
#      A face close-up or a lobby of face tiles is not kept.
#   3. A block that keeps changing while the rest of the picture stays (cursor, small embedded video)
#      is ignored. If most of the area is moving, the frame is video and is dropped.
#   4. Same slide = every other 16 px block has <= 5 % of its pixels changed by > 24. A changed
#      bullet or number is a new slide. Walk in time order. Compare with the slide on screen first,
#      then with every earlier slide. Going back reuses the earlier image. Never store it twice.
#   5. The kept image is the LAST frame of that slide's first run, so a build animation ends finished.
#      It is checked against every frame of the slide. Then every kept image is compared with every
#      other one, and any duplicate pair is merged.
#   6. Time with no slide (camera only) points at the slide shown last, or the next one before the
#      first slide. The timeline stays contiguous and no camera picture is stored.
# ---------------------------------------------------------------------------------------------


def _cluster_lines(hot: np.ndarray, size: int, gap: int) -> list[int]:
    pts = [0]
    for i, on in enumerate(hot.tolist()):
        if on and (i + 1) - pts[-1] >= gap:
            pts.append(i + 1)
    if size - pts[-1] >= gap:
        pts.append(size)
    else:
        pts[-1] = size
    return pts


def _content_well(gray: np.ndarray) -> tuple[int, int, int, int]:
    """Shared-screen rectangle: full picture, minus letterbox bars and one narrow side rail."""
    h, w = gray.shape
    f = gray.astype(np.int16)
    xs = _cluster_lines((np.abs(np.diff(f, axis=1)) > 24).mean(0) >= 0.40, w, max(4, w // 40))
    ys = _cluster_lines((np.abs(np.diff(f, axis=0)) > 24).mean(1) >= 0.40, h, max(4, h // 40))
    x0, x1, y0, y1 = 0, w, 0, h
    for a, b in zip(ys, ys[1:]):
        thin = (b - a) <= int(0.12 * h)
        if a == 0 and thin:
            bar, inner = gray[:b], gray[b:min(h, b + max(1, b - a))]
            if float(bar.mean()) < 18 and float(inner.mean()) > float(bar.mean()) + 25:
                y0 = b
        if b == h and thin:
            bar, inner = gray[a:], gray[max(0, a - max(1, b - a)):a]
            if float(bar.mean()) < 18 and float(inner.mean()) > float(bar.mean()) + 25:
                y1 = a
    for a, b in zip(xs, xs[1:]):
        width = (b - a) / w
        if not (0.06 <= width <= 0.26):
            continue
        if a == 0 and b < x1:
            rail, inner = gray[:, a:b], gray[:, b:min(w, b + (b - a))]
            if float(rail.mean()) + 12 < float(inner.mean()) or float(rail.std()) > float(inner.std()) + 8:
                x0 = max(x0, b)
        if b == w and a > x0:
            rail, inner = gray[:, a:b], gray[:, max(0, a - (b - a)):a]
            if float(rail.mean()) + 12 < float(inner.mean()) or float(rail.std()) > float(inner.std()) + 8:
                x1 = min(x1, a)
    if (x1 - x0) < int(0.40 * w) or (y1 - y0) < int(0.40 * h):
        return 0, 0, w, h
    return x0, y0, x1, y1


def _snap_well(box: tuple[int, int, int, int], w: int, h: int) -> tuple[int, int, int, int]:
    """Snap the well outward to a 1 % grid so a 1 px jitter does not shift the slide."""
    x0, y0, x1, y1 = box
    fx0, fy0, fx1, fy1 = x0 / w, y0 / h, x1 / w, y1 / h
    sx0 = int(round(math.floor(fx0 * 100) / 100 * w))
    sy0 = int(round(math.floor(fy0 * 100) / 100 * h))
    sx1 = int(round(math.ceil(fx1 * 100 - 1e-9) / 100 * w))
    sy1 = int(round(math.ceil(fy1 * 100 - 1e-9) / 100 * h))
    sx0, sy0 = max(0, sx0), max(0, sy0)
    sx1, sy1 = min(w, max(sx0 + 1, sx1)), min(h, max(sy0 + 1, sy1))
    if (sx1 - sx0) < int(0.40 * w) or (sy1 - sy0) < int(0.40 * h):
        return box
    return sx0, sy0, sx1, sy1


def _document_stats(crop: np.ndarray, valid_mask: np.ndarray | None = None) -> dict[str, float]:
    """Compute histogram, flatness, edge-ink, and smooth-photo texture features on valid pixels."""
    if valid_mask is not None and (valid_mask.shape != crop.shape or float(valid_mask.mean()) < 0.5):
        valid_mask = None
    c = crop.astype(np.int16)
    gmax = np.maximum(np.abs(np.diff(c, axis=1))[:-1, :], np.abs(np.diff(c, axis=0))[:, :-1])
    bh, bw = crop.shape[0] // 8, crop.shape[1] // 8
    blk = crop[: bh * 8, : bw * 8].reshape(bh, 8, bw, 8)
    rng = blk.max(axis=(1, 3)) - blk.min(axis=(1, 3))
    bgmax = np.maximum(
        np.abs(np.diff(blk.astype(np.int16), axis=3)).max(axis=(1, 3)),
        np.abs(np.diff(blk.astype(np.int16), axis=1)).max(axis=(1, 3)),
    )
    if valid_mask is None:
        px = crop.ravel()
        em = np.ones_like(gmax, dtype=bool)
        bm = np.ones_like(rng, dtype=bool)
    else:
        px = crop[valid_mask]
        em = valid_mask[:-1, :-1] & valid_mask[:-1, 1:] & valid_mask[1:, :-1]
        bm = valid_mask[: bh * 8, : bw * 8].reshape(bh, 8, bw, 8).all(axis=(1, 3))
    bins = np.bincount(px // 16, minlength=16)
    return {
        "dom": float(bins.max() / max(1, px.size)),
        "flat24": float((rng[bm] <= 24).mean()) if bm.any() else 0.0,
        "ink40": float((gmax[em] > 40).mean()) if em.any() else 0.0,
        "ink60": float((gmax[em] > 60).mean()) if em.any() else 0.0,
        "ink80": float((gmax[em] > 80).mean()) if em.any() else 0.0,
        "photo": float((rng[bm] > 48).mean()) if bm.any() else 0.0,
        "smooth": float(((rng > 48) & (bgmax <= 40))[bm].mean()) if bm.any() else 0.0,
    }


def _sharpness_score(gray: np.ndarray) -> float:
    """OpenCV Laplacian + Sobel acuity score for blur rejection and settled representative selection."""
    if gray.size == 0:
        return 0.0
    lap = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    grad_var = float((gx * gx + gy * gy).mean())
    denom = max(64.0, float(gray.std()) ** 2)
    return round(0.5 * (lap / denom) + 0.05 * (grad_var / denom), 4)


def _ssim_score(a: np.ndarray, b: np.ndarray, mask: np.ndarray | None = None) -> float:
    """OpenCV Gaussian-windowed structural similarity (SSIM) on unmasked pixels."""
    af, bf = a.astype(np.float64), b.astype(np.float64)
    mu1 = cv2.GaussianBlur(af, (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(bf, (11, 11), 1.5)
    s1 = cv2.GaussianBlur(af * af, (11, 11), 1.5) - mu1 * mu1
    s2 = cv2.GaussianBlur(bf * bf, (11, 11), 1.5) - mu2 * mu2
    s12 = cv2.GaussianBlur(af * bf, (11, 11), 1.5) - mu1 * mu2
    c1, c2 = 6.5025, 58.5225
    ssim_map = ((2.0 * mu1 * mu2 + c1) * (2.0 * s12 + c2)) / ((mu1 * mu1 + mu2 * mu2 + c1) * (s1 + s2 + c2))
    if mask is not None and bool((~mask).any()):
        return float(ssim_map[~mask].mean())
    return float(ssim_map.mean())


def _find_corner_pip(
    frames: list[dict[str, Any]], base: Path, cfg: dict[str, Any], load_w: int, load_h: int
) -> tuple[np.ndarray | None, list[float] | None, bool]:
    """Return (valid_canvas_mask, normalized_pip_box, is_camera_pip) using OpenCV connected components."""
    n = len(frames)
    if n < int(cfg["overlay_min_frames"]):
        return None, None, False
    tw, th_h = int(cfg["thumb_width"]), int(cfg["thumb_height"])
    thumbs = _thumbs([base / f["path"] for f in frames], tw, th_h)
    lvl = int(cfg["pixel_level"])
    freq = np.mean(np.abs(thumbs[1:] - thumbs[:-1]) > lvl, axis=0)
    hot = freq >= float(cfg["overlay_min_change_freq"])
    min_hot_px = float(cfg["overlay_min_hot_fraction"]) * (tw * th_h)
    if float(hot.sum()) < min_hot_px:
        return None, None, False

    kernel = np.ones((5, 5), dtype=np.uint8)
    dil = cv2.dilate(hot.astype(np.uint8), kernel, iterations=1)
    n_lab, labels, _, _ = cv2.connectedComponentsWithStats(dil, connectivity=8)
    if n_lab <= 1:
        return None, None, False

    m = int(cfg["overlay_margin_px"])
    max_area = float(cfg["overlay_max_area_fraction"])
    max_edge = float(cfg["v3_overlay_max_edge_dist"])
    max_bg = float(cfg["v3_overlay_max_bg_freq"])
    min_contrast = float(cfg["v3_overlay_min_contrast"])

    cands: list[tuple[float, int]] = []
    for k in range(1, n_lab):
        s = float(hot[labels == k].sum())
        if s >= min_hot_px:
            cands.append((s, k))
    cands.sort(reverse=True)
    if not cands:
        return None, None, False

    # If the single dominant moving region is a compact box in the center of the slide, reject.
    top_k = cands[0][1]
    ys0, xs0 = np.nonzero(labels == top_k)
    tx0, tx1 = max(0, int(xs0.min()) - m), min(tw - 1, int(xs0.max()) + m)
    ty0, ty1 = max(0, int(ys0.min()) - m), min(th_h - 1, int(ys0.max()) + m)
    top_area = (tx1 - tx0 + 1) * (ty1 - ty0 + 1) / (tw * th_h)
    top_edge = min(tx0 / tw, ty0 / th_h, 1.0 - (tx1 + 1) / tw, 1.0 - (ty1 + 1) / th_h)
    if top_area <= max_area and top_edge > max_edge and len(cands) == 1:
        return None, None, False

    chosen_mask = None
    chosen_box = None
    for _, k in cands:
        ys, xs = np.nonzero(labels == k)
        x0, x1 = max(0, int(xs.min()) - m), min(tw - 1, int(xs.max()) + m)
        y0, y1 = max(0, int(ys.min()) - m), min(th_h - 1, int(ys.max()) + m)
        area = (x1 - x0 + 1) * (y1 - y0 + 1) / (tw * th_h)
        if area > max_area:
            continue
        b = [round(x0 / tw, 4), round(y0 / th_h, 4), round((x1 + 1) / tw, 4), round((y1 + 1) / th_h, 4)]
        edge_dist = min(b[0], b[1], 1.0 - b[2], 1.0 - b[3])
        if edge_dist > max_edge:
            continue
        ov_mask = np.zeros((th_h, tw), dtype=bool)
        ov_mask[y0 : y1 + 1, x0 : x1 + 1] = True
        bg = freq[~ov_mask]
        fg = freq[ov_mask]
        if bg.size == 0 or fg.size == 0:
            continue
        out_p50 = float(np.median(bg))
        in_p90 = float(np.percentile(fg, 90))
        if out_p50 <= max_bg and in_p90 >= min_contrast * max(out_p50, 0.01):
            chosen_mask = ov_mask
            chosen_box = b
            break

    if chosen_mask is None or chosen_box is None:
        return None, None, False

    # Distinguish a real camera/video PIP (smooth face/room textures) from synthetic random test noise
    # at native frame resolution so thumbnail downsampling does not smooth out random pixel noise.
    step_means: list[float] = []
    step40_rates: list[float] = []
    for sidx in sorted({0, n // 2, n - 1}):
        with Image.open(base / frames[sidx]["path"]) as im_s:
            g_s = np.asarray(im_s.convert("L"), dtype=np.int16)
        gh_s, gw_s = g_s.shape
        px0, py0 = int(chosen_box[0] * gw_s), int(chosen_box[1] * gh_s)
        px1, py1 = max(px0 + 2, int(chosen_box[2] * gw_s)), max(py0 + 2, int(chosen_box[3] * gh_s))
        sample_patch = g_s[py0:py1, px0:px1]
        if sample_patch.size > 4:
            diffs = np.abs(np.diff(sample_patch, axis=1))
            step_means.append(float(diffs.mean()))
            step40_rates.append(float((diffs > 40).mean()))
    is_camera_pip = bool(step_means) and float(np.median(step_means)) < 15.0 and float(np.median(step40_rates)) < 0.15

    full_ov = cv2.resize(chosen_mask.astype(np.uint8) * 255, (load_w, load_h), interpolation=cv2.INTER_NEAREST) > 0
    return ~full_ov, chosen_box, is_camera_pip


def _compact_pip_mask(
    frames: list[dict[str, Any]], base: Path, cfg: dict[str, Any], load_w: int, load_h: int
) -> np.ndarray | None:
    """Return a valid-canvas mask excluding a localized corner/edge PIP overlay, or None."""
    valid_mask, _, _ = _find_corner_pip(frames, base, cfg, load_w, load_h)
    return valid_mask


def _is_document(
    crop: np.ndarray,
    full_frame: bool,
    cfg: dict[str, Any],
    valid_mask: np.ndarray | None = None,
    has_pip: bool = False,
) -> bool:
    """True when the crop looks like a slide or a page, not a camera picture."""
    if crop.shape[0] < 8 or crop.shape[1] < 8:
        return False
    if _sharpness_score(crop) < float(cfg.get("v3_min_sharpness", 0.20)) * 0.05:
        return False
    s = _document_stats(crop, valid_mask)
    if (
        s["dom"] < float(cfg["v3_min_dominant"])
        or not (float(cfg["v3_min_ink"]) <= s["ink40"] <= float(cfg["v3_max_ink"]))
        or s["photo"] > float(cfg["v3_max_photo"])
    ):
        return False
    # Clean flat or smooth-gradient canvas (title cards, minimalist dark/white, smooth gradients).
    if s["flat24"] >= float(cfg["v3_flat_min_fraction"]) and s["smooth"] <= float(cfg["v3_flat_max_smooth"]):
        if s["ink40"] >= float(cfg["v3_flat_min_ink"]) or s["photo"] >= float(cfg["v3_flat_sparse_min_photo"]):
            return True
    # Dominant solid UI / code / diagram / whiteboard slide.
    if (
        s["dom"] >= float(cfg["v3_ui_min_dominant"])
        and s["smooth"] <= float(cfg["v3_ui_max_smooth"])
        and s["ink40"] >= float(cfg["v3_ui_min_ink"])
        and s["ink60"] >= float(cfg["v3_ui_min_ink60"])
    ):
        return True
    # Strong panel with crisp foreground text (e.g. half-dark panel + photo slides).
    if (
        s["dom"] >= float(cfg["v3_panel_min_dominant"])
        and s["ink40"] >= float(cfg["v3_panel_min_ink"])
        and s["ink80"] >= float(cfg["v3_panel_min_ink80"])
    ):
        return True
    # Photo-containing / half-photo / hero-photo slide distinguished from webcams by crisp ink.
    if has_pip:
        if s["ink60"] >= float(cfg["v3_pip_photo_min_ink60"]) and s["ink80"] >= float(cfg["v3_pip_photo_min_ink80"]):
            return True
        return s["ink40"] >= float(cfg["v3_pip_wire_min_ink40"]) and s["ink60"] >= float(cfg["v3_pip_photo_min_ink60"])
    min_i60 = float(cfg["v3_fullframe_photo_min_ink60"] if full_frame else cfg["v3_photo_min_ink60"])
    min_i80 = float(cfg["v3_fullframe_photo_min_ink80"] if full_frame else cfg["v3_photo_min_ink80"])
    return s["ink60"] >= min_i60 and s["ink80"] >= min_i80


def _edge_cols(gray: np.ndarray) -> np.ndarray:
    """Share of each column that steps by more than 24 gray levels."""
    f = gray.astype(np.int16)
    return (np.abs(np.diff(f, axis=1)) > 24).mean(0)


def _zone_peak(col: np.ndarray, w: int, side: str) -> tuple[int, float] | None:
    """Strongest cut that would leave a 6–26% strip on one side. Cut is a pixel x."""
    if side == "L":
        lo, hi = int(0.06 * w) - 1, int(0.26 * w)
    else:
        lo, hi = int(0.74 * w) - 1, int(0.94 * w)
    lo, hi = max(0, lo), min(len(col), hi)
    if hi <= lo:
        return None
    sl = col[lo:hi]
    j = int(np.argmax(sl))
    return lo + j + 1, float(sl[j])


def _strip_is_rail(gray: np.ndarray, cut: int, side: str) -> bool:
    """True when the outer strip is darker or busier than the slide beside it."""
    h, w = gray.shape
    if side == "L":
        rail, inner = gray[:, :cut], gray[:, cut:min(w, cut + max(1, cut))]
    else:
        width = max(1, w - cut)
        rail, inner = gray[:, cut:], gray[:, max(0, cut - width):cut]
    if rail.size == 0 or inner.size == 0:
        return False
    return float(rail.mean()) + 12 < float(inner.mean()) or float(rail.std()) > float(inner.std()) + 8


def _learn_stable_rail(frames: list[dict[str, Any]], base: Path, cfg: dict[str, Any],
                       load_w: int, load_h: int) -> tuple[str, float] | None:
    """The side cut that most clear frames agree on, or None."""
    learn = float(cfg["v3_rail_learn_strength"])
    votes: dict[tuple[str, float], int] = {}
    total = 0
    for fr in frames:
        with Image.open(base / fr["path"]) as im:
            gray = np.asarray(im.convert("L").resize((load_w, load_h), Image.BILINEAR))
        col = _edge_cols(gray)
        best = None
        for side in ("L", "R"):
            peak = _zone_peak(col, gray.shape[1], side)
            if peak is None:
                continue
            cut, strength = peak
            if strength < learn or not _strip_is_rail(gray, cut, side):
                continue
            if best is None or strength > best[0]:
                best = (strength, side, cut)
        if best is None:
            continue
        key = (best[1], round(best[2] / gray.shape[1], 2))
        votes[key] = votes.get(key, 0) + 1
        total += 1
    if total < int(cfg["v3_rail_min_votes"]):
        return None
    side, frac = max(votes, key=lambda k: votes[k])
    if votes[(side, frac)] < float(cfg["v3_rail_min_agree"]) * total:
        return None
    return side, float(frac)


def _learn_stable_letterbox(
    frames: list[dict[str, Any]], base: Path, learned: tuple[str, float] | None, load_w: int, load_h: int
) -> tuple[int, int] | None:
    """Learn stable top/bottom letterbox rows (y0, y1) across clear frames so dark slides do not jitter."""
    if learned is None:
        return None
    side, frac = learned
    cut = max(1, min(load_w - 1, int(round(frac * load_w))))
    y_votes: dict[tuple[int, int], int] = {}
    total = 0
    step = max(1, len(frames) // 200)
    for fr in frames[::step]:
        with Image.open(base / fr["path"]) as im:
            gray = np.asarray(im.convert("L").resize((load_w, load_h), Image.BILINEAR))
        sub = gray[:, :cut] if side == "R" else gray[:, cut:]
        bx0, by0, bx1, by1 = _content_well(sub)
        if by0 > 0 or by1 < load_h:
            key = (by0, by1)
            y_votes[key] = y_votes.get(key, 0) + 1
        total += 1
    if not y_votes or total < 4:
        return None
    best_y = max(y_votes, key=lambda k: sum(v for (py0, py1), v in y_votes.items() if abs(py0 - k[0]) <= 2 and abs(py1 - k[1]) <= 2))
    cluster = [(k, v) for k, v in y_votes.items() if abs(k[0] - best_y[0]) <= 2 and abs(k[1] - best_y[1]) <= 2]
    if sum(v for _, v in cluster) < 0.35 * total:
        return None
    return max(cluster, key=lambda kv: kv[1])[0]


def _apply_stable_rail(
    gray: np.ndarray,
    box: tuple[int, int, int, int],
    learned: tuple[str, float] | None,
    cfg: dict[str, Any],
    learned_y: tuple[int, int] | None = None,
) -> tuple[int, int, int, int]:
    """Crop at the learned rail and letterbox. A faint edge still counts when the strip is a rail.

    A cut on the other side is a line inside the slide, so it is removed.
    The crop stops a little inside the rail so face pixels on the edge are excluded.
    """
    if learned is None:
        return box
    side, frac = learned
    h, w = gray.shape
    cut = max(1, min(w - 1, int(round(frac * w))))
    x0, y0, x1, y1 = box
    col = _edge_cols(gray)
    pad = max(1, int(0.01 * w))
    lo, hi = max(0, cut - 1 - pad), min(len(col), cut - 1 + pad + 1)
    strength = float(col[lo:hi].max()) if hi > lo else 0.0
    has_lbox = False
    if learned_y is not None:
        ly0, ly1 = learned_y
        sub = gray[:, :cut] if side == "R" else gray[:, cut:]
        if ly0 > 0 and ly1 < h:
            has_lbox = float(sub[:ly0].mean()) < 14.0 and float(sub[ly1:].mean()) < 14.0 and float(sub[:ly0].std()) < 10.0
    if strength < float(cfg["v3_rail_apply_strength"]) and not _strip_is_rail(gray, cut, side) and not has_lbox:
        return box
    gutter = max(4, int(float(cfg["v3_rail_gutter"]) * w))
    if side == "R":
        x0 = 0
        x1 = max(1, min(x1, cut) - gutter)
    else:
        x1 = w
        x0 = min(w - 1, max(x0, cut) + gutter)
    if learned_y is not None:
        ly0, ly1 = learned_y
        if ly0 > 0 and float(gray[:ly0, x0:x1].mean()) < 18.0:
            y0 = ly0
        if ly1 < h and float(gray[ly1:, x0:x1].mean()) < 18.0:
            y1 = ly1
    if (x1 - x0) < int(0.40 * w) or (y1 - y0) < int(0.40 * h):
        return box
    return x0, y0, x1, y1


def _drop_small_components(diff: np.ndarray, min_px: int, clear_edge_bars: bool = False) -> np.ndarray:
    """Clear cursor/badge blobs smaller than min_px (and optional thin OS menu bars) using OpenCV."""
    if min_px <= 1 or not bool(diff.any()):
        return diff
    h, w = diff.shape
    out = diff.copy()
    n_lab, labels, stats, _ = cv2.connectedComponentsWithStats(diff.astype(np.uint8), connectivity=8)
    for k in range(1, n_lab):
        x, y, bw, bh, area = stats[k]
        if area < min_px:
            out[labels == k] = False
        elif clear_edge_bars and (y <= 2 or y + bh >= h - 2) and bh <= 12 and bw >= 80:
            out[labels == k] = False
        elif clear_edge_bars and area < min_px * 2 and bw <= 28 and bh <= 28:
            out[labels == k] = False
    return out


def _mask_pip_on_image(im: Image.Image, pip_box: list[float], crop_box: list[float]) -> Image.Image:
    """Fill a corner PIP webcam region on the cropped slide image with the surrounding slide background color."""
    cw0, ch0, cw1, ch1 = crop_box
    cw, ch = max(1e-6, cw1 - cw0), max(1e-6, ch1 - ch0)
    rx0 = max(0.0, min(1.0, (pip_box[0] - cw0) / cw))
    ry0 = max(0.0, min(1.0, (pip_box[1] - ch0) / ch))
    rx1 = max(0.0, min(1.0, (pip_box[2] - cw0) / cw))
    ry1 = max(0.0, min(1.0, (pip_box[3] - ch0) / ch))
    if (rx1 - rx0) <= 0.01 or (ry1 - ry0) <= 0.01:
        return im
    arr = np.asarray(im).copy()
    h, w = arr.shape[:2]
    x0, y0 = max(0, int(round(rx0 * w))), max(0, int(round(ry0 * h)))
    x1, y1 = min(w, int(round(rx1 * w))), min(h, int(round(ry1 * h)))
    pad = max(6, int(0.02 * min(w, h)))
    bx0, by0 = max(0, x0 - pad), max(0, y0 - pad)
    bx1, by1 = min(w, x1 + pad), min(h, y1 + pad)
    ring_mask = np.ones((by1 - by0, bx1 - bx0), dtype=bool)
    ring_mask[y0 - by0 : y1 - by0, x0 - bx0 : x1 - bx0] = False
    ring_pixels = arr[by0:by1, bx0:bx1][ring_mask]
    if ring_pixels.size >= 3:
        fill_rgb = np.median(ring_pixels.reshape(-1, 3), axis=0).astype(np.uint8)
    else:
        fill_rgb = np.median(arr.reshape(-1, 3), axis=0).astype(np.uint8)
    arr[y0:y1, x0:x1] = fill_rgb
    return Image.fromarray(arr)


def _render_crop(im: Image.Image, box: list[float], max_width: int) -> Image.Image:
    w, h = im.size
    left = max(0, min(w - 1, int(round(box[0] * w))))
    top = max(0, min(h - 1, int(round(box[1] * h))))
    right = max(left + 1, min(w, int(round(box[2] * w))))
    bottom = max(top + 1, min(h, int(round(box[3] * h))))
    crop = im.crop((left, top, right, bottom))
    if crop.width > max_width:
        nh = max(1, round(crop.height * max_width / crop.width))
        crop = crop.resize((max_width, nh), Image.Resampling.LANCZOS)
    return crop


def plan_v3(frames: list[dict[str, Any]], base: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    frames = sorted(frames, key=lambda f: (f["t_start"], f["id"]))
    n = len(frames)
    info: dict[str, Any] = {"content_region": None, "slide_like_frames": 0, "camera_or_live_frames": 0,
                            "duplicate_pairs_merged_in_final_check": 0, "duplicates_in_kept_set": 0,
                            "stable_rail": None}
    if n == 0:
        return {"runs": [], "slides": [], "overlay": None, "verification": [], "v3": info}
    B = max(1, int(cfg["v3_block_px"]))
    W = int(cfg["v3_width"]) // B * B
    H = int(cfg["v3_height"]) // B * B
    lvl, max_blk = int(cfg["pixel_level"]), float(cfg["max_block_change_fraction"])
    gh, gw = H // B, W // B
    load_w, load_h = max(W, int(cfg["v3_width"])), max(H, int(cfg["v3_height"]))

    learned = _learn_stable_rail(frames, base, cfg, load_w, load_h)
    learned_y = _learn_stable_letterbox(frames, base, learned, load_w, load_h)
    info["stable_rail"] = [learned[0], learned[1]] if learned else None
    valid_full, pip_box, is_cam_pip = _find_corner_pip(frames, base, cfg, load_w, load_h)
    has_pip = valid_full is not None
    is_doc = [False] * n
    wells: list[tuple[int, int, int, int] | None] = [None] * n
    canvas: list[np.ndarray | None] = [None] * n
    pip_grid: list[np.ndarray] = [np.zeros((gh, gw), dtype=bool) for _ in range(n)]
    region_counts: dict[tuple[float, float, float, float], int] = {}
    for i, fr in enumerate(frames):
        with Image.open(base / fr["path"]) as im:
            gray = np.asarray(im.convert("L").resize((load_w, load_h), Image.BILINEAR))
        box = _apply_stable_rail(gray, _content_well(gray), learned, cfg, learned_y)
        box = _snap_well(box, load_w, load_h)
        if learned_y is not None:
            # Keep learned letterbox tight instead of letting _snap_well re-include a few pixels of black bar.
            ly0, ly1 = learned_y
            cand_y0 = max(box[1], ly0) if float(gray[:ly0, box[0]:box[2]].mean()) < 18.0 else box[1]
            cand_y1 = min(box[3], ly1) if float(gray[ly1:, box[0]:box[2]].mean()) < 18.0 else box[3]
            if (cand_y1 - cand_y0) >= int(0.40 * load_h):
                box = (box[0], cand_y0, box[2], cand_y1)
        # In a screen-share recording with a learned rail, a full uncropped frame has no shared screen (e.g. Teams lobby).
        if learned is not None and n >= 20 and box == (0, 0, load_w, load_h):
            continue
        crop = gray[box[1]:box[3], box[0]:box[2]]
        full = (box[2] - box[0]) * (box[3] - box[1]) >= 0.97 * load_w * load_h
        vm = valid_full[box[1]:box[3], box[0]:box[2]] if valid_full is not None else None
        if not _is_document(crop, full, cfg, valid_mask=vm, has_pip=has_pip):
            continue
        is_doc[i] = True
        wells[i] = box
        canvas[i] = np.asarray(Image.fromarray(crop).resize((W, H), Image.BILINEAR), dtype=np.uint8)
        if vm is not None and float(vm.mean()) >= 0.5:
            ov_grid = np.asarray(Image.fromarray((~vm).astype(np.uint8) * 255).resize((W, H), Image.NEAREST)) > 0
            pip_grid[i] = ov_grid.reshape(gh, B, gw, B).mean(axis=(1, 3)) > float(cfg["v3_overlay_block_fraction"])
        key = (round(box[0] / load_w, 2), round(box[1] / load_h, 2), round(box[2] / load_w, 2), round(box[3] / load_h, 2))
        region_counts[key] = region_counts.get(key, 0) + 1
    if region_counts:
        info["content_region"] = list(max(region_counts, key=region_counts.get))

    def block_frac(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        d = np.abs(a.astype(np.int16) - b.astype(np.int16)) > lvl
        return d.reshape(gh, B, gw, B).mean(axis=(1, 3))

    T = [float(f["t_start"]) for f in frames]
    dur = [max(0.0, float(f["t_end"]) - float(f["t_start"])) for f in frames]
    tw = float(cfg["v3_live_window_s"])
    doc_ids = [i for i in range(n) if is_doc[i]]
    # Consecutive pairs only. Partial updates (< max_live) isolate embedded live boxes;
    # full-frame churn only drops short fleeting frames when pairs exist on both sides.
    max_live = float(cfg["v3_max_live_fraction"])
    pair_change = []
    for a, b in zip(doc_ids, doc_ids[1:]):
        ch = (block_frac(canvas[a], canvas[b]) > 0.01) & ~(pip_grid[a] | pip_grid[b])
        pair_change.append((a, b, ch, float(ch.mean())))
    live = [np.zeros((gh, gw), dtype=bool) for _ in range(n)]
    burst_frame_max = float(cfg["v3_churn_burst_max_frame_s"])
    for i in doc_ids:
        live[i] = pip_grid[i].copy()
        local_votes = [
            ch for a, b, ch, frac in pair_change
            if abs(T[a] - T[i]) <= tw and abs(T[b] - T[i]) <= tw and frac <= max_live
        ]
        if len(local_votes) >= 3:
            live[i] = live[i] | (np.mean(np.stack(local_votes), axis=0) >= 0.5)
        if i > 0 and dur[i] <= burst_frame_max:
            all_votes = [(a, b, ch) for a, b, ch, _ in pair_change if abs(T[a] - T[i]) <= tw and abs(T[b] - T[i]) <= tw]
            has_before_p = any(b <= i for _, b, _ in all_votes)
            has_after_p = any(a >= i for a, _, _ in all_votes)
            if has_before_p and has_after_p and len(all_votes) >= 4:
                if float((np.mean(np.stack([ch for _, _, ch in all_votes]), axis=0) >= 0.5).mean()) > max_live:
                    is_doc[i] = False

    # Embedded video, ad burst, and rapid desktop-swipe churn filters.
    churn_min = int(cfg["v3_video_churn_min_frames"])
    churn_w = float(cfg["v3_video_churn_window_s"])
    churn_max_s = float(cfg["v3_video_churn_max_member_s"])
    burst_w = float(cfg["v3_churn_burst_window_s"])
    cut_thresh = float(cfg["v3_churn_burst_cut_fraction"])
    min_cuts = int(cfg["v3_churn_burst_min_cuts"])
    min_fast_frac = float(cfg["v3_churn_burst_min_fast_fraction"])
    nondoc_w = float(cfg["v3_churn_burst_nondoc_window_s"])
    min_nondoc = int(cfg["v3_churn_burst_min_nondoc"])
    hi_cuts = int(cfg["v3_churn_burst_hi_cuts"])
    orig_doc = list(is_doc)
    burst_dropped: set[int] = set()
    doc_pair_diffs = {
        a: float(((block_frac(canvas[a], canvas[b]) > 0.04) & ~(pip_grid[a] | pip_grid[b])).mean())
        for a, b, _, _ in pair_change if b == a + 1
    }
    for i in doc_ids:
        if i == 0 or not orig_doc[i]:
            continue
        if n >= churn_min and dur[i] <= churn_max_s:
            win = [j for j in range(n) if abs(T[j] - T[i]) <= churn_w]
            if len(win) >= churn_min:
                has_before = any(not orig_doc[j] for j in win if j < i)
                has_after = any(not orig_doc[j] for j in win if j > i)
                if has_before and has_after and sum(not orig_doc[j] for j in win) / len(win) > 0.5:
                    is_doc[i] = False
                    burst_dropped.add(i)
                    continue
        if dur[i] <= burst_frame_max:
            bwin = [j for j in range(n) if abs(T[j] - T[i]) <= burst_w]
            if len(bwin) < min_cuts + 1:
                continue
            if sum(dur[j] <= burst_frame_max for j in bwin) / len(bwin) < min_fast_frac:
                continue
            cuts_before = sum(
                1 for j in bwin if j < min(i, n - 1)
                and doc_pair_diffs.get(j, 1.0 if not (orig_doc[j] and orig_doc[j + 1]) else 0.0) > cut_thresh
            )
            cuts_after = sum(
                1 for j in bwin if i <= j < n - 1
                and doc_pair_diffs.get(j, 1.0 if not (orig_doc[j] and orig_doc[j + 1]) else 0.0) > cut_thresh
            )
            total_cuts = cuts_before + cuts_after
            if total_cuts >= min_cuts and cuts_before >= 1 and cuts_after >= 1:
                nondoc_near = sum(1 for j in range(n) if abs(T[j] - T[i]) <= nondoc_w and not orig_doc[j])
                if nondoc_near >= min_nondoc or total_cuts >= hi_cuts:
                    is_doc[i] = False
                    burst_dropped.add(i)
    # Propagate burst suppression along contiguous non-cut frames of the same video/browser shot.
    all_dropped = set(burst_dropped) | {i for i in doc_ids if not is_doc[i] and dur[i] <= burst_frame_max}
    if all_dropped:
        queue = list(all_dropped)
        while queue:
            curr = queue.pop()
            for nxt in (curr - 1, curr + 1):
                if nxt <= 0 or nxt >= n or not is_doc[nxt] or dur[nxt] > burst_frame_max:
                    continue
                lo = min(curr, nxt)
                if doc_pair_diffs.get(lo, 1.0) <= cut_thresh:
                    is_doc[nxt] = False
                    burst_dropped.add(nxt)
                    all_dropped.add(nxt)
                    queue.append(nxt)
    # Second pass in index space: drop isolated 1-2 frame moving video shots surrounded by non-doc video churn.
    if n >= churn_min:
        for i in range(1, n):
            if not is_doc[i]:
                continue
            iwin = [j for j in range(max(0, i - 10), min(n, i + 11)) if j != i]
            if dur[i] <= churn_max_s and len(iwin) >= churn_min:
                if any(not is_doc[j] for j in iwin if j < i) and any(not is_doc[j] for j in iwin if j > i):
                    if sum(not is_doc[j] for j in iwin) / len(iwin) >= 0.75:
                        is_doc[i] = False
                        continue
            # A paused/resumed 2-frame moving video shot flanked on both sides by >=6 non-doc video frames.
            if i + 1 < n and is_doc[i + 1] and min(dur[i], dur[i + 1]) <= 2.0:
                if 0.01 <= doc_pair_diffs.get(i, 1.0) <= 0.25:
                    before_nondoc = i >= 6 and all(not is_doc[j] for j in range(i - 6, i))
                    after_nondoc = i + 7 < n and all(not is_doc[j] for j in range(i + 2, i + 8))
                    if before_nondoc and after_nondoc:
                        is_doc[i] = False
                        is_doc[i + 1] = False

    info["slide_like_frames"] = sum(is_doc)
    info["camera_or_live_frames"] = n - sum(is_doc)

    ph = [""] * n
    for i in range(n):
        if is_doc[i]:
            ph[i] = phash_hex(Image.fromarray(canvas[i]), 8)
    ret_ph = int(cfg["v3_return_max_phash_distance"])

    speck = max(1, int(float(cfg["v3_ignore_speck_fraction"]) * H * W))

    def same(i: int, j: int, also: np.ndarray | None = None) -> tuple[bool, float]:
        mask = live[i] | live[j]
        if also is not None:
            mask = mask | also
        if bool(mask.all()):
            return False, 1.0
        diff = np.abs(canvas[i].astype(np.int16) - canvas[j].astype(np.int16)) > lvl
        if bool(mask.any()):
            expanded = np.repeat(np.repeat(mask, B, axis=0), B, axis=1)
            diff = diff.copy()
            diff[expanded] = False
        if not bool(diff.any()):
            return True, 0.0
        frac = diff.reshape(gh, B, gw, B).mean(axis=(1, 3))
        bm = float(frac.max())
        if bm <= max_blk:
            return True, bm
        # Only a little changed. Drop cursor-sized blobs (and thin edge OS menu bars when pHash + SSIM agree), then look again.
        if float(diff.mean()) <= 0.02:
            high_sim = _hd(ph[i], ph[j]) <= 8 and _ssim_score(canvas[i], canvas[j]) >= 0.965
            diff = _drop_small_components(diff, speck, clear_edge_bars=high_sim)
            if not bool(diff.any()):
                return True, 0.0
            bm = float(diff.reshape(gh, B, gw, B).mean(axis=(1, 3)).max())
        return bm <= max_blk, bm

    seeds: list[int] = []
    members: list[list[int]] = []
    owner = [-1] * n
    cur = None
    for i in range(n):
        if not is_doc[i]:
            continue
        hit = None
        if cur is not None and same(seeds[cur], i)[0]:
            hit = cur
        else:
            for k in range(len(seeds) - 1, -1, -1):
                if k != cur and _hd(ph[seeds[k]], ph[i]) <= ret_ph and same(seeds[k], i)[0]:
                    hit = k
                    break
        if hit is None:
            seeds.append(i)
            members.append([])
            hit = len(seeds) - 1
        members[hit].append(i)
        owner[i] = hit
        cur = hit

    def pick(k: int) -> int:
        mem = members[k]
        last = mem[0]
        for i in range(mem[0] + 1, n):
            if owner[i] == k:
                last = i
            elif is_doc[i]:
                break
        return last if all(same(last, j)[0] for j in mem) else mem[0]

    rep = [pick(k) for k in range(len(seeds))]
    alias = list(range(len(seeds)))
    # Live blocks of a slide that was merged in. A webcam can be masked on one
    # representative and not on a short member of the other. The stored images still match.
    extra = [np.zeros((gh, gw), dtype=bool) for _ in seeds]
    merged = 0
    for a in range(len(seeds)):
        if alias[a] != a:
            continue
        for b in range(a + 1, len(seeds)):
            if alias[b] == b and same(rep[a], rep[b])[0] and all(same(rep[a], j, live[rep[b]])[0] for j in members[b]):
                alias[b] = a
                extra[a] = extra[a] | live[rep[b]] | extra[b]
                members[a] += members[b]
                merged += 1

    def same_block_share(i: int, j: int) -> float:
        mask = live[i] | live[j]
        bf = block_frac(canvas[i], canvas[j])
        if bool(mask.any()):
            bf = bf.copy()
            bf[mask] = 0.0
        return float((bf <= max_blk).mean())

    def changed_has_photo(short_idx: int, anchor_idx: int) -> bool:
        bf = block_frac(canvas[short_idx], canvas[anchor_idx]) > max_blk
        if not bool(bf.any()):
            return False
        blk = canvas[short_idx][:gh * B, :gw * B].reshape(gh, B, gw, B)
        rng = (blk.max(axis=(1, 3)) - blk.min(axis=(1, 3))) > 48
        return float(rng[bf].mean()) > 0.25

    def is_progressive_build_or_fade(early_idx: int, late_idx: int) -> bool:
        if same_block_share(early_idx, late_idx) < 0.50:
            return False
        if _ssim_score(canvas[early_idx][:64, :], canvas[late_idx][:64, :]) < 0.90:
            return False
        ch = (block_frac(canvas[early_idx], canvas[late_idx]) > max_blk) & ~(live[early_idx] | live[late_idx])
        if not bool(ch.any()):
            return True
        blks_a = canvas[early_idx][:gh * B, :gw * B].reshape(gh, B, gw, B)
        blks_b = canvas[late_idx][:gh * B, :gw * B].reshape(gh, B, gw, B)
        rng_a = blks_a.max(axis=(1, 3)) - blks_a.min(axis=(1, 3))
        rng_b = blks_b.max(axis=(1, 3)) - blks_b.min(axis=(1, 3))
        flat_a = float((rng_a[ch] <= 20).mean())
        flat_b = float((rng_b[ch] <= 20).mean())
        photo_a = float((rng_a[ch] > 48).mean())
        return flat_a >= 0.75 or (flat_b >= 0.75 and photo_a >= 0.40)

    def absorb(src: int, dst: int) -> None:
        alias[src] = dst
        for j in members[src]:
            extra[dst] |= live[j] | (block_frac(canvas[rep[dst]], canvas[j]) > max_blk)
        extra[dst] |= extra[src]
        members[dst] += members[src]

    build_max_s = float(cfg["v3_build_max_seconds"])
    min_anchor_s = float(cfg["v3_build_min_anchor_seconds"])
    build_same = float(cfg["v3_build_min_same_blocks"])
    popover_same = float(cfg["v3_popover_min_same_blocks"])
    if n >= 20 and seeds:
        slide_dur = [sum(dur[j] for j in members[k]) for k in range(len(seeds))]
        order = sorted([k for k in range(len(seeds)) if alias[k] == k], key=lambda k: min(members[k]))
        # 1) Progressive build-in steps & column fades (right-to-left so a multi-step build folds into its settled anchor)
        for pos in range(len(order) - 2, -1, -1):
            k = order[pos]
            if alias[k] != k or len(members[k]) > 3:
                continue
            nxt = order[pos + 1]
            while alias[nxt] != nxt:
                nxt = alias[nxt]
            short_build = (
                slide_dur[k] <= build_max_s
                and slide_dur[nxt] >= min_anchor_s
                and same_block_share(rep[k], rep[nxt]) >= build_same
            )
            verified_build = slide_dur[k] < slide_dur[nxt] and is_progressive_build_or_fade(rep[k], rep[nxt])
            if short_build or verified_build:
                absorb(k, nxt)
                slide_dur[nxt] += slide_dur[k]
                merged += 1
        # 2) Brief window pop-over immediately after a long anchor slide right before ending or switching to camera
        order = [k for k in order if alias[k] == k]
        for pos in range(1, len(order)):
            k = order[pos]
            if alias[k] != k or slide_dur[k] > build_max_s or len(members[k]) > 3:
                continue
            prev = order[pos - 1]
            while alias[prev] != prev:
                prev = alias[prev]
            last_m = max(members[k])
            ends_in_camera = (pos == len(order) - 1) or not any(is_doc[j] for j in range(last_m + 1, min(n, last_m + 6)))
            if slide_dur[prev] >= min_anchor_s and same_block_share(rep[k], rep[prev]) >= popover_same and (
                changed_has_photo(rep[k], rep[prev]) or ends_in_camera
            ):
                absorb(k, prev)
                slide_dur[prev] += slide_dur[k]
                merged += 1
        # 3) Collapse embedded live-demo / scrolling sub-window bursts (>=3 consecutive slides with static top header)
        order = [k for k in order if alias[k] == k]
        groups: list[list[int]] = []
        for k in order:
            if groups:
                anchor = max(groups[-1], key=lambda x: slide_dur[x])
                bf = block_frac(canvas[rep[anchor]], canvas[rep[k]])
                mask = live[rep[anchor]] | live[rep[k]]
                if bool(mask.any()):
                    bf = bf.copy()
                    bf[mask] = 0.0
                if (
                    float((bf <= max_blk).mean()) >= build_same
                    and float((bf[:6, :] <= max_blk).mean()) >= 0.98
                    and _ssim_score(canvas[rep[anchor]][:64, :], canvas[rep[k]][:64, :]) >= 0.985
                ):
                    groups[-1].append(k)
                    continue
            groups.append([k])
        for g in groups:
            if len(g) >= 3:
                anchor = max(g, key=lambda x: slide_dur[x])
                for k in g:
                    if k != anchor and alias[k] == k:
                        absorb(k, anchor)
                        slide_dur[anchor] += slide_dur[k]
                        merged += 1

    info["duplicate_pairs_merged_in_final_check"] = merged
    live_k = [k for k in range(len(seeds)) if alias[k] == k]
    info["duplicates_in_kept_set"] = sum(
        1 for x, a in enumerate(live_k) for b in live_k[x + 1:] if same(rep[a], rep[b])[0])
    newno = {k: x for x, k in enumerate(live_k)}

    def _root(x: int) -> int:
        while alias[x] != x:
            x = alias[x]
        return x

    for i in range(n):
        if owner[i] >= 0:
            owner[i] = newno[_root(owner[i])]
    if not live_k:
        return {"runs": [], "slides": [], "overlay": None, "verification": [], "v3": info}

    first = next(owner[i] for i in range(n) if owner[i] >= 0)
    shown, runs = first, []
    for i in range(n):
        if owner[i] >= 0:
            shown = owner[i]
        if runs and runs[-1]["slide"] == shown:
            runs[-1]["frames"].append(i)
        else:
            runs.append({"slide": shown, "frames": [i]})
    slides, verification = [], []
    for x, k in enumerate(live_k):
        mem = sorted(members[k])
        r = rep[k]
        box = wells[r]
        crop = [round(box[0] / load_w, 4), round(box[1] / load_h, 4), round(box[2] / load_w, 4), round(box[3] / load_h, 4)]
        for j in mem:
            ok, bm = same(r, j, extra[k])
            if not ok:
                raise ValueError(f"unique slide {x + 1}: image {frames[r]['id']} does not cover {frames[j]['id']}")
            verification.append({"frame_id": frames[j]["id"], "representative": frames[r]["id"],
                                 "max_block_change_fraction": round(bm, 4), "phash_distance": _hd(ph[r], ph[j])})
        slide_entry: dict[str, Any] = {
            "slide": x + 1, "representative": frames[r]["id"], "path": frames[r]["path"],
            "seconds_on_screen": round(sum(dur[j] for j in mem), 3),
            "members": [frames[j]["id"] for j in mem], "crop": crop,
        }
        if is_cam_pip and pip_box is not None:
            slide_entry["pip_box"] = pip_box
        slides.append(slide_entry)
    out_runs = []
    for r in runs:
        fs = [frames[j] for j in r["frames"]]
        out_runs.append({"id": fs[0]["id"], "t_start": fs[0]["t_start"], "t_end": fs[-1]["t_end"], "slide": r["slide"] + 1,
                         "source_frames": [f["id"] for f in fs]})
    ov_meta = {"box": pip_box, "area_fraction": round((pip_box[2] - pip_box[0]) * (pip_box[3] - pip_box[1]), 4)} if pip_box else None
    return {"runs": out_runs, "slides": slides, "overlay": ov_meta, "verification": verification, "v3": info}


def write_crops(result: dict[str, Any], base: Path, hash_size: int = 8) -> dict[str, Any]:
    """Write one cropped (and PIP-masked) WebP per kept slide when cropping or PIP masking applies.

    Updates paths, bytes, phash, keep_paths and drop_paths. Original videos are never touched.
    The source frame files stay until the caller deletes drop_paths.
    """
    quality = int(result["info"]["params"].get("v3_crop_quality", 75))
    max_width = int(result["info"]["params"].get("v3_crop_max_width", 1280))
    any_crop_or_pip = any(
        (s.get("crop") and (s["crop"][2] - s["crop"][0]) * (s["crop"][3] - s["crop"][1]) < 0.97)
        or s.get("pip_box")
        for s in result["slides"]
    )
    if not any_crop_or_pip:
        return result
    updated: dict[int, tuple[str, int, str]] = {}
    for s in result["slides"]:
        box = s.get("crop") or [0.0, 0.0, 1.0, 1.0]
        pbox = s.get("pip_box")
        rel = f"frames/slide-{int(s['slide'])}.webp"
        dest = base / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(base / s["path"]) as im:
            cropped = _render_crop(im.convert("RGB"), [float(v) for v in box], max_width)
            if pbox:
                cropped = _mask_pip_on_image(cropped, [float(v) for v in pbox], [float(v) for v in box])
            cropped.save(dest, "WEBP", quality=quality, method=4)
            ph = phash_hex(cropped, hash_size)
        updated[int(s["slide"])] = (rel, dest.stat().st_size, ph)
        s["path"] = rel
    if updated:
        for fr in result["frames"]:
            hit = updated.get(int(fr["slide"]))
            if hit:
                fr["path"], fr["bytes"], fr["phash"] = hit
        keep = sorted({fr["path"] for fr in result["frames"]})
        source = set(result.get("source_paths") or [])
        result["keep_paths"] = keep
        result["drop_paths"] = sorted(source - set(keep))
        seen: dict[int, int] = {}
        for fr in result["frames"]:
            seen[int(fr["slide"])] = int(fr["bytes"])
        result["info"]["unique_slide_bytes"] = sum(seen.values())
    return result


def apply(frames: list[dict[str, Any]], base: Path, cfg: dict[str, Any], hash_size: int = 8) -> dict[str, Any]:
    """Plan + build the new manifest frame list. Does not touch any file."""
    by_id = {f["id"]: f for f in frames}
    v3 = cfg.get("mode", "slides_only") == "slides_only"
    p = plan_v3(frames, base, cfg) if v3 else plan(frames, base, cfg, hash_size)
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
        "method": METHOD_V3 if v3 else METHOD,
        "source_frame_count": len(frames),
        "unique_slide_count": len(p["slides"]),
        "run_count": len(p["runs"]),
        "source_frame_bytes": sum(f["bytes"] for f in {f["path"]: f for f in frames}.values()),
        "unique_slide_bytes": sum(by_id[s["representative"]]["bytes"] for s in p["slides"]),
        "overlay_mask": p["overlay"],
        "params": {k: cfg[k] for k in DEFAULTS if k not in ("enabled", "mode")},
    }
    return {"frames": new_frames, "slides": p["slides"], "keep_paths": keep_paths, "drop_paths": drop_paths,
            "source_paths": sorted({f["path"] for f in frames}),
            "info": info, "verification": p.get("verification", []), "v3": p.get("v3")}
