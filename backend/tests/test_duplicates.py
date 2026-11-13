from app import duplicates
from conftest import fixture_json


def _pairs(groups, typ):
    return sorted(tuple(f"{m['asset_id']}:{m['slide_id']}" if m["slide_id"] else m["asset_id"] for m in g["members"])
                  for g in groups if g["type"] == typ)


def test_duplicate_groups_match_fixture(demo):
    got = demo.get("/api/duplicates").json()
    want = fixture_json("duplicates.json")
    assert got["counts"] == want["counts"] == {"exact_file": 1, "shared_slide": 2, "similar_slide": 1}
    for typ in ("exact_file", "shared_slide", "similar_slide"):
        assert _pairs(got["groups"], typ) == _pairs(want["groups"], typ), typ
    sim = next(g for g in got["groups"] if g["type"] == "similar_slide")
    assert sim["needs_review"] is True and sim["evidence"]["method"] == "text_ratio" and sim["score"] < 1
    # deck (1).pdf (a_03) is an exact copy -> it must not create repeated slide groups
    assert not any(m["asset_id"] == "a_03" for g in got["groups"] if g["type"] != "exact_file" for m in g["members"])


def test_type_filter(demo):
    body = demo.get("/api/duplicates", params={"type": "similar_slide"}).json()
    assert {g["type"] for g in body["groups"]} == {"similar_slide"}
    assert demo.get("/api/duplicates", params={"type": "nope"}).status_code == 422


def test_slides_view_lists_matches_and_copy_inherits(demo):
    s = {x["id"]: x for x in demo.get("/api/assets/a_02/slides").json()["slides"]}
    assert [m["other_slide_id"] for m in s["p2"]["matches"]] == ["p1"]
    assert s["p4"]["matches"][0]["type"] == "similar"
    assert s["p1"]["matches"] == []
    copy = {x["id"]: x for x in demo.get("/api/assets/a_03/slides").json()["slides"]}
    assert [(m["other_asset_id"], m["other_slide_id"]) for m in copy["p2"]["matches"]] == [("a_04", "p1")]


T = {"shared_max": 4, "similar_max": 12, "min_ratio": 0.85, "min_chars": 20}


def _s(text, ph="0f0f0f0f0f0f0f0f"):
    import hashlib
    return {"text": text, "text_sha256": hashlib.sha256(duplicates.normalise(text).encode()).hexdigest(), "phash": ph}


def test_short_text_cannot_be_shared_by_text():
    a, b = _s("Thank you"), _s("Thank you")
    res = duplicates.compare_slides(a, b, T)
    assert res is None or res[0] != "shared"


def test_shared_needs_text_and_phash():
    text = "Energy saving: sleep modes for idle radio units"
    assert duplicates.compare_slides(_s(text), _s(text), T)[0] == "shared"
    # same text but a very different image -> not shared (only similar via text ratio)
    res = duplicates.compare_slides(_s(text), _s(text, "f0f0f0f0f0f0f0f0"), T)
    assert res[0] == "similar"


def test_blank_pages_are_not_matched_by_phash():
    z = "0000000000000000"
    assert duplicates.compare_slides(_s("", z), _s("", z), T) is None


def test_phash_only_similarity():
    long_a = "Handover optimisation: fewer dropped calls in dense cells"
    long_b = "Energy saving: sleep modes for idle radio units at night"
    close = "0f0f0f0f0f0f0f0e"  # distance 1 from the default
    # both pages have real text that differs -> text decides, no pHash-only noise
    assert duplicates.compare_slides(_s(long_a), _s(long_b, close), T) is None
    # image-heavy page (little text) + close image -> similar via phash, needs review
    res = duplicates.compare_slides(_s("Fig. 3"), _s("Fig. 4", close), T)
    assert res[0] == "similar" and res[1] == "phash"
