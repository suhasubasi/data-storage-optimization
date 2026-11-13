import io
from types import SimpleNamespace
import numpy as np
from PIL import Image, ImageDraw
from dso_pipeline.slide_content import has_slide_content
from dso_pipeline import video


def slide(background='white', ink='black'):
    image = Image.new('RGB', (800, 450), background)
    ImageDraw.Draw(image).text((35, 40), 'Network performance results', fill=ink, font_size=32)
    return image


def camera():
    return Image.fromarray(np.random.default_rng(8).integers(30, 220, (450, 800, 3), dtype=np.uint8))


def test_light_and_dark_presentations_pass():
    assert has_slide_content(slide())
    assert has_slide_content(slide('#171717', 'white'))


def test_camera_blank_and_picture_only_do_not_pass():
    assert not has_slide_content(camera())
    image = Image.new('RGB', (800, 450), 'white')
    assert not has_slide_content(image)
    ImageDraw.Draw(image).ellipse((250, 30, 550, 420), fill='tan')
    assert not has_slide_content(image)


def test_camera_interval_has_no_slide_and_return_is_kept(monkeypatch, tmp_path):
    images = [camera(), slide(), camera(), slide()]
    process = SimpleNamespace(stdout=io.BytesIO(b''.join(im.tobytes() for im in images)), stderr=io.BytesIO(), wait=lambda: 0)
    monkeypatch.setattr(video.subprocess, 'Popen', lambda *a, **kw: process)
    frames = list(video._key_frames(tmp_path/'input.mp4', (800, 450), 1, 12, 8, .01, 24))
    assert [t for t, _ in frames] == [0, 1, 2, 3]
    assert [image is None for _, image in frames] == [True, False, True, False]


def test_dedup_keeps_camera_gap(tmp_path):
    from test_slide_region import frames_on_disk
    from dso_pipeline import unique_slides as u
    frames = frames_on_disk(tmp_path, [slide(), slide()])
    frames[1].update(t_start=3, t_end=4)
    result = u.apply(frames, tmp_path, u.config({}))
    assert [(f['t_start'], f['t_end']) for f in result['frames']] == [(0, 1), (3, 4)]
    assert result['info']['unique_slide_count'] == 1
