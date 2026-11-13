"""Human-readable exports built ON REQUEST from the real derived files (nothing is cached, so these
files add no stored bytes):

  * transcript.txt : the whole script as plain text (segments in time order; or page text for PDFs)
  * slides.pptx    : one slide per UNIQUE slide (unique-slide pass), time order of first appearance,
                     speaker notes = when it was on screen + what was said while it was on screen
  * slides.pdf     : the same pictures, one page each, with a one-line caption

Only real data: the images are the kept derived frames / page images, the text is the stored
transcript / page text. Speaker names are not identified (out of scope) and nothing is rewritten.
"""
from __future__ import annotations

import io
import re
import unicodedata
import zlib
from dataclasses import dataclass, field
from pathlib import Path

from dso_contracts.models import ErrorCode

from . import db, settings
from .errors import ApiError
from .services import get_asset_row, metadata_or_empty, unique_slides_info

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SOURCE_LABEL = {"sharepoint": "SharePoint", "onedrive": "OneDrive", "ericsson_play": "Ericsson Play"}


def hms(t: float | None) -> str:
    if t is None:
        return "--:--:--"
    s = max(0, int(t))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def safe_stem(filename: str) -> str:
    stem = Path(filename).stem
    ascii_ = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    ascii_ = re.sub(r"[^A-Za-z0-9._ -]+", "", ascii_).strip(" .") or "export"
    return ascii_[:120]


def _clean(s: str) -> str:
    return _CTRL.sub("", s or "")


# ---------------------------------------------------------------------------------------------
# plain text
# ---------------------------------------------------------------------------------------------
def _header(row, meta, pipeline_model: str | None) -> list[str]:
    lines = [meta.title or row["filename"],
             f"File: {row['filename']}  (asset {row['id']}, SHA-256 {row['sha256']})",
             f"Source: {SOURCE_LABEL.get(row['source_system'], row['source_system'])} (simulated source label; the file "
             f"itself is real) · owner {row['owner']}"]
    if row["kind"] == "video":
        bits = [f"language: {meta.language or 'unknown'}"]
        if meta.duration_seconds:
            bits.append(f"length: {hms(meta.duration_seconds)}")
        if pipeline_model:
            bits.append(f"speech-to-text: {pipeline_model} (local)")
        lines.append(" · ".join(bits))
        lines.append("Automatic transcript, unedited. Speaker names are not identified (out of scope).")
    else:
        lines.append("Text layer of each page, unedited.")
    lines.append(f"Original (kept): /files/originals/{row['id']}/{row['filename']}")
    return lines


def transcript_text(asset_id: str, timestamps: bool = True) -> tuple[str, str]:
    import json

    with db.read() as conn:
        row = get_asset_row(conn, asset_id)
        if row["manifest_bytes"] is None:
            raise ApiError(ErrorCode.conflict, f"{asset_id} has not been processed yet, so there is no text to export.")
        meta = metadata_or_empty(row)
        model = (json.loads(row["pipeline_json"]) or {}).get("model") if row["pipeline_json"] else None
        out = _header(row, meta, model) + [""]
        if row["kind"] == "video":
            segs = conn.execute('SELECT * FROM segments WHERE asset_id = ? ORDER BY "start", id', (asset_id,)).fetchall()
            frames = {f["id"]: f["path"] for f in conn.execute("SELECT id, path FROM frames WHERE asset_id = ?", (asset_id,))}
            if not segs:
                out.append("(no speech detected)")
            elif timestamps:
                out += [f"[{hms(s['start'])} - {hms(s['end'])}] {_clean(s['text']).strip()}" for s in segs]
            else:  # flowing text; a new paragraph whenever the picture on screen changes to another slide
                para: list[str] = []
                last = object()
                for s in segs:
                    pic = frames.get(s["frame_id"]) if s["frame_id"] else None
                    if para and pic != last:
                        out += [" ".join(para), ""]
                        para = []
                    para.append(_clean(s["text"]).strip())
                    last = pic
                if para:
                    out.append(" ".join(para))
        else:
            pages = conn.execute("SELECT page, text FROM slides WHERE asset_id = ? ORDER BY page", (asset_id,)).fetchall()
            for p in pages:
                out += [f"--- Page {p['page']} ---", _clean(p["text"]).strip() or "(no text on this page)", ""]
    text = "\n".join(out).rstrip() + "\n"
    return f"{safe_stem(row['filename'])}.transcript.txt", text


# ---------------------------------------------------------------------------------------------
# unique slides (shared by PPTX and PDF)
# ---------------------------------------------------------------------------------------------
@dataclass
class DeckSlide:
    number: int
    path: Path
    ranges: list[tuple[float, float]] = field(default_factory=list)
    page: int | None = None
    said: list[str] = field(default_factory=list)
    source_frames: int = 0


@dataclass
class Deck:
    asset_id: str
    filename: str
    title: str
    kind: str
    source: str
    owner: str
    sha256: str
    slides: list[DeckSlide]
    raw_frames: int | None


def load_deck(asset_id: str) -> Deck:
    with db.read() as conn:
        row = get_asset_row(conn, asset_id)
        if row["manifest_bytes"] is None:
            raise ApiError(ErrorCode.conflict, f"{asset_id} has not been processed yet, so there are no slides to export.")
        meta = metadata_or_empty(row)
        base = settings.DERIVED_DIR / asset_id
        slides: list[DeckSlide] = []
        raw = None
        if row["kind"] == "video":
            us = unique_slides_info(row)
            if not us:
                raise ApiError(ErrorCode.conflict,
                               "The unique-slide pass has not run for this recording yet, so a deck would repeat the "
                               "same slide many times. Run it first (backend: python -m app.cli unique-slides "
                               f"{asset_id}).")
            raw = us.get("source_frame_count")
            frames = conn.execute("SELECT * FROM frames WHERE asset_id = ? ORDER BY t_start, id", (asset_id,)).fetchall()
            by_path: dict[str, DeckSlide] = {}
            by_frame: dict[str, DeckSlide] = {}
            for f in frames:
                d = by_path.get(f["path"])
                if d is None:
                    d = by_path[f["path"]] = DeckSlide(number=len(by_path) + 1, path=base / f["path"])
                d.ranges.append((f["t_start"], f["t_end"]))
                by_frame[f["id"]] = d
            for s in conn.execute('SELECT frame_id, text FROM segments WHERE asset_id = ? ORDER BY "start", id', (asset_id,)):
                if s["frame_id"] in by_frame:
                    by_frame[s["frame_id"]].said.append(_clean(s["text"]).strip())
            slides = list(by_path.values())
        else:
            for p in conn.execute("SELECT page, text, path FROM slides WHERE asset_id = ? ORDER BY page", (asset_id,)):
                slides.append(DeckSlide(number=p["page"], path=base / p["path"], page=p["page"],
                                        said=[_clean(p["text"]).strip()]))
        for d in slides:
            if not d.path.is_file():
                raise ApiError(ErrorCode.not_found, f"Derived image missing on disk: {d.path.name}")
        return Deck(asset_id=asset_id, filename=row["filename"], title=meta.title or row["filename"], kind=row["kind"],
                    source=SOURCE_LABEL.get(row["source_system"], row["source_system"]), owner=row["owner"],
                    sha256=row["sha256"], slides=slides, raw_frames=raw)


def _ranges_text(d: DeckSlide) -> str:
    if d.page is not None:
        return f"page {d.page}"
    return ", ".join(f"{hms(a)}-{hms(b)}" for a, b in d.ranges)


def _jpeg(path: Path, quality: int = 85) -> tuple[bytes, int, int]:
    from PIL import Image

    with Image.open(path) as im:
        rgb = im.convert("RGB")
        buf = io.BytesIO()
        rgb.save(buf, format="JPEG", quality=quality, optimize=True)
        return buf.getvalue(), rgb.width, rgb.height


def _deck_intro(deck: Deck) -> list[str]:
    what = (f"{len(deck.slides)} unique slides from {deck.raw_frames} extracted key frames"
            if deck.kind == "video" else f"{len(deck.slides)} pages")
    return [deck.title, f"{deck.filename}", f"{what} · asset {deck.asset_id} · SHA-256 {deck.sha256[:16]}...",
            f"Source: {deck.source} (simulated source label) · owner {deck.owner}",
            "Built from the stored derived files; the original is kept. Slide notes = when the slide was on screen "
            "and the automatic transcript said meanwhile (unedited, no speaker names)."]


# ---------------------------------------------------------------------------------------------
# PowerPoint
# ---------------------------------------------------------------------------------------------
def slides_pptx(asset_id: str) -> tuple[str, bytes]:
    try:
        from pptx import Presentation
        from pptx.util import Emu, Pt
    except ImportError as e:  # pragma: no cover - dependency missing on this machine
        raise ApiError(ErrorCode.internal_error, "PowerPoint export needs python-pptx in the backend venv "
                                                 "(pip install -r backend/requirements.txt).") from e
    deck = load_deck(asset_id)
    prs = Presentation()
    W, H = Emu(12192000), Emu(6858000)  # 13.333 x 7.5 in (16:9)
    prs.slide_width, prs.slide_height = W, H
    blank = prs.slide_layouts[6]

    intro = prs.slides.add_slide(blank)
    tb = intro.shapes.add_textbox(Emu(600000), Emu(1500000), W - Emu(1200000), H - Emu(3000000))
    tf = tb.text_frame
    tf.word_wrap = True
    for i, line in enumerate(_deck_intro(deck)):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.size = Pt(32 if i == 0 else 16)
        p.font.bold = i == 0

    for d in deck.slides:
        data, iw, ih = _jpeg(d.path)
        s = prs.slides.add_slide(blank)
        scale = min(W / iw, H / ih)
        w, h = int(iw * scale), int(ih * scale)
        s.shapes.add_picture(io.BytesIO(data), int((W - w) / 2), int((H - h) / 2), w, h)
        label = f"Slide {d.number}/{len(deck.slides)} · " + (
            f"on screen {_ranges_text(d)}" if d.page is None else _ranges_text(d))
        notes = [label, f"Source: {deck.filename} ({deck.asset_id})", ""]
        notes.append(("Said while on screen: " if d.page is None else "Page text: ") + (" ".join(d.said) or "(nothing)"))
        s.notes_slide.notes_text_frame.text = "\n".join(notes)
    buf = io.BytesIO()
    prs.save(buf)
    return f"{safe_stem(deck.filename)}.slides.pptx", buf.getvalue()


# ---------------------------------------------------------------------------------------------
# PDF (tiny writer: JPEG pages + one Helvetica caption line; streams page by page, no bitmaps kept)
# ---------------------------------------------------------------------------------------------
def _pdf_str(s: str) -> str:
    s = s.encode("latin-1", "replace").decode("latin-1")
    return "(" + s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


class _Pdf:
    def __init__(self) -> None:
        self.buf = io.BytesIO()
        self.offsets: list[int] = []
        self.buf.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        self.pages: list[int] = []
        self.reserve(3)  # 1 catalog, 2 pages, 3 font

    def reserve(self, n: int) -> None:
        self.offsets += [0] * n

    def new_id(self) -> int:
        self.offsets.append(0)
        return len(self.offsets)

    def obj(self, oid: int, body: bytes) -> None:
        self.offsets[oid - 1] = self.buf.tell()
        self.buf.write(f"{oid} 0 obj\n".encode() + body + b"\nendobj\n")

    def stream(self, oid: int, head: str, data: bytes) -> None:
        self.obj(oid, f"<< {head} /Length {len(data)} >>\nstream\n".encode() + data + b"\nendstream")

    def page(self, w: float, h: float, content: bytes, images: dict[str, int]) -> None:
        cid, pid = self.new_id(), self.new_id()
        self.stream(cid, "/Filter /FlateDecode", zlib.compress(content))
        xo = " ".join(f"/{k} {v} 0 R" for k, v in images.items())
        self.obj(pid, (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {w:.2f} {h:.2f}] /Contents {cid} 0 R "
                       f"/Resources << /Font << /F1 3 0 R >> /XObject << {xo} >> >> >>").encode())
        self.pages.append(pid)

    def finish(self) -> bytes:
        self.obj(3, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        kids = " ".join(f"{p} 0 R" for p in self.pages)
        self.obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {len(self.pages)} >>".encode())
        self.obj(1, b"<< /Type /Catalog /Pages 2 0 R >>")
        xref = self.buf.tell()
        self.buf.write(f"xref\n0 {len(self.offsets) + 1}\n0000000000 65535 f \n".encode())
        for off in self.offsets:
            self.buf.write(f"{off:010d} 00000 n \n".encode())
        self.buf.write(f"trailer\n<< /Size {len(self.offsets) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
        return self.buf.getvalue()


def _text_ops(lines: list[tuple[float, float, float, str]]) -> bytes:
    ops = ["BT"]
    for x, y, size, text in lines:
        ops.append(f"/F1 {size:.1f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm {_pdf_str(text)} Tj")
    ops.append("ET")
    return "\n".join(ops).encode("latin-1")


def slides_pdf(asset_id: str) -> tuple[str, bytes]:
    deck = load_deck(asset_id)
    pdf = _Pdf()
    PW, PH, CAP = 960.0, 540.0, 28.0  # points; 16:9 picture area + caption band
    intro = _deck_intro(deck)
    pdf.page(PW, PH + CAP, _text_ops([(48, PH - 120, 26, intro[0][:70])] +
                                     [(48, PH - 170 - 26 * i, 12, t[:150]) for i, t in enumerate(intro[1:])]), {})
    for d in deck.slides:
        data, iw, ih = _jpeg(d.path)
        img = pdf.new_id()
        pdf.stream(img, f"/Type /XObject /Subtype /Image /Width {iw} /Height {ih} /ColorSpace /DeviceRGB "
                        f"/BitsPerComponent 8 /Filter /DCTDecode", data)
        scale = min(PW / iw, PH / ih)
        w, h = iw * scale, ih * scale
        x, y = (PW - w) / 2, CAP + (PH - h) / 2
        cap = f"Slide {d.number}/{len(deck.slides)} · {_ranges_text(d)} · {deck.filename}"
        content = f"q {w:.2f} 0 0 {h:.2f} {x:.2f} {y:.2f} cm /Im{img} Do Q\n".encode() + _text_ops([(12, 9, 9, cap[:190])])
        pdf.page(PW, PH + CAP, content, {f"Im{img}": img})
    return f"{safe_stem(deck.filename)}.slides.pdf", pdf.finish()
