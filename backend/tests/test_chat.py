"""Meeting chat (REC v1.2). Chats here are tiny synthetic texts written inside the tests."""
from dso_contracts.models import ChatLog, SearchResponse

from app import chat, ingest

TXT = """Some intro text before the chat (ignored)

[10:05] Alice Example
Hello, can everyone hear me?

[10:07] Bob Example
Yes, the slides look clear
second line

[10:59] Bob Example
After the end
"""


def post(client, aid, name="chat.txt", data=TXT.encode(), **form):
    return client.post(f"/api/assets/{aid}/chat", files={"file": (name, data, "application/octet-stream")}, data=form)


def test_parse_lines_and_html():
    msgs = chat.parse_lines(TXT.splitlines())
    assert [(m["clock"], m["author"]) for m in msgs] == [("10:05", "Alice Example"), ("10:07", "Bob Example"),
                                                        ("10:59", "Bob Example")]
    assert msgs[1]["text"] == "Yes, the slides look clear\nsecond line"
    html = ("<html><head><style>p{}</style></head><body><p>Intro</p><p>[09:01] Ann</p><p>Hi&nbsp;there</p>"
            "<p>[09:02] Ben</p><p><img src='cid:x'></p><p><a name=\"_MailAutoSig\"></a>SIGNATURE Mobile +46 1</p>"
            "</body></html>")
    msgs = chat.parse_lines(chat.html_to_lines(html))
    assert msgs == [{"clock": "09:01", "author": "Ann", "text": "Hi there", "has_image": False},
                    {"clock": "09:02", "author": "Ben", "text": "", "has_image": True}]  # signature cut off


def test_time_estimate():
    assert chat.start_from_filename("Team sync-20240105_091503-Meeting Recording.mp4") == "2024-01-05T09:15:03"
    assert chat.start_from_filename("talk.mp4") is None
    s = "2024-01-05T09:15:03"
    assert chat.estimate_t("09:21", s, None) == 357.0  # 09:21:00 - 09:15:03
    assert chat.estimate_t("09:15", s, None) == 0.0
    assert chat.estimate_t("11:00", s, 3600.0) is None  # after the recording
    assert chat.estimate_t("00:10", "2024-01-05T23:50:00", None) == 1200.0  # past midnight


def test_attach_search_and_keep_on_reingest(demo):
    r = post(demo, "a_01", recording_start="2026-09-30T10:00:00")
    assert r.status_code == 201, r.text
    log = ChatLog.model_validate(r.json())
    assert [m.id for m in log.messages] == ["c1", "c2", "c3"]
    assert [m.t for m in log.messages] == [300.0, 420.0, None]  # 10:59 is after the 1800 s recording
    assert log.alignment.basis.value == "manual" and log.alignment.status.value == "estimated"
    assert log.alignment.uncertainty_seconds == 59.0 and "2 of 3 messages" in log.alignment.note
    assert log.source.filename == "chat.txt" and log.source.bytes == len(TXT.encode())

    res = SearchResponse.model_validate(demo.get("/api/search", params={"q": "slides clear"}).json())
    hit = next(h for h in res.hits if h.hit_type.value == "chat")
    assert hit.asset_id == "a_01" and hit.item_id == "c2" and hit.start == 420.0 and hit.frame_id == "f3"  # f3 covers 410-1220 s

    ingest.ingest_manifest("a_01", ingest.settings.REPO_ROOT / "contracts/fixtures/manifests/a_01.manifest.json")
    res = demo.get("/api/search", params={"q": "slides clear"}).json()
    assert any(h["hit_type"] == "chat" for h in res["hits"])  # re-processing keeps the chat

    r = post(demo, "a_01", data=b"[10:30] Carl\nreplaced\n", recording_start="2026-09-30T10:00:00")
    assert [m["text"] for m in r.json()["messages"]] == ["replaced"]
    assert demo.get("/api/search", params={"q": "slides clear"}).json()["total"] == 0


def test_attach_validation(demo):
    assert demo.get("/api/assets/a_01/chat").json() == {"asset_id": "a_01", "source": None, "alignment": None,
                                                         "messages": []}
    assert post(demo, "a_02").status_code == 422  # a document, not a recording
    assert post(demo, "a_01", name="chat.docx").status_code == 415
    assert post(demo, "a_01", data=b"no chat here").status_code == 422
    assert post(demo, "a_01", recording_start="yesterday").status_code == 422
    assert post(demo, "a_99").status_code == 404
    r = post(demo, "a_01")  # no start in 'event-recording.mp4' -> times unknown, said clearly
    log = r.json()
    assert log["alignment"]["status"] == "unknown" and all(m["t"] is None for m in log["messages"])
