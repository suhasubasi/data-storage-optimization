import hashlib
import shutil
import sys
from pathlib import Path

import pytest

PIPELINE_DIR = Path(__file__).resolve().parents[1]
REPO = PIPELINE_DIR.parent
TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    """Synthetic samples generated fresh into a temp dir (never touches data/)."""
    import synthetic_samples as ms
    d = tmp_path_factory.mktemp("samples")
    ms.make_deck(d / "deck.pdf", ms.SLIDES_A, "Rev A")
    shutil.copyfile(d / "deck.pdf", d / "deck (1).pdf")
    b = list(ms.SLIDES_A)
    b[0] = (b[0][0], b[0][1].replace("Rev A", "Rev B"))
    b[2] = ("Energy saving", "Sleep modes for idle radio units\nFifteen percent lower power per site")
    ms.make_deck(d / "deck-revB.pdf", b, "Rev B")
    if shutil.which("ffmpeg"):
        ms.make_video(d / "deck.pdf", d / "talk.mp4")
    return d


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    (d / "originals").mkdir(parents=True)
    (d / "derived").mkdir()
    return d


def place_original(data_dir: Path, asset_id: str, src: Path) -> Path:
    dest = data_dir / "originals" / asset_id / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    dest.chmod(0o444)  # like the backend: originals are read-only
    return dest


def fingerprint(p: Path):
    st = p.stat()
    return hashlib.sha256(p.read_bytes()).hexdigest(), st.st_size, st.st_mtime_ns
