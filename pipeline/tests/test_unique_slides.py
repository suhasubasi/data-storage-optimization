"""Unique-slide pass: merges only frames that show the same slide; never drops a distinct slide."""
import json
import shutil
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

from dso_contracts.models import Manifest
from dso_pipeline import postpass, unique_slides as U
from dso_pipeline.common import phash_file, sha256_file

W, H = 640, 360


def slide(title: str, bullets: list[str], cam_seed: int | None, highlight: int | None = None) -> Image.Image:
    """Synthetic slide (TEST ONLY): dark background, heading, bullets, optional moving 'webcam' box."""
    img = Image.new("RGB", (W, H), (18, 18, 22))
    d = ImageDraw.Draw(img)
    d.rectangle([40, 30, 600, 34], fill=(60, 120, 220))
    d.text((40, 50), title, fill=(240, 240, 240), font_size=36)
    for i, b in enumerate(bullets):
        y = 120 + 34 * i
        if highlight == i:
            d.rectangle([36, y - 4, 420, y + 26], fill=(70, 110, 180))
        d.text((50, y), "- " + b, fill=(220, 220, 220), font_size=22)
    if cam_seed is not None:  # webcam picture-in-picture, bottom right, different every frame
        rng = np.random.default_rng(cam_seed)
        cam = rng.integers(0, 255, (100, 150, 3), dtype=np.uint8)
        img.paste(Image.fromarray(cam), (W - 170, H - 115))
    return img


def build(tmp_path, images, step=3.0):
    d = tmp_path / "derived" / "a_t"
    (d / "frames").mkdir(parents=True)
    frames, derived = [], []
    for i, im in enumerate(images):
        rel = f"frames/f{i + 1}.webp"
        im.save(d / rel, "WEBP", quality=75)
        b = (d / rel).stat().st_size
        frames.append({"id": f"f{i + 1}", "t_start": i * step, "t_end": (i + 1) * step, "path": rel, "bytes": b,
                       "phash": phash_file(d / rel), "matched_slide": None})
        derived.append({"path": rel, "bytes": b, "kind": "frame"})
    return d, frames, derived


def talk(n_cam=40):
    """A: 12 frames (webcam moves), B: heading differs only slightly from A, C: same as B but one bullet
    highlighted (2 s only), then back to A, then D shown for one frame only."""
    A = ["Decision models", ["Small decisions", "Cheap checks", "Escalate when unsure"]]
    B = ["Decision modes", ["Small decisions", "Cheap checks", "Escalate when unsure"]]
    D = ["Questions?", ["Thank you"]]
    seq = [slide(*A, cam_seed=i) for i in range(12)]
    seq += [slide(*B, cam_seed=100 + i) for i in range(10)]
    seq += [slide(*B, cam_seed=200, highlight=1)]
    seq += [slide(*A, cam_seed=300 + i) for i in range(n_cam - 24)]
    seq += [slide(*D, cam_seed=999)]
    return seq


def test_merges_webcam_repeats_but_keeps_every_distinct_slide(tmp_path):
    d, frames, _ = build(tmp_path, talk())
    r = U.apply(frames, d, U.config({"unique_slides": {"mode": "v2"}}))
    info = r["info"]
    assert info["overlay_mask"] is not None and info["overlay_mask"]["area_fraction"] < 0.15
    # 4 distinct pictures: A, B (one word differs), B+highlight (short), D (one frame)
    assert info["unique_slide_count"] == 4, [s["members"] for s in r["slides"]]
    # time ranges: A | B | B+hl | A again (reuses A's image) | D
    assert [f["slide"] for f in r["frames"]] == [1, 2, 3, 1, 4]
    assert r["frames"][0]["path"] == r["frames"][3]["path"]
    assert r["frames"][-1]["source_frames"] == [frames[-1]["id"]]  # one-frame slide is kept
    # contiguous, covers the same span, every source frame used exactly once
    for a, b in zip(r["frames"], r["frames"][1:]):
        assert a["t_end"] == b["t_start"]
    assert sorted(x for f in r["frames"] for x in f["source_frames"]) == sorted(f["id"] for f in frames)
    assert len(r["keep_paths"]) == 4 and len(r["drop_paths"]) == len(frames) - 4


def test_no_overlay_detected_when_nothing_moves(tmp_path):
    imgs = [slide(f"Slide {i}", ["a", "b"], cam_seed=None) for i in range(35)]
    d, frames, _ = build(tmp_path, imgs)
    r = U.apply(frames, d, U.config({"unique_slides": {"mode": "v2"}}))
    assert r["info"]["overlay_mask"] is None
    assert r["info"]["unique_slide_count"] == 35  # "Slide 1" vs "Slide 2": a real difference, never merged


def test_representative_is_the_longest_held_frame(tmp_path):
    A = ["Same slide", ["one", "two"]]
    imgs = [slide(*A, cam_seed=i) for i in range(3)]
    d, frames, _ = build(tmp_path, imgs)
    frames[1]["t_end"] = frames[1]["t_start"] + 30
    frames[2]["t_start"] = frames[1]["t_end"]
    frames[2]["t_end"] = frames[2]["t_start"] + 3
    r = U.apply(frames, d, U.config({"unique_slides": {"overlay_min_frames": 1, "mode": "v2"}}))
    assert r["info"]["unique_slide_count"] == 1 and r["frames"][0]["path"] == "frames/f2.webp"


def _manifest(d, frames, derived):
    segs = [{"id": f"s{i + 1}", "start": f["t_start"] + 0.5, "end": f["t_start"] + 2.0, "text": f"said {i}",
             "frame_id": f["id"], "speaker": None} for i, f in enumerate(frames)]
    (d / "transcript.json").write_text(json.dumps({"language": "en", "model": "test", "duration_seconds": 0,
                                                   "segments": segs}, indent=2))
    derived = [{"path": "transcript.json", "bytes": (d / "transcript.json").stat().st_size, "kind": "transcript"}] + derived
    m = {"schema_version": "1.0", "asset_id": "a_t", "kind": "video",
         "original": {"path": "originals/a_t/t.mp4", "bytes": 1, "sha256": "0" * 64},
         "metadata": {"title": None, "author": None, "doc_number": None, "revision": None, "date": None,
                      "language": "en", "duration_seconds": frames[-1]["t_end"]},
         "segments": segs, "frames": frames, "slides": [], "derived_files": derived,
         "pipeline": {"version": "t", "model": "test", "frame_threshold": 12, "seconds": 1.0}}
    (d / "manifest.json").write_text(json.dumps(m, indent=2))
    return m


def test_post_pass_remaps_segments_and_prune_removes_only_redundant_frames(tmp_path):
    d, frames, derived = build(tmp_path, talk())
    before = _manifest(d, frames, derived)
    shas = {f["path"]: sha256_file(d / f["path"]) for f in frames}
    (d / "frames" / "notes.txt").write_text("not an image: never pruned")

    dry = postpass.run_unique_slides("a_t", d, dry_run=True)
    assert dry["unique_slides"] == 4 and json.loads((d / "manifest.json").read_text()) == before

    audit = tmp_path / "audit"
    res = postpass.run_unique_slides("a_t", d, audit)
    assert res["unique_slides"] == 4 and res["frames_to_prune"] == len(frames) - 4
    m = json.loads((d / "manifest.json").read_text())
    Manifest.model_validate(m)
    assert m["pipeline"]["unique_slides"]["applied_as"] == "post_pass"
    ids = {f["id"]: f for f in m["frames"]}
    for old, new in zip(before["segments"], m["segments"]):  # text/time untouched, frame = range on screen
        assert (old["text"], old["start"], old["end"]) == (new["text"], new["start"], new["end"])
        f = ids[new["frame_id"]]
        assert f["t_start"] <= new["start"] < f["t_end"]
        assert old["frame_id"] in f["source_frames"]
    t = json.loads((d / "transcript.json").read_text())
    assert t["segments"] == m["segments"]
    assert len(list(audit.glob("a_t-manifest-before-*.json"))) == 1
    # nothing deleted yet; a second pass is refused
    assert len(list((d / "frames").glob("*.webp"))) == len(frames)
    try:
        postpass.run_unique_slides("a_t", d)
        raise AssertionError("second pass must be refused")
    except postpass.PostPassError:
        pass

    res = postpass.prune_frames("a_t", d)
    assert res["removed_files"] == len(frames) - 4
    left = {p.name for p in (d / "frames").iterdir()}
    assert left == {p.split("/")[1] for p in {f["path"] for f in m["frames"]}} | {"notes.txt"}
    for p in {f["path"] for f in m["frames"]}:
        assert sha256_file(d / p) == shas[p]
    listed = {x["path"]: x["bytes"] for x in m["derived_files"]}
    on_disk = {p.relative_to(d).as_posix(): p.stat().st_size for p in d.rglob("*")
               if p.is_file() and p.name not in ("manifest.json", "notes.txt")}
    assert listed == on_disk


def test_prune_refuses_without_the_pass(tmp_path):
    d, frames, derived = build(tmp_path, talk())
    _manifest(d, frames, derived)
    try:
        postpass.prune_frames("a_t", d)
        raise AssertionError("must refuse")
    except postpass.PostPassError as e:
        assert "has not been applied" in str(e)
    assert len(list((d / "frames").glob("*.webp"))) == len(frames)


def test_cli_unique_slides_and_prune(tmp_path):
    d, frames, derived = build(tmp_path, talk())
    _manifest(d, frames, derived)
    p = subprocess.run([sys.executable, "-m", "dso_pipeline", "unique-slides", "--asset-id", "a_t", "--out", str(d)],
                       capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    assert json.loads(p.stdout)["unique_slides"] == 4
    p = subprocess.run([sys.executable, "-m", "dso_pipeline", "prune-frames", "--asset-id", "a_t", "--out", str(d)],
                       capture_output=True, text=True)
    assert p.returncode == 0 and json.loads(p.stdout)["removed_files"] == len(frames) - 4


def test_v3_slides_only_keeps_every_distinct_slide_and_no_duplicates(tmp_path):
    """v3 (default): returning to slide A reuses A's image; the 1-frame highlight and D stay separate."""
    d, frames, _ = build(tmp_path, talk())
    r = U.apply(frames, d, U.config({}))
    info = r["info"]
    assert info["method"] == U.METHOD_V3
    assert info["unique_slide_count"] == 4  # A, B, B+highlight, D
    assert r["v3"]["duplicates_in_kept_set"] == 0
    assert len(r["keep_paths"]) == 4
    assert r["frames"][0]["t_start"] == frames[0]["t_start"] and r["frames"][-1]["t_end"] == frames[-1]["t_end"]
