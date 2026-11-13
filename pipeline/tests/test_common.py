import hashlib

from PIL import Image

from dso_pipeline.common import normalise_text, phash_distance, phash_hex, text_sha256


def test_text_normalisation_rule():
    # NFKC (ﬁ ligature -> fi, full-width A -> A) -> lowercase -> collapse whitespace -> strip
    assert normalise_text("  Ｈandover\tOptimi\uFB01cation \n\n DENSE  ") == "handover optimification dense"
    assert text_sha256("A  b") == hashlib.sha256(b"a b").hexdigest()
    assert text_sha256("Hello\nWorld") == text_sha256("  hello   world ")


def test_phash_format():
    h = phash_hex(Image.new("RGB", (64, 64), (200, 10, 10)))
    assert len(h) == 16 and h == h.lower() and int(h, 16) >= 0
    assert phash_distance(h, h) == 0
