import hashlib

from app.main import app
from conftest import fixture_json


def test_offboarding_matches_fixture(demo):
    r = demo.get("/api/offboarding", params={"owner": "carl"})
    assert r.status_code == 200
    got, want = r.json(), fixture_json("offboarding.json")
    got.pop("generated_at"), want.pop("generated_at")
    assert got == want
    assert got["deletes_performed"] is False


def test_near_duplicates_never_qualify(demo):
    rows = {x["asset_id"]: x for x in demo.get("/api/offboarding", params={"owner": "carl"}).json()["rows"]}
    # a_04 shares two slides and has one similar slide with a_02, but is NOT an exact copy -> keep
    assert rows["a_04"]["recommendation"] == "keep"
    assert rows["a_03"]["recommendation"] == "eligible_after_approval"


def test_leavers_own_two_copies_are_both_kept(empty):
    data = b"%PDF-1.4 leaver deck"
    for name in ("deck.pdf", "deck (1).pdf"):
        r = empty.post("/api/assets", files={"file": (name, data, "application/pdf")},
                       data={"source_system": "onedrive", "owner": "dana"})
        assert r.status_code == 201
    body = empty.get("/api/offboarding", params={"owner": "dana"}).json()
    assert [x["recommendation"] for x in body["rows"]] == ["keep", "keep"]
    assert body["summary"] == {"total": 2, "eligible": 0, "keep": 2, "eligible_bytes": 0}


def test_offboarding_never_deletes_originals(empty):
    from app import settings
    data = b"%PDF-1.4 shared deck"
    ids = []
    for owner, src in (("erik", "sharepoint"), ("leaver", "onedrive")):
        ids.append(empty.post("/api/assets", files={"file": ("d.pdf", data, "application/pdf")},
                              data={"source_system": src, "owner": owner}).json()["id"])
    body = empty.get("/api/offboarding", params={"owner": "leaver"}).json()
    assert body["rows"][0]["recommendation"] == "eligible_after_approval"
    assert body["deletes_performed"] is False
    for aid in ids:
        p = settings.ORIGINALS_DIR / aid / "d.pdf"
        assert p.exists() and hashlib.sha256(p.read_bytes()).hexdigest() == hashlib.sha256(data).hexdigest()


def test_there_is_no_delete_endpoint(demo):
    methods = {m for route in app.routes for m in (getattr(route, "methods", None) or set())}
    assert "DELETE" not in methods and "PUT" not in methods and "PATCH" not in methods
    r = demo.delete("/api/assets/a_02")
    assert r.status_code == 405 and "error" in r.json()
