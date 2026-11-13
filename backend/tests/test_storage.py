import json

from app import db, services, settings
from conftest import fixture_json


def test_reference_calculation_matches_contract_fixture():
    """Same inputs as contracts/scripts/make_fixtures.py -> identical report (except generated_at)."""
    want = fixture_json("storage_report.json")
    assets = [dict(a) for a in fixture_json("assets.json")["assets"]]
    got = services.compute_storage(assets, want["totals"]["derived_bytes"], want["totals"]["index_bytes"],
                                   want["generated_at"]).model_dump(mode="json")
    assert got == want


def test_scenario_math(demo):
    r = demo.get("/api/storage/report").json()
    t = r["totals"]
    O, D, I = t["original_bytes"], t["derived_bytes"], t["index_bytes"]
    assert I == settings.DB_PATH.stat().st_size > 0  # measured
    assert D == 913_523  # all derived_files + every manifest.json
    s = {x["key"]: x for x in r["scenarios"]}
    assert [x["id"] for x in r["scenarios"]] == [0, 1, 2, 3]
    # scenario 0: real, nothing deleted -> negative
    assert s["today"]["after_bytes"] == O + D + I and s["today"]["saved_bytes"] == -(D + I) < 0
    assert s["today"]["removed"] == [] and s["today"]["hypothetical"] is False
    # 1: processed video originals
    assert [x["asset_id"] for x in s["replace_videos"]["removed"]] == ["a_01"]
    assert s["replace_videos"]["after_bytes"] == O - 734_003_200 + D + I
    # 2: extra exact copies (keep earliest upload)
    rem = s["remove_exact_duplicates"]["removed"]
    assert rem == [{"asset_id": "a_03", "filename": "ran-deck (1).pdf", "bytes": 2_400_000,
                    "reason": "exact_duplicate", "kept_copy_asset_id": "a_02"}]
    # 3: union, no double counting
    assert sorted(x["asset_id"] for x in s["both"]["removed"]) == ["a_01", "a_03"]
    assert s["both"]["after_bytes"] == O - 734_003_200 - 2_400_000 + D + I
    for x in r["scenarios"]:
        assert x["after_bytes"] == x["kept_original_bytes"] + x["derived_bytes"] + x["index_bytes"]
        assert abs(x["savings_pct"] - round((O - x["after_bytes"]) / O * 100, 4)) < 1e-9


def test_unprocessed_video_is_not_counted_in_scenario_1():
    assets = [dict(id="a_1", filename="v.mp4", kind="video", bytes=1000, sha256="1" * 64, status="uploaded",
                   created_at="2026-11-13T08:00:00Z")]
    r = services.compute_storage(assets, 0, 10, "2026-11-13T08:00:00Z")
    assert r.scenarios[1].removed == [] and r.scenarios[1].saved_bytes == -10


def test_empty_library_has_null_percent(empty):
    r = empty.get("/api/storage/report").json()
    assert r["totals"]["original_bytes"] == 0
    assert all(s["savings_pct"] is None for s in r["scenarios"])
