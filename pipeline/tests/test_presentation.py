"""PPTX ingest. Decks are built inside the tests with python-pptx (tiny synthetic inputs, test-only)."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from pptx import Presentation
from pptx.util import Inches

from conftest import fingerprint, place_original
from helpers import check_manifest
from dso_pipeline import presentation
from dso_pipeline.common import Status, load_thresholds, text_sha256


def make_deck(path: Path, slides: list[tuple[str, str]], hide: tuple[int, ...] = (), title="Test deck") -> Path:
    prs = Presentation()
    for i, (head, body) in enumerate(slides, start=1):
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text = head
        s.placeholders[1].text = body
        if i in hide:
            s._element.set("show", "0")
    rows = prs.slides.add_slide(prs.slide_layouts[5])
    rows.shapes.title.text = "Table slide"
    tbl = rows.shapes.add_table(2, 2, Inches(1), Inches(2), Inches(4), Inches(1)).table
    tbl.cell(0, 0).text, tbl.cell(0, 1).text = "Doc", "1/221 02-FGB 101"
    tbl.cell(1, 0).text, tbl.cell(1, 1).text = "Owner", "Team"
    prs.core_properties.title = title
    prs.core_properties.author = "Tester"
    prs.save(path)
    return path


def fake_renderer(pptx: Path, out_dir: Path, width: int) -> int:
    """Test stand-in for PowerPoint/LibreOffice: one plain PNG per slide (different shade per slide)."""
    n = len(Presentation(str(pptx)).slides)
    for i in range(1, n + 1):
        Image.new("RGB", (width * 2, width * 9 // 8), ((i * 40) % 256, 80, 160)).save(out_dir / f"s{i}.png")
    return n


SLIDES = [("Welcome", "Agenda for today"), ("Energy saving", "Sleep modes lower power per site"),
          ("Summary", "Questions?")]


def test_read_slides_text_tables_hidden(tmp_path):
    deck = make_deck(tmp_path / "d.pptx", SLIDES, hide=(2,))
    slides, core = presentation.read_slides(deck)
    assert [s["page"] for s in slides] == [1, 2, 3, 4]
    assert slides[1]["text"] == "Energy saving\nSleep modes lower power per site" and slides[1]["hidden"]
    assert "Doc | 1/221 02-FGB 101" in slides[3]["text"]
    assert core["title"] == "Test deck" and core["author"] == "Tester"
    md = presentation.metadata(core, "d.pptx", [s["text"] for s in slides])
    assert md["doc_number"] == "1/221 02-FGB 101" and md["revision"] is None  # never invented


def test_is_pptx(tmp_path):
    assert presentation.is_pptx(make_deck(tmp_path / "d.pptx", SLIDES))
    (tmp_path / "x.pptx").write_bytes(b"not a zip")
    assert not presentation.is_pptx(tmp_path / "x.pptx")


def test_process_with_renderer(tmp_path):
    deck = make_deck(tmp_path / "d.pptx", SLIDES, hide=(2,))
    before = fingerprint(deck)
    out = tmp_path / "out"
    out.mkdir()
    parts = presentation.process_presentation(deck, out, load_thresholds(), Status(out), renderer=fake_renderer)
    assert fingerprint(deck) == before
    assert [s["id"] for s in parts["slides"]] == ["p1", "p2", "p3", "p4"]
    for s in parts["slides"]:
        assert s["text_sha256"] == text_sha256(s["text"])
        img = out / s["path"]
        assert img.stat().st_size == s["bytes"] and len(s["phash"]) == 16
        with Image.open(img) as im:
            assert im.width == 1280  # never wider than page_image_max_width_px
    assert "slide 2 is hidden in the deck (still processed)" in parts["warnings"]
    assert parts["metadata"]["title"] == "Test deck"


def test_slide_count_mismatch_refused(tmp_path):
    deck = make_deck(tmp_path / "d.pptx", SLIDES)

    def short(pptx, out_dir, width):
        fake_renderer(pptx, out_dir, width)
        return 2

    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(RuntimeError, match="refusing to pair"):
        presentation.process_presentation(deck, out, load_thresholds(), Status(out), renderer=short)


def run_cli(asset_id, inp, out, env):
    return subprocess.run([sys.executable, "-m", "dso_pipeline", "process", "--asset-id", asset_id, "--kind",
                           "document", "--input", str(inp), "--out", str(out)], capture_output=True, text=True, env=env)


def test_no_renderer_fails_clearly_and_keeps_original(tmp_path, data_dir, monkeypatch):
    deck = make_deck(tmp_path / "d.pptx", SLIDES)
    orig = place_original(data_dir, "a_x1", deck)
    before = fingerprint(orig)
    out = data_dir / "derived" / "a_x1"
    env = {**__import__("os").environ, "DSO_PPTX_RENDERER": "none"}
    p = run_cli("a_x1", orig, out, env)
    assert p.returncode == 1 and "Could not render slide images" in p.stderr
    assert not (out / "manifest.json").exists()
    assert "Could not render slide images" in json.loads((out / "error.json").read_text())["error"]["message"]
    assert fingerprint(orig) == before


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_cli_with_libreoffice(tmp_path, data_dir):
    deck = make_deck(tmp_path / "d.pptx", SLIDES, hide=(3,))
    orig = place_original(data_dir, "a_x2", deck)
    before = fingerprint(orig)
    out = data_dir / "derived" / "a_x2"
    env = {**__import__("os").environ, "DSO_PPTX_RENDERER": "libreoffice"}
    p = run_cli("a_x2", orig, out, env)
    assert p.returncode == 0, p.stderr
    m = check_manifest(out)
    assert fingerprint(orig) == before and m["kind"] == "document" and len(m["slides"]) == 4
    assert "slide images rendered with libreoffice" in m["pipeline"]["warnings"]
