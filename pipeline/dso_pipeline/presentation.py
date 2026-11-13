"""PPTX -> one entry per slide: text, normalised-text SHA-256, slide image (WebP) + pHash.

Same output shape as a PDF (kind 'document', slides 'p<n>'), so the backend duplicate engine compares
PowerPoint slides with PDF pages and with other decks the same way.

- Text: python-pptx, every text frame and table cell on the slide (group shapes included), in the
  deck's own shape order. Speaker notes are NOT part of the slide text (they are not shown on the slide).
- Slide image: a real render of the slide by an office program. We never draw a fake picture:
    1. Microsoft PowerPoint (Windows, via COM): exports each slide as PNG, hidden slides included.
    2. LibreOffice (`soffice`): converts to PDF with hidden slides included, then pages are rendered.
  If neither works, processing stops with a clear error (the frozen schema needs an image + pHash
  per slide, so a text-only result can't be stored without a contract change).
- The original is never opened in place: the renderer works on a temporary COPY.

Renderer choice: env DSO_PPTX_RENDERER = auto (default) | powerpoint | libreoffice.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from .common import Status, phash_file, text_sha256
from .document import _DOC_NO, _REV

# One PNG per slide in `out_dir`, named s<n>.png (1-based). Returns the number of slides rendered.
Renderer = Callable[[Path, Path, int], int]

_PS_EXPORT = r"""
param([string]$In, [string]$OutDir, [int]$Width)
$ErrorActionPreference = 'Stop'
$app = New-Object -ComObject PowerPoint.Application
$pres = $null
try {
  # Open(FileName, ReadOnly=msoTrue, Untitled=msoFalse, WithWindow=msoFalse)
  $pres = $app.Presentations.Open($In, -1, 0, 0)
  $w = $pres.PageSetup.SlideWidth; $h = $pres.PageSetup.SlideHeight
  $height = [int][math]::Round($Width * $h / $w)
  $n = $pres.Slides.Count
  for ($i = 1; $i -le $n; $i++) {
    $pres.Slides.Item($i).Export((Join-Path $OutDir ("s{0}.png" -f $i)), 'PNG', $Width, $height)
  }
  Write-Output "SLIDES $n"
} finally {
  if ($pres -ne $null) { $pres.Close() }
  # Only quit PowerPoint if we left nothing else open (the user may have their own decks open).
  if ($app.Presentations.Count -eq 0) { $app.Quit() }
  [System.Runtime.InteropServices.Marshal]::ReleaseComObject($app) | Out-Null
}
"""


def is_pptx(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            return "ppt/presentation.xml" in z.namelist()
    except (zipfile.BadZipFile, OSError):
        return False


def _shape_texts(shapes) -> list[str]:
    from pptx.enum.shapes import MSO_SHAPE_TYPE

    out: list[str] = []
    for sh in shapes:
        if sh.shape_type == MSO_SHAPE_TYPE.GROUP:
            out.extend(_shape_texts(sh.shapes))
            continue
        if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
            t = sh.text_frame.text.strip()
            if t:
                out.append(t)
        if getattr(sh, "has_table", False) and sh.has_table:
            for row in sh.table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    out.append(" | ".join(cells))
    return out


def read_slides(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """[{page, text, hidden}], core properties. Read-only."""
    from pptx import Presentation

    prs = Presentation(str(path))
    slides = []
    for i, slide in enumerate(prs.slides, start=1):
        text = "\n".join(_shape_texts(slide.shapes))
        slides.append({"page": i, "text": text, "hidden": slide._element.get("show") in ("0", "false")})
    cp = prs.core_properties
    core = {
        "title": (cp.title or "").strip() or None,
        "author": (cp.author or "").strip() or None,
        "subject": cp.subject or "",
        "keywords": cp.keywords or "",
        "created": cp.created,
        "modified": cp.modified,
    }
    return slides, core


def _iso_date(d: datetime | None) -> str | None:
    return d.strftime("%Y-%m-%d") if d else None


def metadata(core: dict[str, Any], filename: str, slide_texts: list[str]) -> dict[str, Any]:
    """Only values really present in the file / file name (never invented). Decks often carry the document
    number in a footer on a later slide, so every slide's text is searched (first match wins)."""
    doc_number = revision = None
    for src in (filename, core["subject"], core["keywords"], *slide_texts):
        if doc_number is None and (m := _DOC_NO.search(src)):
            doc_number = m.group(1)
        if revision is None and (m := _REV.search(src)):
            revision = m.group(1).upper()
    return {
        "title": core["title"],
        "author": core["author"],
        "doc_number": doc_number,
        "revision": revision,
        "date": _iso_date(core["created"]) or _iso_date(core["modified"]),
        "language": None,
    }


def render_powerpoint(pptx: Path, out_dir: Path, width: int) -> int:
    if os.name != "nt":
        raise RuntimeError("Microsoft PowerPoint is only available on Windows")
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        raise RuntimeError("PowerShell not found")
    script = out_dir / "export.ps1"
    script.write_text(_PS_EXPORT, encoding="utf-8")
    try:
        p = subprocess.run([ps, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script),
                            "-In", str(pptx), "-OutDir", str(out_dir), "-Width", str(width)],
                           capture_output=True, text=True, timeout=900)
    finally:
        script.unlink(missing_ok=True)
    if p.returncode != 0 or "SLIDES" not in p.stdout:
        raise RuntimeError(f"PowerPoint export failed: {(p.stderr or p.stdout).strip()[:500]}")
    return int(p.stdout.split("SLIDES", 1)[1].split()[0])


def render_libreoffice(pptx: Path, out_dir: Path, width: int) -> int:
    import pymupdf

    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        raise RuntimeError("LibreOffice (soffice) not found")
    opts = json.dumps({"ExportHiddenSlides": {"type": "boolean", "value": "true"}})
    profile = out_dir / "lo-profile"
    p = subprocess.run([soffice, f"-env:UserInstallation={profile.resolve().as_uri()}", "--headless",
                        "--convert-to", f"pdf:impress_pdf_Export:{opts}", "--outdir", str(out_dir), str(pptx)],
                       capture_output=True, text=True, timeout=900)
    pdf = out_dir / (pptx.stem + ".pdf")
    if p.returncode != 0 or not pdf.is_file():
        raise RuntimeError(f"LibreOffice conversion failed: {(p.stderr or p.stdout).strip()[:500]}")
    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc, start=1):
            zoom = width / max(page.rect.width, 1.0)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            pix.save(str(out_dir / f"s{i}.png"))
        return doc.page_count


RENDERERS: dict[str, Renderer] = {"powerpoint": render_powerpoint, "libreoffice": render_libreoffice}


def render_slides(pptx: Path, out_dir: Path, width: int, renderer: Renderer | None = None) -> tuple[int, str]:
    """Try the renderers in order. Returns (slide count, renderer name)."""
    if renderer is not None:
        return renderer(pptx, out_dir, width), getattr(renderer, "__name__", "custom")
    choice = os.environ.get("DSO_PPTX_RENDERER", "auto").strip().lower()
    names = ["powerpoint", "libreoffice"] if choice == "auto" else [choice]
    errors = []
    for name in names:
        fn = RENDERERS.get(name)
        if fn is None:
            errors.append(f"{name}: unknown renderer")
            continue
        try:
            return fn(pptx, out_dir, width), name
        except Exception as e:  # noqa: BLE001 - try the next renderer
            errors.append(f"{name}: {e}")
            for f in out_dir.glob("s*.png"):
                f.unlink()
    raise RuntimeError("Could not render slide images (needs Microsoft PowerPoint on Windows or LibreOffice). "
                       + " / ".join(errors))


def process_presentation(input_path: Path, out_dir: Path, thresholds: dict[str, Any], status: Status,
                         renderer: Renderer | None = None) -> dict[str, Any]:
    dcfg = thresholds.get("document", {})
    max_w = int(dcfg.get("page_image_max_width_px", 1280))
    fmt = dcfg.get("page_image_format", "webp")
    hash_size = int(thresholds.get("phash", {}).get("hash_size", 8))

    status.progress("reading slides", 0.05)
    slides_in, core = read_slides(input_path)
    if not slides_in:
        raise RuntimeError("The presentation has no slides")
    warnings: list[str] = []
    for s in slides_in:
        if not s["text"]:
            warnings.append(f"no text on slide {s['page']} (picture-only slide? OCR is out of scope)")
        if s["hidden"]:
            warnings.append(f"slide {s['page']} is hidden in the deck (still processed)")

    pages_dir = out_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dso-pptx-") as tmp:
        tmp_dir = Path(tmp)
        copy = tmp_dir / "deck.pptx"
        shutil.copyfile(input_path, copy)  # renderers only ever see a temp copy
        status.progress("rendering slides", 0.1)
        n, used = render_slides(copy, tmp_dir, max_w, renderer)
        if n != len(slides_in):
            raise RuntimeError(f"{used} rendered {n} slides but the deck has {len(slides_in)}; refusing to pair "
                               "text and images that may not belong together")
        slides: list[dict[str, Any]] = []
        derived: list[dict[str, Any]] = []
        for s in slides_in:
            pno = s["page"]
            status.progress("saving slide images", 0.1 + 0.9 * (pno - 1) / n, stage_progress=(pno - 1) / n)
            png = tmp_dir / f"s{pno}.png"
            if not png.is_file():
                raise RuntimeError(f"{used} did not write an image for slide {pno}")
            rel = f"pages/p{pno}.{fmt}"
            dest = out_dir / rel
            with Image.open(png) as im:
                img = im.convert("RGB")
                if img.width > max_w:
                    img = img.resize((max_w, round(img.height * max_w / img.width)), Image.LANCZOS)
                img.save(dest, format=fmt.upper(), quality=75, method=4)
            nbytes = dest.stat().st_size
            slides.append({"id": f"p{pno}", "page": pno, "text": s["text"], "text_sha256": text_sha256(s["text"]),
                           "phash": phash_file(dest, hash_size), "path": rel, "bytes": nbytes})
            derived.append({"path": rel, "bytes": nbytes, "kind": "page_image"})
    warnings.append(f"slide images rendered with {used}")
    return {
        "metadata": metadata(core, input_path.name, [x["text"] for x in slides_in]),
        "segments": [],
        "frames": [],
        "slides": slides,
        "derived_files": derived,
        "model": None,
        "frame_threshold": None,
        "warnings": warnings,
    }
