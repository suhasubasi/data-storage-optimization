"""TEST-ONLY: small SYNTHETIC inputs for the automated pipeline tests (no Ericsson data, nothing downloaded).

They are built fresh in a temporary folder for each test session (see conftest.py) and never put in data/.
They are not shown to users and are not used for any reported number.

  deck.pdf            4-page slide deck with PDF metadata (title/author/date) and a doc number + "Rev A" on page 1
  deck (1).pdf        byte-identical copy of deck.pdf          -> backend: exact_file duplicate (sha256)
  deck-revB.pdf       same deck, "Rev B", page 3 text revised  -> backend: shared slides p2/p4, similar/changed p3
  talk.mp4            ~25 s "recording": the deck pages shown as slides + synthetic speech (ffmpeg flite)
                      incl. the phrase "as you see here" -> frames and transcript linked by time
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pymupdf

SLIDES_A = [
    ("RAN Evolution Roadmap 2027", "Doc. no. 1/221 02-FGB 101  Rev A\nSynthetic sample for the DSO hackathon"),
    ("Handover optimisation", "Fewer dropped calls in dense cells\nTested in three cities"),
    ("Energy saving", "Sleep modes for idle radio units\nTwelve percent lower power per site"),
    ("Summary and next steps", "Field trials continue in 2027\nQuestions?"),
]
SPEECH = [
    "Welcome everyone to the radio access network evolution session.",
    "As you see here, handover optimisation reduces dropped calls in dense cells.",
    "Next, energy saving. Sleep modes for idle radio units lower the power per site.",
    "To summarise, field trials continue next year. Thank you.",
]
COLORS = [(0.05, 0.2, 0.45), (0.0, 0.45, 0.35), (0.55, 0.2, 0.05), (0.3, 0.1, 0.45)]


def make_deck(path: Path, slides, rev: str) -> None:
    doc = pymupdf.open()
    for (title, body), color in zip(slides, COLORS):
        page = doc.new_page(width=960, height=540)  # 16:9 slide
        page.draw_rect(page.rect, color=None, fill=color)
        page.draw_rect(pymupdf.Rect(0, 470, 960, 540), color=None, fill=(1, 1, 1))
        page.insert_text((60, 140), title, fontsize=44, color=(1, 1, 1))
        page.insert_text((60, 230), body, fontsize=26, color=(1, 1, 1))
        page.insert_text((60, 515), "Ericsson DSO synthetic sample", fontsize=16, color=(0, 0, 0))
    doc.set_metadata({
        "title": "RAN Evolution Roadmap",
        "author": "DSO Team (synthetic)",
        "creationDate": "D:20260930120000",
        "subject": "Synthetic hackathon test deck",
    })
    doc.save(path, garbage=4, deflate=True)
    doc.close()


def run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)


def make_video(deck: Path, out: Path) -> None:
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        parts = []
        with pymupdf.open(deck) as doc:
            for i, page in enumerate(doc):
                png = tmp / f"slide{i}.png"
                page.get_pixmap(matrix=pymupdf.Matrix(1280 / 960, 1280 / 960)).save(png)
                wav = tmp / f"say{i}.wav"
                txt = tmp / f"say{i}.txt"
                txt.write_text(SPEECH[i])
                run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"flite=textfile={txt}:voice=slt",
                     "-ar", "16000", "-ac", "1", str(wav)])
                part = tmp / f"part{i}.mp4"
                # slide image + its speech + 1 s of silence padding
                run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", "10", "-i", str(png), "-i", str(wav),
                     "-af", "apad=pad_dur=1", "-shortest", "-c:v", "libx264", "-preset", "veryfast",
                     "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "10", "-c:a", "aac", "-b:a", "48k",
                     "-ar", "16000", str(part)])
                parts.append(part)
        lst = tmp / "list.txt"
        lst.write_text("".join(f"file '{p}'\n" for p in parts))
        run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
             "-c", "copy", "-metadata", "title=RAN evolution session (synthetic)", "-movflags", "+faststart", str(out)])
