import json
import subprocess
import sys

import pytest

from conftest import fingerprint, place_original
from helpers import check_manifest
from dso_pipeline.common import text_sha256


def run_cli(asset_id, kind, inp, out, env=None):
    return subprocess.run([sys.executable, "-m", "dso_pipeline", "process", "--asset-id", asset_id, "--kind", kind,
                           "--input", str(inp), "--out", str(out)], capture_output=True, text=True, env=env)


def test_pdf_manifest_valid_and_original_untouched(samples, data_dir):
    orig = place_original(data_dir, "a_t1", samples / "deck.pdf")
    before = fingerprint(orig)
    out = data_dir / "derived" / "a_t1"
    p = run_cli("a_t1", "document", orig, out)
    assert p.returncode == 0, p.stderr
    m = check_manifest(out)
    assert fingerprint(orig) == before  # never deleted / modified
    assert m["asset_id"] == "a_t1" and m["kind"] == "document"
    assert m["original"]["path"] == "originals/a_t1/deck.pdf"
    assert m["original"]["sha256"] == before[0] and m["original"]["bytes"] == before[1]
    assert [s["id"] for s in m["slides"]] == ["p1", "p2", "p3", "p4"]
    assert m["segments"] == [] and m["frames"] == []
    for s in m["slides"]:
        assert s["text_sha256"] == text_sha256(s["text"])
        assert (out / s["path"]).stat().st_size == s["bytes"]
    assert "Handover optimisation" in m["slides"][1]["text"]
    md = m["metadata"]
    assert md["title"] == "RAN Evolution Roadmap" and md["date"] == "2026-09-30"
    assert md["doc_number"] == "1/221 02-FGB 101" and md["revision"] == "A"
    assert m["pipeline"]["model"] is None and m["pipeline"]["frame_threshold"] is None
    assert json.loads((out / "progress.json").read_text()) == {"stage": "done", "progress": 1.0}
    assert not (out / "error.json").exists()


def test_copy_and_revision_hashes(samples, data_dir):
    """Pipeline only emits hashes; this checks they carry the signal the backend needs."""
    ms = {}
    for aid, name in (("a_x1", "deck.pdf"), ("a_x2", "deck (1).pdf"), ("a_x3", "deck-revB.pdf")):
        orig = place_original(data_dir, aid, samples / name)
        assert run_cli(aid, "document", orig, data_dir / "derived" / aid).returncode == 0
        ms[aid] = check_manifest(data_dir / "derived" / aid)
    a, copy, b = ms["a_x1"], ms["a_x2"], ms["a_x3"]
    assert a["original"]["sha256"] == copy["original"]["sha256"]  # exact copy, name differs
    assert a["original"]["sha256"] != b["original"]["sha256"]
    # unchanged pages: same text hash; revised page 3: different text hash
    assert a["slides"][1]["text_sha256"] == b["slides"][1]["text_sha256"]
    assert a["slides"][3]["text_sha256"] == b["slides"][3]["text_sha256"]
    assert a["slides"][2]["text_sha256"] != b["slides"][2]["text_sha256"]
    assert b["metadata"]["revision"] == "B"


def test_non_pdf_fails_cleanly(tmp_path, data_dir):
    fake = tmp_path / "notes.pdf"
    fake.write_text("not a pdf")
    orig = place_original(data_dir, "a_bad", fake)
    before = fingerprint(orig)
    out = data_dir / "derived" / "a_bad"
    p = run_cli("a_bad", "document", orig, out)
    assert p.returncode == 1 and "failed" in p.stderr
    assert not (out / "manifest.json").exists()
    err = json.loads((out / "error.json").read_text())
    assert err["error"]["code"] == "pipeline_failed" and err["error"]["message"]
    assert fingerprint(orig) == before


def test_missing_input_writes_error(data_dir):
    out = data_dir / "derived" / "a_none"
    p = run_cli("a_none", "document", data_dir / "originals" / "a_none" / "x.pdf", out)
    assert p.returncode == 1
    assert (out / "error.json").exists() and not (out / "manifest.json").exists()


def test_refuses_out_inside_originals(samples, data_dir):
    orig = place_original(data_dir, "a_t2", samples / "deck.pdf")
    before = fingerprint(orig)
    p = run_cli("a_t2", "document", orig, orig.parent)
    assert p.returncode == 1
    assert sorted(x.name for x in orig.parent.iterdir()) == ["deck.pdf"]
    assert fingerprint(orig) == before


def test_failure_mid_run_leaves_no_manifest(samples, data_dir, monkeypatch):
    """Stale manifest from an earlier run is removed first; a crash after some outputs => no manifest."""
    from dso_pipeline import document, process

    orig = place_original(data_dir, "a_t3", samples / "deck.pdf")
    before = fingerprint(orig)
    out = data_dir / "derived" / "a_t3"
    out.mkdir(parents=True)
    (out / "manifest.json").write_text("{}")  # stale

    real = document.process_document

    def boom(*a, **k):
        real(*a, **k)  # page images get written...
        raise RuntimeError("simulated crash before manifest")

    monkeypatch.setattr(document, "process_document", boom)
    with pytest.raises(RuntimeError):
        process.run("a_t3", "document", orig, out)
    assert not (out / "manifest.json").exists()
    assert "simulated crash" in json.loads((out / "error.json").read_text())["error"]["message"]
    assert fingerprint(orig) == before


def test_rerun_replaces_old_outputs(samples, data_dir):
    orig = place_original(data_dir, "a_t4", samples / "deck.pdf")
    out = data_dir / "derived" / "a_t4"
    (out / "pages").mkdir(parents=True)
    (out / "pages" / "p99.webp").write_bytes(b"old")
    (out / "error.json").write_text("{}")
    assert run_cli("a_t4", "document", orig, out).returncode == 0
    check_manifest(out)  # p99 gone, error.json gone
    assert not (out / "error.json").exists()
