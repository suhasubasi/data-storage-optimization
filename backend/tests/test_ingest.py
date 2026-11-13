import json

import pytest

from fixture_data import FIXTURES_DIR
from app import db, ingest, settings
from conftest import fill_optional, fixture_json

from dso_contracts.models import Manifest


def test_fixture_assets_match_contract_fixture(demo):
    r = demo.get("/api/assets")
    assert r.status_code == 200
    assert r.json() == fixture_json("assets.json")


def test_asset_detail_matches_fixtures(demo):
    for aid, name in (("a_01", "asset_detail_video.json"), ("a_02", "asset_detail_document.json")):
        got = demo.get(f"/api/assets/{aid}").json()
        want = fill_optional(fixture_json(name))
        got.pop("latest_job"), want.pop("latest_job")  # fixture job is illustrative; we never fake jobs
        assert got == want


def test_manifest_bytes_measured_and_counted_as_derived(demo):
    with db.read() as conn:
        row = conn.execute("SELECT manifest_bytes FROM assets WHERE id = 'a_01'").fetchone()
    size = (FIXTURES_DIR / "manifests" / "a_01.manifest.json").stat().st_size
    assert row["manifest_bytes"] == size
    m = Manifest.model_validate_json((FIXTURES_DIR / "manifests" / "a_01.manifest.json").read_bytes())
    assert demo.get("/api/assets/a_01").json()["asset"]["derived_bytes"] == sum(f.bytes for f in m.derived_files) + size


def test_timeline_matches_fixture(demo):
    assert demo.get("/api/assets/a_01/timeline").json() == fixture_json("timeline.json")


def test_timeline_for_document_is_empty(demo):
    t = demo.get("/api/assets/a_02/timeline").json()
    assert t["segments"] == [] and t["frames"] == []


def test_unprocessed_asset_detail(demo):
    d = demo.get("/api/assets/a_05").json()
    assert d["asset"]["status"] == "uploaded" and d["derived"] is None and d["metadata"] is None
    assert d["asset"]["derived_bytes"] == 0


def test_ingest_rejects_wrong_sha_and_wrong_id(demo, tmp_path):
    m = json.loads((FIXTURES_DIR / "manifests" / "a_02.manifest.json").read_text())
    bad = dict(m, original=dict(m["original"], sha256="0" * 64))
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ingest.IngestError, match="sha256"):
        ingest.ingest_manifest("a_02", p)
    p.write_text(json.dumps(m))
    with pytest.raises(ingest.IngestError, match="expected a_04"):
        ingest.ingest_manifest("a_04", p)
    p.write_text('{"asset_id": "a_02"}')
    with pytest.raises(ingest.IngestError, match="contract"):
        ingest.ingest_manifest("a_02", p)


def test_reingest_is_idempotent(demo):
    before = demo.get("/api/assets/a_02/slides").json()
    ingest.ingest_manifest("a_02", FIXTURES_DIR / "manifests" / "a_02.manifest.json")
    assert demo.get("/api/assets/a_02/slides").json() == before
    hits = demo.get("/api/search", params={"q": "roadmap"}).json()["hits"]
    # page 1 of a_02 + a_03 (exact copies), plus each file's title row (v1.1) -- nothing doubled
    assert sorted((h["hit_type"], h["asset_id"]) for h in hits) == [
        ("asset", "a_02"), ("asset", "a_03"), ("slide", "a_02"), ("slide", "a_03")]


def test_errors_use_contract_shape(demo):
    r = demo.get("/api/assets/a_99")
    assert r.status_code == 404
    assert r.json() == {"error": {"code": "not_found", "message": "Asset a_99 was not found.", "details": None}}
    r = demo.get("/api/offboarding")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    r = demo.get("/api/jobs/j_nope")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
