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

from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .common import phash_hex

METHOD = "masked-block-diff+masked-phash v2 (representative verified)"
METHOD_V3 = "slides-only v3: content region + live-block mask + slide/camera test + strict block diff, zero duplicates"
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
    "v3_max_live_fraction": 0.3,
    "v3_min_sharpness": 0.20,
    "v3_return_max_phash_distance": 12,
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
# v3 "slides only". Keeps ONLY slide/screen content; camera pictures (faces, stage, film) are not kept.
#   1. Layout: long straight edges seen in >= 60 % of frames (Teams/Zoom tile borders, letterbox) cut the
#      picture into cells; the biggest cell is the shared-content region. Everything else (participant
#      strip, black bars) is ignored.
#   2. Live blocks: a 16 px block of the content region that changes in >= 50 % of neighbouring frame
#      pairs within +-15 s is "live" (a webcam tile or video inside the share). Live blocks are ignored.
#   3. Slide test: a frame is slide content only if live blocks cover < 30 % of the region AND its
#      edges are sharp (rendered text/graphics): strong edges / medium edges >= 0.20. Camera pictures
#      are soft (measured: Jury webcams <= 0.18 at the 95th percentile, GraalVM slides >= 0.23).
#   4. Same slide = EVERY non-live 16 px block has <= 5 % of pixels changed by > 24 (a changed bullet,
#      number or highlight is a new slide). A frame is first compared with the slide on screen, then
#      with every earlier slide (return to an old slide reuses its image; no second copy).
#   5. Image kept = LAST frame of the slide's first run (bullet builds end finished), verified against
#      every member; else the first frame. Then all kept images are compared pairwise; any duplicate
#      pair is merged, so the kept set has zero duplicates under the same rule.
#   6. Time not showing a slide (camera only) points at the slide shown last (the next one at the very
#      start), so the timeline stays contiguous and no camera picture is stored.
# ---------------------------------------------------------------------------------------------


def _v3_load(paths: list[Path], w: int, h: int, edge_min: float):
    g = np.empty((len(paths), h, w), dtype=np.uint8)
    colacc = np.zeros(w - 1)
    rowacc = np.zeros(h - 1)
    for i, p in enumerate(paths):
        with Image.open(p) as im:
            a = np.asarray(im.convert("L").resize((w, h), Image.BILINEAR))
        g[i] = a
        f = a.astype(np.int16)
        colacc += (np.abs(np.diff(f, axis=1)) > 20).mean(0) > 0.5
        rowacc += (np.abs(np.diff(f, axis=0)) > 20).mean(1) > 0.5
    n = max(1, len(paths))
    cols = [i + 1 for i, c in enumerate(colacc / n) if c >= edge_min]
    rows = [i + 1 for i, c in enumerate(rowacc / n) if c >= edge_min]

    def cells(lines, size):
        pts = sorted(set([0, size] + lines))
        return [(a, b) for a, b in zip(pts, pts[1:]) if b - a > 4]
    best = max(((x1 - x0) * (y1 - y0), (x0, y0, x1, y1)) for x0, x1 in cells(cols, w) for y0, y1 in cells(rows, h))[1]
    return g, best


def _v3_sharpness(g: np.ndarray) -> float:
    f = g.astype(np.int16)
    gm = np.maximum(np.abs(np.diff(f, axis=1))[:-1], np.abs(np.diff(f, axis=0))[:, :-1])
    return float((gm > 60).sum() / max(1, int((gm > 12).sum())))


def plan_v3(frames: list[dict[str, Any]], base: Path, cfg: dict[str, Any]) -> dict[str, Any]:
    frames = sorted(frames, key=lambda f: (f["t_start"], f["id"]))
    n = len(frames)
    info: dict[str, Any] = {"content_region": None, "slide_like_frames": 0, "camera_or_live_frames": 0,
                            "duplicate_pairs_merged_in_final_check": 0, "duplicates_in_kept_set": 0}
    if n == 0:
        return {"runs": [], "slides": [], "overlay": None, "verification": [], "v3": info}
    W, H, B = int(cfg["v3_width"]), int(cfg["v3_height"]), int(cfg["v3_block_px"])
    lvl, max_blk = int(cfg["pixel_level"]), float(cfg["max_block_change_fraction"])
    g, (x0, y0, x1, y1) = _v3_load([base / f["path"] for f in frames], W, H, float(cfg["v3_layout_edge_min_frames"]))
    info["content_region"] = [round(x0 / W, 4), round(y0 / H, 4), round(x1 / W, 4), round(y1 / H, 4)]
    ins = 3
    ch, cw = (y1 - y0 - 2 * ins) // B * B, (x1 - x0 - 2 * ins) // B * B
    if ch < B or cw < B:
        ch, cw, y0, x0, ins = H // B * B, W // B * B, 0, 0, 0
    G = g[:, y0 + ins:y0 + ins + ch, x0 + ins:x0 + ins + cw]
    gh, gw = ch // B, cw // B

    def bfrac(i: int, j: int) -> np.ndarray:
        d = np.abs(G[i].astype(np.int16) - G[j].astype(np.int16)) > lvl
        return d.reshape(gh, B, gw, B).mean((1, 3))

    T = [float(f["t_start"]) for f in frames]
    C = [bfrac(i - 1, i) > 0.01 for i in range(1, n)]  # C[q]: pair (q, q+1); any visible change counts
    tw, minp, thr = float(cfg["v3_live_window_s"]), int(cfg["v3_live_min_pairs"]), float(cfg["v3_live_min_change_freq"])
    live = []
    for i in range(n):
        qs = [q for q in range(max(0, i - 60), min(n - 1, i + 60)) if abs(T[q] - T[i]) <= tw and abs(T[q + 1] - T[i]) <= tw]
        live.append(np.mean([C[q] for q in qs], 0) >= thr if len(qs) >= minp else np.zeros((gh, gw), bool))
    sharp = [_v3_sharpness(G[i]) for i in range(n)]
    is_slide = [float(live[i].mean()) < float(cfg["v3_max_live_fraction"]) and sharp[i] >= float(cfg["v3_min_sharpness"])
                for i in range(n)]
    info["slide_like_frames"] = sum(is_slide)
    info["camera_or_live_frames"] = n - sum(is_slide)
    ph = [phash_hex(Image.fromarray(G[i]), 8) for i in range(n)]
    ret_ph = int(cfg["v3_return_max_phash_distance"])

    def same(i: int, j: int) -> tuple[bool, float]:
        m = live[i] | live[j]
        if m.all():
            return False, 1.0
        bm = float(bfrac(i, j)[~m].max())
        return bm <= max_blk, bm

    seeds: list[int] = []
    members: list[list[int]] = []
    owner = [-1] * n
    cur = None
    for i in range(n):
        if not is_slide[i]:
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
        for i in range(mem[0] + 1, n):  # last frame of the first contiguous run (camera frames do not end it)
            if owner[i] == k:
                last = i
            elif is_slide[i]:
                break
        return last if all(same(last, j)[0] for j in mem) else seeds[k]

    rep = [pick(k) for k in range(len(seeds))]
    # Final check: compare every kept image with every other one; merge any duplicate pair.
    alias = list(range(len(seeds)))
    merged = 0
    for a in range(len(seeds)):
        if alias[a] != a:
            continue
        for b in range(a + 1, len(seeds)):
            if alias[b] == b and same(rep[a], rep[b])[0] and all(same(rep[a], j)[0] for j in members[b]):
                alias[b] = a
                members[a] += members[b]
                merged += 1
    info["duplicate_pairs_merged_in_final_check"] = merged
    live_k = [k for k in range(len(seeds)) if alias[k] == k]
    info["duplicates_in_kept_set"] = sum(1 for x, a in enumerate(live_k) for b in live_k[x + 1:] if same(rep[a], rep[b])[0])
    newno = {k: x for x, k in enumerate(live_k)}
    for i in range(n):
        if owner[i] >= 0:
            owner[i] = newno[alias[owner[i]]]
    if not live_k:
        return {"runs": [], "slides": [], "overlay": None, "verification": [], "v3": info}
    # Timeline: camera-only time points at the slide shown last (or the first slide before any slide).
    first = next(owner[i] for i in range(n) if owner[i] >= 0)
    shown, runs = first, []
    for i in range(n):
        if owner[i] >= 0:
            shown = owner[i]
        if runs and runs[-1]["slide"] == shown:
            runs[-1]["frames"].append(i)
        else:
            runs.append({"slide": shown, "frames": [i]})
    dur = [max(0.0, float(f["t_end"]) - float(f["t_start"])) for f in frames]
    slides, verification = [], []
    for x, k in enumerate(live_k):
        mem = sorted(members[k])
        r = rep[k]
        for j in mem:
            ok, bm = same(r, j)
            if not ok:
                raise ValueError(f"unique slide {x + 1}: image {frames[r]['id']} does not cover {frames[j]['id']}")
            verification.append({"frame_id": frames[j]["id"], "representative": frames[r]["id"],
                                 "max_block_change_fraction": round(bm, 4), "phash_distance": _hd(ph[r], ph[j])})
        slides.append({"slide": x + 1, "representative": frames[r]["id"], "path": frames[r]["path"],
                       "seconds_on_screen": round(sum(dur[j] for j in mem), 3), "members": [frames[j]["id"] for j in mem]})
    out_runs = []
    for r in runs:
        fs = [frames[j] for j in r["frames"]]
        out_runs.append({"id": fs[0]["id"], "t_start": fs[0]["t_start"], "t_end": fs[-1]["t_end"], "slide": r["slide"] + 1,
                         "source_frames": [f["id"] for f in fs]})
    return {"runs": out_runs, "slides": slides, "overlay": None, "verification": verification, "v3": info}


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
            "info": info, "verification": p.get("verification", []), "v3": p.get("v3")}
