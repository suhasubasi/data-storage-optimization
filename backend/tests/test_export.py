import json

from dso_contracts.models import ExportAsset, ExportChunk

from app import settings

from conftest import fill_optional, fixture_json


def test_export_asset_matches_fixture(demo):
    r = demo.get("/api/assets/a_02/export")
    assert r.status_code == 200
    got, want = r.json(), fill_optional(fixture_json("export_asset.json"))
    ExportAsset.model_validate(got)
    for d in (got, want):
        d.pop("exported_at")
        for s in d["slides"]:
            for m in s["matches"]:
                m.pop("score")
        for m in d["matches"]:
            m.pop("score")
    assert got == want


def test_export_has_provenance_and_source_links(demo):
    body = demo.get("/api/assets/a_01/export").json()
    assert body["source"]["original_url"] == "/files/originals/a_01/event-recording.mp4"
    assert body["source"]["sha256"] and body["source"]["source_simulated"] is True
    c = body["chunks"][1]
    assert c["chunk_id"] == "a_01:s2" and c["start"] == 96.2 and c["frame_id"] == "f2"
    assert c["image_url"] == "/files/derived/a_01/frames/f2.webp"


def test_export_jsonl(demo):
    r = demo.get("/api/export.jsonl")
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/x-ndjson")
    lines = [json.loads(x) for x in r.text.splitlines() if x.strip()]
    for line in lines:
        ExportChunk.model_validate(line)
    fixture_lines = [fill_optional(json.loads(x)) for x in open(settings.FIXTURES_DIR / "export.jsonl", encoding="utf-8")]
    by_id = {x["chunk_id"]: x for x in lines}
    for want in fixture_lines:  # fixture has a_01 + a_02; we export every ready asset
        assert by_id[want["chunk_id"]] == want
    assert {x["source"]["asset_id"] for x in lines} == {"a_01", "a_02", "a_03", "a_04"}  # a_05 not processed
