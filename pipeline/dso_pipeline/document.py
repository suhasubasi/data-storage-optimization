"""PDF -> one entry per page: text, normalised-text SHA-256, page image (WebP) + pHash.

The three hashes (CONTRACTS.md): file SHA-256 (original.sha256), per-page text_sha256, per-page phash.
No corpus-wide grouping here; the backend duplicate engine matches across files.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pymupdf
from PIL import Image

from .common import Status, phash_file, text_sha256

# Ericsson-style document number, e.g. "1/221 02-FGB 101" or "EN/LZT 123 4567". Heuristic: only
# reported when literally present in the file name, PDF metadata or first-page text.
_DOC_NO = re.compile(r"\b(\d{1,4}/\d{3}\s?\d{2}-[A-Z]{2,5}\s?\d{2,6}(?:\s?[A-Z]{1,3})?|[A-Z]{2,4}/[A-Z]{3}\s?\d{3}\s?\d{3,4})\b")
# Revision only with an explicit label ("Rev A", "Revision: PA1", "rev. B", "Hackathon_RevB").
_REV = re.compile(r"(?:^|\b|(?<=[_\-\s]))(?:rev(?:ision)?)\.?\s*[:\-]?\s*([A-Z]{1,2}\d{0,2})\b", re.IGNORECASE)
_PDF_DATE = re.compile(r"^D:(\d{4})(\d{2})?(\d{2})?")


def _trim_letterbox(
    img: Image.Image, deck_box: tuple[int, int, int, int] | None = None
) -> tuple[Image.Image, tuple[int, int, int, int] | None]:
    """Trim uniform top/bottom or left/right letterbox margin bars before computing pHash."""
    w, h = img.size
    if w < 32 or h < 32:
        return img, deck_box
    a = np.asarray(img.convert("L"))
    row_mean, row_std = a.mean(axis=1), a.std(axis=1)
    col_mean, col_std = a.mean(axis=0), a.std(axis=0)

    # 1. Check symmetric 16:9 slide letterbox inside a taller page (e.g. 11x8.5 Letter landscape).
    target_h = int(round(w * 9.0 / 16.0))
    pad_y = (h - target_h) // 2
    if int(0.04 * h) <= pad_y <= int(0.22 * h):
        top_bar, bot_bar = a[:pad_y], a[h - pad_y :]
        if top_bar.std() <= 2.5 and bot_bar.std() <= 2.5 and (
            (top_bar.mean() >= 248 and bot_bar.mean() >= 248) or (top_bar.mean() <= 10 and bot_bar.mean() <= 10)
        ):
            inner_edge = (
                abs(float(row_mean[pad_y : pad_y + 4].mean()) - float(top_bar.mean())) > 6.0
                or abs(float(row_mean[h - pad_y - 4 : h - pad_y].mean()) - float(bot_bar.mean())) > 6.0
                or float(row_std[pad_y : pad_y + 4].max()) > 4.0
                or float(row_std[h - pad_y - 4 : h - pad_y].max()) > 4.0
            )
            if inner_edge or deck_box == (0, pad_y, w, h - pad_y):
                box = (0, pad_y, w, h - pad_y)
                return img.crop(box), box

    # 2. General uniform black outer bars with a crisp boundary step (never trim white slide margins).
    y0, y1, x0, x1 = 0, h, 0, w
    max_my = int(0.22 * h)
    for y in range(int(0.03 * h), max_my):
        if row_std[:y].max() <= 2.5 and float(row_mean[:y].mean()) <= 10.0 and (
            abs(float(row_mean[y]) - float(row_mean[:y].mean())) > 12.0 or row_std[y] > 6.0
        ):
            y0 = y
            break
    for y in range(h - int(0.03 * h), h - max_my, -1):
        if row_std[y:].max() <= 2.5 and float(row_mean[y:].mean()) <= 10.0 and (
            abs(float(row_mean[y - 1]) - float(row_mean[y:].mean())) > 12.0 or row_std[y - 1] > 6.0
        ):
            y1 = y
            break
    max_mx = int(0.22 * w)
    for x in range(int(0.03 * w), max_mx):
        if col_std[:x].max() <= 2.5 and float(col_mean[:x].mean()) <= 10.0 and (
            abs(float(col_mean[x]) - float(col_mean[:x].mean())) > 12.0 or col_std[x] > 6.0
        ):
            x0 = x
            break
    for x in range(w - int(0.03 * w), w - max_mx, -1):
        if col_std[x:].max() <= 2.5 and float(col_mean[x:].mean()) <= 10.0 and (
            abs(float(col_mean[x - 1]) - float(col_mean[x:].mean())) > 12.0 or col_std[x - 1] > 6.0
        ):
            x1 = x
            break
    if (x0 > 0 or y0 > 0 or x1 < w or y1 < h) and (x1 - x0) >= int(0.6 * w) and (y1 - y0) >= int(0.6 * h):
        return img.crop((x0, y0, x1, y1)), deck_box
    return img, deck_box


def _pdf_date(raw: str | None) -> str | None:
    if not raw:
        return None
    m = _PDF_DATE.match(raw.strip())
    if not m:
        return raw.strip() or None
    y, mo, d = m.group(1), m.group(2), m.group(3)
    return "-".join(p for p in (y, mo, d) if p)


def _metadata(doc: pymupdf.Document, filename: str, first_page_text: str) -> dict[str, Any]:
    meta = doc.metadata or {}
    title = (meta.get("title") or "").strip() or None
    author = (meta.get("author") or "").strip() or None
    date = _pdf_date(meta.get("creationDate")) or _pdf_date(meta.get("modDate"))
    doc_number = revision = None
    for src in (filename, meta.get("subject") or "", meta.get("keywords") or "", first_page_text):
        if doc_number is None and (m := _DOC_NO.search(src)):
            doc_number = m.group(1)
        if revision is None and (m := _REV.search(src)):
            revision = m.group(1).upper()
    return {
        "title": title,
        "author": author,
        "doc_number": doc_number,
        "revision": revision,
        "date": date,
        "language": None,
    }


def process_document(input_path: Path, out_dir: Path, thresholds: dict[str, Any], status: Status) -> dict[str, Any]:
    """Returns the kind-specific manifest parts: metadata, slides, derived_files, warnings."""
    dcfg = thresholds.get("document", {})
    max_w = int(dcfg.get("page_image_max_width_px", 1280))
    fmt = dcfg.get("page_image_format", "webp")
    hash_size = int(thresholds.get("phash", {}).get("hash_size", 8))

    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    slides: list[dict[str, Any]] = []
    derived: list[dict[str, Any]] = []
    warnings: list[str] = []

    with pymupdf.open(input_path) as doc:  # read-only open
        if doc.needs_pass:
            raise RuntimeError("PDF is password protected; cannot read pages")
        n = doc.page_count
        if n == 0:
            raise RuntimeError("PDF has no pages")
        first_text = ""
        deck_box: tuple[int, int, int, int] | None = None
        for i, page in enumerate(doc):
            pno = i + 1
            status.progress("rendering pages", i / n, stage_progress=i / n)  # real: pages done / pages
            text = page.get_text("text").strip()
            if i == 0:
                first_text = text
            if not text:
                warnings.append(f"no text layer on page {pno} (scanned image? OCR is out of scope)")

            # Render at most max_w px wide (never upscale above 2x).
            zoom = min(max_w / max(page.rect.width, 1.0), 2.0)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            img, deck_box = _trim_letterbox(img, deck_box)
            rel = f"pages/p{pno}.{fmt}"
            dest = out_dir / rel
            img.save(dest, format=fmt.upper(), quality=75, method=4)
            nbytes = dest.stat().st_size
            slides.append(
                {
                    "id": f"p{pno}",
                    "page": pno,
                    "text": text,
                    "text_sha256": text_sha256(text),
                    # Hash the saved file so anyone can recompute it from disk.
                    "phash": phash_file(dest, hash_size),
                    "path": rel,
                    "bytes": nbytes,
                }
            )
            derived.append({"path": rel, "bytes": nbytes, "kind": "page_image"})
        metadata = _metadata(doc, input_path.name, first_text)

    return {
        "metadata": metadata,
        "segments": [],
        "frames": [],
        "slides": slides,
        "derived_files": derived,
        "model": None,
        "frame_threshold": None,
        "warnings": warnings,
    }
