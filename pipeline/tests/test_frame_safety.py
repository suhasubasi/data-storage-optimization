"""Unique-slide comparer and representative safety. Synthetic images are TEST ONLY (never measured savings)."""
import numpy as np

from dso_pipeline import unique_slides as U


def test_comparer_checks_partial_bottom_and_right_blocks():
    th = np.zeros((3, 23, 23), dtype=np.int16)
    th[1, 22, 22] = 255
    th[2, 0, 22] = 255
    cfg = U.config({"unique_slides": {"mode": "v2"}})
    cmp = U._Comparer(th, np.zeros((23, 23), dtype=bool), cfg)
    assert (cmp.block_max(0, [1, 2]) > 0).all()


def test_comparer_checks_unmasked_pixels_in_mostly_masked_blocks():
    # v1 skipped blocks that were more than half under the mask, so a change there was never seen.
    th = np.zeros((2, 20, 20), dtype=np.int16)
    th[1, 0, 0] = 255
    mask = np.ones((20, 20), dtype=bool)
    mask[0, 0] = False
    cmp = U._Comparer(th, mask, U.config({"unique_slides": {"mode": "v2"}}))
    assert cmp.block_max(0, [1])[0] == 1


def test_final_representative_covers_every_member(tmp_path):
    from PIL import Image
    from test_unique_slides import build

    # A is within tolerance of B and C, but B and C are not within tolerance.
    # Longest-held B must not replace C solely because both matched seed A.
    a = np.zeros((180, 320, 3), dtype=np.uint8)
    b, c = a.copy(), a.copy()
    b[1:5, 1:5] = 255
    c[10:14, 10:14] = 255
    base, frames, _ = build(tmp_path, [Image.fromarray(x) for x in (a, b, c)])
    frames[1]['t_end'] = 30
    frames[2]['t_start'], frames[2]['t_end'] = 30, 33
    cfg = U.config({"unique_slides": {"mode": "v2"}})
    cfg.update(max_phash_distance=64, max_block_change_fraction=0.06)
    result = U.apply(frames, base, cfg)
    th = U._thumbs([base / f['path'] for f in frames], 320, 180)
    cmp = U._Comparer(th, np.zeros((180, 320), dtype=bool), cfg)
    ids = {f['id']: i for i, f in enumerate(frames)}
    # The case really happened: all three are one slide and the longest (B) was rejected for the seed (A).
    assert [s['members'] for s in result['slides']] == [['f1', 'f2', 'f3']]
    assert result['slides'][0]['representative'] == 'f1'
    assert {v['frame_id'] for v in result['verification']} == {'f1', 'f2', 'f3'}
    for slide in result['slides']:
        assert (cmp.block_max(ids[slide['representative']],
                             [ids[x] for x in slide['members']]) <= 0.06).all()


def test_longest_frame_is_kept_when_it_covers_every_member(tmp_path):
    from PIL import Image
    from test_unique_slides import build

    a = np.zeros((180, 320, 3), dtype=np.uint8)
    b = a.copy()
    b[1:5, 1:5] = 255
    base, frames, _ = build(tmp_path, [Image.fromarray(x) for x in (a, b)])
    frames[1]['t_end'] = 30
    cfg = U.config({"unique_slides": {"mode": "v2"}})
    cfg.update(max_phash_distance=64, max_block_change_fraction=0.06)
    result = U.apply(frames, base, cfg)
    assert [(s['representative'], s['members']) for s in result['slides']] == [('f2', ['f1', 'f2'])]
