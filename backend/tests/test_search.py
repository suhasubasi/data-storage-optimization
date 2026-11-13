from conftest import fixture_json


def test_search_returns_text_frame_and_timestamp(demo):
    r = demo.get("/api/search", params={"q": "handover"})
    assert r.status_code == 200
    body = r.json()
    want = {h["hit_type"] + h["asset_id"]: h for h in fixture_json("search.json")["hits"]}
    seg = next(h for h in body["hits"] if h["hit_type"] == "segment")
    w = want["segmenta_01"]
    for k in ("asset_id", "text", "start", "end", "item_id", "frame_id", "media", "page"):
        assert seg[k] == w[k], k
    assert "<mark>handover</mark>" in seg["snippet"]
    slide = next(h for h in body["hits"] if h["hit_type"] == "slide" and h["asset_id"] == "a_02")
    w = want["slidea_02"]
    for k in ("text", "page", "item_id", "media", "start", "frame_id"):
        assert slide[k] == w[k], k
    assert all(h["score"] > 0 for h in body["hits"])
    assert body["total"] == 4  # video segment + same slide in a_02, a_03 (exact copy) and a_04


def test_search_prefix_and_limit(demo):
    body = demo.get("/api/search", params={"q": "hand", "limit": 1}).json()
    assert body["total"] == 4 and len(body["hits"]) == 1


def test_search_is_safe_against_fts_syntax(demo):
    for q in ['"', "AND OR NOT (", "power*", "near(", "12%"]:
        r = demo.get("/api/search", params={"q": q})
        assert r.status_code == 200, q
    assert demo.get("/api/search", params={"q": "!!!"}).json()["total"] == 0


def test_search_validation(demo):
    assert demo.get("/api/search", params={"q": ""}).status_code == 422
    r = demo.get("/api/search", params={"q": "x", "limit": 0})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
