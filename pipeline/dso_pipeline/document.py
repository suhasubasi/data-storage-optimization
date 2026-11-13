"""PDF -> one entry per page: text, normalised-text SHA-256, page image (WebP) + pHash.

The three hashes (CONTRACTS.md): file SHA-256 (original.sha256), per-page text_sha256, per-page phash.
No corpus-wide grouping here; the backend duplicate engine matches across files.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pymupdf
from PIL import Image

from .common import Status, phash_file, text_sha256

# Ericsson-style document number, e.g. "1/221 02-FGB 101" or "EN/LZT 123 4567". Heuristic: only
# reported when literally present in the file name, PDF metadata or first-page text.
_DOC_NO = re.compile(r"\b(\d{1,4}/\d{3}\s?\d{2}-[A-Z]{2,5}\s?\d{2,6}(?:\s?[A-Z]{1,3})?|[A-Z]{2,4}/[A-Z]{3}\s?\d{3}\s?\d{3,4})\b")
# Revision only with an explicit label ("Rev A", "Revision: PA1", "rev. B").
_REV = re.compile(r"\b(?:rev(?:ision)?)\.?\s*[:\-]?\s*([A-Z]{1,2}\d{0,2})\b", re.IGNORECASE)
_PDF_DATE = re.compile(r"^D:(\d{4})(\d{2})?(\d{2})?")


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
        for i, page in enumerate(doc):
            pno = i + 1
            status.progress("rendering pages", i / n)
            text = page.get_text("text").strip()
            if i == 0:
                first_text = text
            if not text:
                warnings.append(f"no text layer on page {pno} (scanned image? OCR is out of scope)")

            # Render at most max_w px wide (never upscale above 2x).
            zoom = min(max_w / max(page.rect.width, 1.0), 2.0)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
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
