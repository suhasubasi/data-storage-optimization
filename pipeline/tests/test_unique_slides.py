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


def test_v3_drops_a_camera_and_crops_off_the_side_rail(tmp_path):
    """A moving side rail is not part of the slide. A camera frame is not kept. A changed title is."""
    def frame(title, rail_seed):
        img = Image.new("RGB", (W, H), (245, 245, 245))
        d = ImageDraw.Draw(img)
        d.text((40, 80), title, fill=(20, 20, 20), font_size=42)
        d.text((40, 160), "- Keep the slide text", fill=(20, 20, 20), font_size=28)
        rail = np.random.default_rng(rail_seed).integers(0, 40, (H, 90, 3), dtype=np.uint8)
        img.paste(Image.fromarray(rail), (W - 90, 0))
        return img

    cam = Image.fromarray(np.random.default_rng(1).integers(0, 255, (H, W, 3), dtype=np.uint8))
    d, frames, _ = build(tmp_path, [frame("Storage plan", 1), frame("Storage plan", 2), frame("Storage costs", 3), cam])
    r = U.apply(frames, d, U.config({}))
    assert r["info"]["unique_slide_count"] == 2, [s["members"] for s in r["slides"]]
    assert r["v3"]["duplicates_in_kept_set"] == 0
    assert "f4" not in [m for s in r["slides"] for m in s["members"]]
    assert r["slides"][0]["representative"] == "f2"
    U.write_crops(r, d)
    with Image.open(d / r["slides"][0]["path"]) as im:
        assert im.width < W
        assert float(np.asarray(im.convert("L"))[:, -8:].mean()) > 180


def test_v3_crops_a_dark_slide_using_the_rail_from_the_bright_ones(tmp_path):
    """A dark slide has only a faint rail edge. The bright slides show where the rail is."""
    def bright(seed):
        img = Image.new("RGB", (W, H), (245, 245, 245))
        d = ImageDraw.Draw(img)
        d.text((40, 80), "Storage plan", fill=(20, 20, 20), font_size=42)
        rail = np.random.default_rng(seed).integers(0, 40, (H, 90, 3), dtype=np.uint8)
        img.paste(Image.fromarray(rail), (W - 90, 0))
        return img

    def dark(seed):
        img = Image.new("RGB", (W, H), (28, 28, 32))
        d = ImageDraw.Draw(img)
        d.text((40, 70), "Education and Digital Inclusion", fill=(230, 230, 230), font_size=28)
        d.text((40, 140), "Access to Internet", fill=(210, 210, 210), font_size=22)
        # The top 30% of the rail is black. The edge is real, but it covers too
        # little of the column for the per-frame cutoff (40%). WebP keeps a block this tall.
        rail = np.full((H, 90, 3), 28, dtype=np.uint8)
        rail[:108, :, :] = 0
        img.paste(Image.fromarray(rail), (W - 90, 0))
        return img

    images = [bright(i) for i in range(6)] + [dark(i) for i in range(4)]
    d, frames, _ = build(tmp_path, images)
    r = U.apply(frames, d, U.config({}))
    assert r["info"]["unique_slide_count"] == 2, [s["members"] for s in r["slides"]]
    assert r["v3"]["duplicates_in_kept_set"] == 0
    dark_slide = next(s for s in r["slides"] if "f10" in s["members"])
    assert dark_slide["crop"][2] < 0.90
    U.write_crops(r, d)
    with Image.open(d / dark_slide["path"]) as im:
        assert im.width < W


def test_v3_drops_face_tiles_and_keeps_a_title_card(tmp_path):
    """A title card stays. A lobby of face tiles and a close-up do not."""
    title = Image.new("RGB", (W, H), (32, 32, 40))
    draw = ImageDraw.Draw(title)
    draw.text((60, 140), "Jury deliberation", fill=(240, 240, 240), font_size=48)

    def face_disk(size):
        # Smooth waves: an 8 px block changes a lot, but neighbouring pixels do not.
        # That is a face tile, not a line of text.
        yy, xx = np.mgrid[0:size, 0:size]
        cy = cx = (size - 1) / 2.0
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= (size / 2) ** 2
        shade = 100 + 35 * np.sin(xx * 0.9) + 20 * np.sin(yy * 0.7)
        rgb = np.zeros((size, size, 3), dtype=np.uint8)
        rgb[:] = (8, 8, 10)
        vals = np.clip(shade, 0, 255).astype(np.uint8)
        rgb[mask, 0] = np.clip(vals[mask].astype(np.int16) + 20, 0, 255)
        rgb[mask, 1] = vals[mask]
        rgb[mask, 2] = np.clip(vals[mask].astype(np.int16) - 10, 0, 255)
        return rgb

    wall = Image.new("RGB", (W, H), (8, 8, 10))
    wd = ImageDraw.Draw(wall)
    for x in (40, 180, 320, 460):
        wall.paste(Image.fromarray(face_disk(110)), (x, 120))
        wd.text((x + 20, 236), "Name", fill=(170, 170, 170), font_size=12)
    close = Image.fromarray(face_disk(max(W, H))[:H, :W])
    d, frames, _ = build(tmp_path, [title, wall, close, title])
    r = U.apply(frames, d, U.config({}))
    assert r["info"]["unique_slide_count"] == 1, [s["members"] for s in r["slides"]]
    assert r["slides"][0]["members"] == ["f1", "f4"]
    assert r["v3"]["duplicates_in_kept_set"] == 0


def test_v3_drops_a_face_lobby_that_sits_inside_the_crop(tmp_path):
    """Faces in the picture are not a slide, even after the side rail is removed."""
    def bright(seed):
        img = Image.new("RGB", (W, H), (245, 245, 245))
        d = ImageDraw.Draw(img)
        d.text((40, 80), "Storage plan", fill=(20, 20, 20), font_size=42)
        d.text((40, 150), "Keep this text", fill=(20, 20, 20), font_size=28)
        rail = np.random.default_rng(seed).integers(0, 40, (H, 90, 3), dtype=np.uint8)
        img.paste(Image.fromarray(rail), (W - 90, 0))
        return img

    def face_disk(size):
        yy, xx = np.mgrid[0:size, 0:size]
        cy = cx = (size - 1) / 2.0
        mask = (yy - cy) ** 2 + (xx - cx) ** 2 <= (size / 2) ** 2
        shade = 100 + 35 * np.sin(xx * 0.9) + 20 * np.sin(yy * 0.7)
        rgb = np.full((size, size, 3), 8, dtype=np.uint8)
        vals = np.clip(shade, 0, 255).astype(np.uint8)
        rgb[mask, 0] = np.clip(vals[mask].astype(np.int16) + 20, 0, 255)
        rgb[mask, 1] = vals[mask]
        rgb[mask, 2] = np.clip(vals[mask].astype(np.int16) - 10, 0, 255)
        return rgb

    lobby = Image.new("RGB", (W, H), (8, 8, 10))
    ld = ImageDraw.Draw(lobby)
    for x in (40, 180, 320):
        lobby.paste(Image.fromarray(face_disk(110)), (x, 120))
        ld.text((x + 16, 236), "Name", fill=(180, 180, 180), font_size=12)
    rail = np.random.default_rng(7).integers(0, 40, (H, 90, 3), dtype=np.uint8)
    lobby.paste(Image.fromarray(rail), (W - 90, 0))
    images = [bright(i) for i in range(6)] + [lobby]
    d, frames, _ = build(tmp_path, images)
    r = U.apply(frames, d, U.config({}))
    assert r["info"]["unique_slide_count"] == 1, [s["members"] for s in r["slides"]]
    assert "f7" not in [m for s in r["slides"] for m in s["members"]]


def test_v3_drops_embedded_video_and_absorbs_build_steps(tmp_path):
    """Embedded-video frames amidst camera churn are dropped; short build-in steps merge into settled slide."""
    rng = np.random.default_rng(42)
    noise = lambda: Image.fromarray(rng.integers(0, 255, (H, W, 3), dtype=np.uint8))

    title = Image.new("RGB", (W, H), (242, 244, 247))
    td = ImageDraw.Draw(title)
    td.text((40, 60), "Agenda & Introduction", fill=(20, 20, 20), font_size=40)
    td.text((40, 125), "Ericsson Response & Connect to Learn", fill=(30, 30, 30), font_size=26)
    td.text((40, 175), "- Overview of goals, architecture, and hackathon tracks", fill=(30, 30, 30), font_size=22)

    dark_card = Image.new("RGB", (W, H), (20, 20, 24))
    dd = ImageDraw.Draw(dark_card)
    dd.text((60, 120), "Video subtitle card caption", fill=(230, 230, 230), font_size=28)
    dd.text((60, 170), "Field operations documentary clip", fill=(210, 210, 210), font_size=22)

    def build_slide(n_bullets):
        img = Image.new("RGB", (W, H), (245, 245, 248))
        dr = ImageDraw.Draw(img)
        dr.text((40, 40), "Key Network Innovations", fill=(15, 15, 20), font_size=36)
        dr.text((40, 88), "Connecting rural schools globally across regions", fill=(40, 40, 50), font_size=22)
        dr.text((40, 122), "Architecture & phased roll-out schedule overview", fill=(40, 40, 50), font_size=22)
        for k in range(n_bullets):
            dr.text((60, 165 + 36 * k), f"- Milestone capability {k + 1} for deployment", fill=(25, 25, 30), font_size=22)
        return img

    imgs = [title] + [noise() for _ in range(6)] + [dark_card] + [noise() for _ in range(6)] + [
        build_slide(1), build_slide(2), build_slide(3)
    ]
    d = tmp_path / "derived" / "a_mix"
    (d / "frames").mkdir(parents=True)
    durs = [3.0] + [1.0] * 13 + [2.0, 2.0, 60.0]
    frames, t = [], 0.0
    for i, (im, dur_s) in enumerate(zip(imgs, durs)):
        rel = f"frames/f{i + 1}.webp"
        im.save(d / rel, "WEBP", quality=75)
        frames.append({"id": f"f{i + 1}", "t_start": round(t, 3), "t_end": round(t + dur_s, 3),
                       "path": rel, "bytes": (d / rel).stat().st_size,
                       "phash": phash_file(d / rel), "matched_slide": None})
        t += dur_s
    r = U.apply(frames, d, U.config({}))
    assert r["info"]["unique_slide_count"] == 2, [s["members"] for s in r["slides"]]
    assert "f8" not in [m for s in r["slides"] for m in s["members"]]
    assert "f17" in r["slides"][1]["members"]


def test_keeps_gradient_hero_photo_sparse_white_and_corner_pip_slides(tmp_path):
    """Keeps two-tone gradient, half/hero-photo, sparse white, and compact corner-PIP minimalist slides."""
    yy = np.linspace(0.0, 1.0, H)[:, None]
    xx = np.linspace(0.0, 1.0, W)[None, :]

    # 1. Two-tone gradient title slide
    grad_rgb = np.stack([
        (25 + 140 * xx * (1.0 - 0.3 * yy)).astype(np.uint8),
        (60 + 95 * yy + 0.0 * xx).astype(np.uint8),
        (195 - 75 * xx + 30 * yy).astype(np.uint8),
    ], axis=-1)
    grad_slide = Image.fromarray(grad_rgb)
    ImageDraw.Draw(grad_slide).text((80, 140), "Imagine Possible\nConnected Education", fill=(250, 250, 255), font_size=42)

    # 2. Half-photo / hero-photo slide (smooth scenic bands + dark text panel with crisp bullets)
    hero_rgb = np.zeros((H, W, 3), dtype=np.uint8)
    photo_wave = 128 + 70 * np.sin(xx[:, :W // 2] * 9.0) * np.cos(yy * 7.0)
    hero_rgb[:, :W // 2, 0] = np.clip(photo_wave + 25, 0, 255).astype(np.uint8)
    hero_rgb[:, :W // 2, 1] = np.clip(photo_wave, 0, 255).astype(np.uint8)
    hero_rgb[:, :W // 2, 2] = np.clip(photo_wave - 20, 0, 255).astype(np.uint8)
    hero_rgb[:, W // 2:] = (24, 30, 44)
    hero_slide = Image.fromarray(hero_rgb)
    hd = ImageDraw.Draw(hero_slide)
    hd.text((W // 2 + 24, 55), "Field Results", fill=(245, 245, 250), font_size=34)
    for k in range(4):
        hd.text((W // 2 + 24, 120 + k * 42), f"- Impact milestone {k + 1}", fill=(215, 220, 235), font_size=22)

    # 3. Sparse dark-text-on-white closing slide
    sparse_white = Image.new("RGB", (W, H), (248, 249, 250))
    sd = ImageDraw.Draw(sparse_white)
    sd.text((140, 125), "Thank you for listening", fill=(22, 24, 28), font_size=36)
    sd.text((225, 200), "Special thanks to the team", fill=(65, 70, 80), font_size=20)

    # 4. Minimalist dark slide with compact moving corner PIP (>=32 frames so detect_overlay fires)
    def pip_dark_slide(heading: str, subtitle: str, seed: int) -> Image.Image:
        img = Image.new("RGB", (W, H), (16, 17, 21))
        dr = ImageDraw.Draw(img)
        dr.text((70, 120), heading, fill=(238, 240, 245), font_size=34)
        dr.text((70, 180), subtitle, fill=(185, 190, 200), font_size=22)
        rng = np.random.default_rng(seed)
        pip = rng.integers(30, 230, (78, 114, 3), dtype=np.uint8)
        img.paste(Image.fromarray(pip), (W - 122, H - 84))
        return img

    seq = (
        [grad_slide] * 4
        + [hero_slide] * 4
        + [sparse_white] * 4
        + [pip_dark_slide("Recursive Decision Models", "Operating System One", 10 + i) for i in range(12)]
        + [pip_dark_slide("Three Rules", "Small checks escalate only when needed", 100 + i) for i in range(12)]
    )
    d, frames, _ = build(tmp_path, seq, step=4.0)
    r = U.apply(frames, d, U.config({}))
    assert r["info"]["unique_slide_count"] == 5, [s["representative"] for s in r["slides"]]
    assert r["v3"]["slide_like_frames"] == len(seq)


def test_drops_face_lobby_webcam_and_short_video_ad_burst_tail(tmp_path):
    """Drops Teams-style face lobbies, soft live webcams, and full moving bursts + tails while keeping flanking slides."""
    yy = np.linspace(-1.0, 1.0, H)[:, None]
    xx = np.linspace(-1.0, 1.0, W)[None, :]

    def soft_portrait_blob(cx: float, cy: float, phase: float) -> np.ndarray:
        dist2 = ((xx - cx) / 0.28) ** 2 + ((yy - cy) / 0.42) ** 2
        env = np.exp(-dist2 * 2.5)
        tex = 128 + 65 * np.sin(8.0 * xx + phase) * np.cos(7.0 * yy - phase)
        bg = 48 + 20 * xx + 15 * yy
        gray = np.clip(bg * (1.0 - env) + tex * env, 0, 255).astype(np.uint8)
        return np.stack([gray, np.clip(gray - 8, 0, 255), np.clip(gray - 14, 0, 255)], axis=-1)

    def make_slide(title: str, body: str) -> Image.Image:
        img = Image.new("RGB", (W, H), (242, 245, 250))
        dr = ImageDraw.Draw(img)
        dr.text((50, 50), title, fill=(15, 25, 45), font_size=36)
        for k in range(5):
            dr.text((55, 130 + 36 * k), f"- {body} item {k + 1}", fill=(35, 45, 65), font_size=22)
        return img

    def ad_burst_frame(k: int, crisp: bool) -> Image.Image:
        rng = np.random.default_rng(700 + k)
        base = soft_portrait_blob(-0.2 + 0.08 * (k % 4), 0.0, float(k))
        if crisp:
            # High-contrast graphic overlay mimicking ad card / YouTube player overlay
            base[H - 95:H - 25, 40:440] = (20, 20, 26)
            img = Image.fromarray(base)
            dr = ImageDraw.Draw(img)
            dr.text((55, H - 82), f"WATCH NOW CLIP {k % 3}", fill=(245, 245, 245), font_size=24)
            # Smooth continuous shot step (< cut_thresh) when continuing same video shot
            patch = rng.integers(80, 170, (44, 60, 3), dtype=np.uint8)
            img.paste(Image.fromarray(patch), (460 + (k % 3) * 8, 90))
            return img
        return Image.fromarray(base)

    # Teams face lobby lookalike: dark outer bars + soft portrait blobs + minimal UI chrome
    lobby = Image.fromarray(soft_portrait_blob(0.0, -0.05, 1.2))
    ImageDraw.Draw(lobby).rectangle([0, 0, W, 24], fill=(32, 34, 48))

    # Build timeline: held slide A (10s), lobby (12s), live webcam (12s),
    # then a rapid video/ad burst [2 raw non-doc + 5 short crisp burst frames whose last 2 sit past nondoc window],
    # followed by held slide B (10s).
    slide_a = make_slide("Opening Overview", "Architecture summary")
    slide_b = make_slide("Final Roadmap", "Deployment plan")
    frames_meta = [
        (slide_a, 10.0),
        (lobby, 12.0),
        (Image.fromarray(soft_portrait_blob(0.15, 0.0, 2.5)), 12.0),
        (ad_burst_frame(0, False), 1.0),
        (ad_burst_frame(1, False), 1.0),
        (ad_burst_frame(2, True), 2.0),
        (ad_burst_frame(3, True), 1.5),
        (ad_burst_frame(4, True), 1.5),
        (ad_burst_frame(5, True), 1.5),
        (ad_burst_frame(6, True), 1.5),
        (slide_b, 10.0),
    ]
    d = tmp_path / "derived" / "a_burst"
    (d / "frames").mkdir(parents=True)
    frames, t = [], 0.0
    for i, (im, dur_s) in enumerate(frames_meta):
        rel = f"frames/f{i + 1}.webp"
        im.save(d / rel, "WEBP", quality=75)
        frames.append({"id": f"f{i + 1}", "t_start": round(t, 3), "t_end": round(t + dur_s, 3),
                       "path": rel, "bytes": (d / rel).stat().st_size,
                       "phash": phash_file(d / rel), "matched_slide": None})
        t += dur_s
    r = U.apply(frames, d, U.config({}))
    kept_members = [m for s in r["slides"] for m in s["members"]]
    assert r["info"]["unique_slide_count"] == 2, [s["representative"] for s in r["slides"]]
    assert "f1" in kept_members and "f11" in kept_members
    for bad in ("f2", "f3", "f4", "f5", "f6", "f7", "f8", "f9", "f10"):
        assert bad not in kept_members, f"unexpectedly kept non-slide frame {bad}"


def test_compact_pip_mask_accepts_corner_and_rejects_centered_motion(tmp_path):
    """_compact_pip_mask masks localized corner PIPs and rejects centered live boxes."""
    cfg = U.config({})
    rng = np.random.default_rng(42)

    def make_seq(box_xy, name):
        seq = []
        for i in range(34):
            img = Image.new("RGB", (W, H), (22, 24, 30))
            ImageDraw.Draw(img).text((40, 40), "Static Slide", fill=(235, 235, 240), font_size=30)
            x0, y0, bw, bh = box_xy
            img.paste(Image.fromarray(rng.integers(20, 240, (bh, bw, 3), dtype=np.uint8)), (x0, y0))
            seq.append(img)
        sub = tmp_path / name
        d, frames, _ = build(sub, seq, step=2.0)
        return frames, d

    corner_frames, corner_dir = make_seq((W - 115, H - 80, 110, 76), "corner")
    mask_corner = U._compact_pip_mask(corner_frames, corner_dir, cfg, W, H)
    assert mask_corner is not None
    assert float((~mask_corner).mean()) < 0.10

    center_frames, center_dir = make_seq((230, 120, 120, 80), "center")
    assert U._compact_pip_mask(center_frames, center_dir, cfg, W, H) is None


def test_diarize_separates_many_speakers_without_audio_clips_and_keeps_solo_talk(tmp_path):
    """Text-only diarization separates many distinct speakers (e.g. 8) without saving WAV files and avoids false-splitting 1 speaker."""
    import wave
    from pathlib import Path
    from dso_pipeline import diarize

    sr = 16000
    t_seg = 4.0
    tt = np.arange(int(sr * t_seg)) / sr

    def synth_voice(f0: float, bright: float, formant_hz: float) -> np.ndarray:
        sig = np.zeros_like(tt)
        for h in range(1, 14):
            f = h * f0
            if f > 5500:
                break
            res = np.exp(-0.5 * ((f - formant_hz) / 450.0) ** 2) + 0.35
            amp = res / (h ** (1.4 - 0.6 * bright))
            sig += amp * np.sin(2.0 * np.pi * f * tt)
        return (0.25 * sig / np.max(np.abs(sig))).astype(np.float32)

    def write_wav(path: Path, samples: np.ndarray) -> None:
        clipped = np.clip(samples * 32767.0, -32768.0, 32767.0).astype(np.int16)
        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(clipped.tobytes())

    # 1) 8 distinct speakers (3 turns each), shuffled order, chronological first-appearance naming
    voices = [synth_voice(95.0 + 20.0 * s, 0.1 + 0.08 * s, 450.0 + 180.0 * ((s * 3) % 8)) for s in range(8)]
    order = [0, 1, 2, 3, 4, 5, 6, 7, 2, 5, 0, 7, 1, 4, 6, 3, 7, 0, 4, 2, 6, 1, 3, 5]
    audio8 = np.concatenate([voices[p] for p in order])
    segs8 = [
        {"id": f"s{i + 1}", "start": round(i * t_seg, 2), "end": round((i + 1) * t_seg - 0.1, 2),
         "text": f"turn {i}", "frame_id": "f1", "speaker": None}
        for i in range(len(order))
    ]
    wav8 = tmp_path / "eight.wav"
    write_wav(wav8, audio8)
    res8 = diarize.diarize_wav(wav8, segs8)
    assert len(res8["speakers"]) == 8
    assert [s["speaker"] for s in segs8] == [f"Speaker {p + 1}" for p in order]
    assert not (tmp_path / "audio").exists()

    # 2) Single speaker with subtle natural pitch inflection (+/- 2.5 Hz) stays Speaker 1
    rng = np.random.default_rng(7)
    audio1 = np.concatenate([synth_voice(115.0 + float(rng.uniform(-2.5, 2.5)), 0.35, 700.0) for _ in range(16)])
    segs1 = [
        {"id": f"s{i + 1}", "start": round(i * t_seg, 2), "end": round((i + 1) * t_seg - 0.1, 2),
         "text": f"solo {i}", "frame_id": "f1", "speaker": None}
        for i in range(16)
    ]
    wav1 = tmp_path / "solo.wav"
    write_wav(wav1, audio1)
    res1 = diarize.diarize_wav(wav1, segs1)
    assert len(res1["speakers"]) == 1
    assert all(s["speaker"] == "Speaker 1" for s in segs1)


def test_v3_masks_real_camera_pip_ignores_menubar_cursor_and_merges_build(tmp_path):
    """Smooth corner camera PIP is masked by write_crops; OS menu bar/cursor & timed builds merge cleanly."""
    yy, xx = np.mgrid[0:84, 0:120]

    def cam_patch(phase: float) -> Image.Image:
        # Smooth camera gradient texture (non-random pixel noise) that varies over time
        g = np.clip(110 + 55 * np.sin(xx * 0.08 + phase) * np.cos(yy * 0.07 - phase), 15, 240).astype(np.uint8)
        rgb = np.stack([g, np.clip(g.astype(np.int16) - 10, 0, 255).astype(np.uint8),
                        np.clip(g.astype(np.int16) - 20, 0, 255).astype(np.uint8)], axis=-1)
        return Image.fromarray(rgb)

    def make_bg(extra_bullet: str | None = None, menubar: bool = False, cursor_xy: tuple[int, int] | None = None):
        img = Image.new("RGB", (W, H), (242, 244, 248))
        dr = ImageDraw.Draw(img)
        dr.text((40, 28), "Architecture Walkthrough", fill=(18, 22, 30), font_size=34)
        dr.text((45, 110), "- Core OpenCV deduplication pipeline", fill=(30, 34, 42), font_size=22)
        if extra_bullet:
            dr.rectangle([45, 160, 430, 206], fill=(32, 74, 156))
            dr.text((55, 168), f"- {extra_bullet}", fill=(245, 247, 250), font_size=24)
        if menubar:
            dr.rectangle([0, 0, 380, 7], fill=(165, 170, 178))
        if cursor_xy:
            cx, cy = cursor_xy
            dr.rectangle([cx, cy, cx + 10, cy + 10], fill=(10, 10, 10))
        return img

    imgs: list[Image.Image] = []
    durs: list[float] = []
    # Slide 1 build step (9s -> >4s build gate, <=3 frames) then settled Slide 1 (24s -> <45s anchor gate), with moving camera PIP & cursor/menubar
    for i in range(3):
        im = make_bg(extra_bullet=None, menubar=(i == 0), cursor_xy=(260 + i * 5, 220))
        im.paste(cam_patch(i * 0.5), (W - 130, H - 90))
        imgs.append(im)
        durs.append(3.0)
    for i in range(16):
        im = make_bg(extra_bullet="Progressive bullet landed", menubar=(i == 0), cursor_xy=(300 + i * 2, 230))
        im.paste(cam_patch(10.0 + i * 0.6), (W - 130, H - 90))
        imgs.append(im)
        durs.append(1.5)
    # Slide 2 with menu bar & tiny cursor variation should collapse to 1 clean slide
    for i in range(12):
        im = Image.new("RGB", (W, H), (242, 244, 248))
        dr = ImageDraw.Draw(im)
        dr.text((40, 28), "Closing Summary & Next Steps", fill=(18, 22, 30), font_size=34)
        dr.text((45, 115), "- Edge filtering + diarization active", fill=(30, 34, 42), font_size=22)
        if i == 0:
            dr.rectangle([0, 0, 380, 7], fill=(165, 170, 178))
        dr.rectangle([280 + i, 210, 289 + i, 219], fill=(12, 12, 12))
        im.paste(cam_patch(30.0 + i * 0.7), (W - 130, H - 90))
        imgs.append(im)
        durs.append(2.0)

    d = tmp_path / "derived" / "a_pip_build"
    (d / "frames").mkdir(parents=True)
    frames, t = [], 0.0
    for i, (im, dur_s) in enumerate(zip(imgs, durs)):
        rel = f"frames/f{i + 1}.webp"
        im.save(d / rel, "WEBP", quality=75)
        frames.append({"id": f"f{i + 1}", "t_start": round(t, 3), "t_end": round(t + dur_s, 3),
                       "path": rel, "bytes": (d / rel).stat().st_size,
                       "phash": phash_file(d / rel), "matched_slide": None})
        t += dur_s

    r = U.apply(frames, d, U.config({}))
    assert r["info"]["unique_slide_count"] == 2, [(s["representative"], s["members"]) for s in r["slides"]]
    assert all(s.get("pip_box") is not None for s in r["slides"])
    U.write_crops(r, d)
    assert all(f["path"].startswith("frames/slide-") for f in r["frames"])
    # Masked PIP region in the saved slide must be uniform (camera patch replaced by slide fill color)
    with Image.open(d / r["slides"][0]["path"]) as out_im:
        patch = np.asarray(out_im.convert("RGB"))[H - 80 :, W - 115 :]
        assert float(patch.std()) < 4.0
