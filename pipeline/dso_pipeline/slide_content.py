"""Local visual gate for text presentations; no model, OCR service or face data.

Require both a dominant flat background and several aligned glyph-sized marks.
This deliberately excludes picture-only slides as well as ordinary camera footage.
"""
import numpy as np
from PIL import Image
from scipy import ndimage


def has_slide_content(image: Image.Image) -> bool:
    image = image.convert("RGB")
    image.thumbnail((800, 450), Image.Resampling.LANCZOS)
    rgb = np.asarray(image, dtype=np.int16)
    h, w = rgb.shape[:2]
    if min(h, w) < 60:
        return False
    # Find a large uniform slide background, including dark themes. Texture in
    # faces, clothing and scenery should not qualify merely by average colour.
    smooth = np.max(np.abs(rgb - ndimage.uniform_filter(rgb.astype(float), size=(5, 5, 1))), axis=2) < 5
    bins = (rgb // 32).astype(int)
    codes = bins[:, :, 0] * 64 + bins[:, :, 1] * 8 + bins[:, :, 2]
    counts = np.bincount(codes[smooth], minlength=512)
    dominant = int(counts.argmax())
    if counts[dominant] / (w * h) < .35:
        return False
    background = np.median(rgb[smooth & (codes == dominant)], axis=0)
    ink = np.max(np.abs(rgb - background), axis=2) > 55
    labels, _ = ndimage.label(ink)
    rows = []
    for component in ndimage.find_objects(labels):
        if component is None:
            continue
        y, x = component
        cw, ch = x.stop - x.start, y.stop - y.start
        if 2 <= cw <= w * .06 and 5 <= ch <= h * .12 and .08 <= cw / ch <= 3:
            rows.append((y.start + y.stop) / 2)
    # Text has aligned characters, rather than scattered isolated edges.
    return any(sum(abs(y - other) <= max(3, h * .012) for other in rows) >= 10 for y in rows)
