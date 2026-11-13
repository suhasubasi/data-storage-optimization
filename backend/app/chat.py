"""Meeting chat attached to a recording (REC v1.2).

Input: the chat as an Outlook .msg (e.g. a Teams meeting chat pasted into a mail) or a plain .txt with the
same "[HH:MM] Name" header lines. Each message keeps the clock time exactly as written. Its place in the
recording is ESTIMATED: clock time minus the recording start (read from the recording file name, e.g.
'<name>-YYYYMMDD_HHMMSS-Meeting Recording.mp4', or given by the user). Chat times only have minutes, so every
estimate can be up to 59 s early. We say so in the response and never present it as exact.

The uploaded chat file is hashed (SHA-256) and parsed; only the parsed messages are stored (in the DB, so
they count in I). The file itself is not kept: the user's original stays where it is. Nothing is deleted.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from pathlib import Path

from dso_contracts.models import ChatAlignment, ChatLog, ChatMessage, ChatSource, ErrorCode

from . import db
from .errors import ApiError
from .services import get_asset_row

MAX_BYTES = 20 * 1024 * 1024
UNCERTAINTY_S = 59.0
IMG = "\u0000IMG\u0000"
_HEADER = re.compile(r"^\[(\d{1,2}):(\d{2})\]\s+(.+?)\s*$")
_START_IN_NAME = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})(?!\d)")
_BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "table"}


class _HtmlText(HTMLParser):
    """HTML -> text lines; <img> becomes a marker; <style>/<script>/<head> skipped."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "head", "title"):
            self.skip += 1
        elif tag == "img":
            self.out.append(IMG)
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "head", "title"):
            self.skip = max(0, self.skip - 1)
        elif tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data.replace("\r", " ").replace("\n", " "))


def html_to_lines(html: str) -> list[str]:
    # Outlook marks the start of the sender's e-mail signature; it is not part of the chat.
    cut = re.search(r"<a\s+name=\"?_MailAutoSig", html, re.IGNORECASE)
    if cut:
        html = html[: cut.start()]
    p = _HtmlText()
    p.feed(html)
    return "".join(p.out).split("\n")


def parse_lines(lines: list[str]) -> list[dict]:
    """[{clock, author, text, has_image}] from '[HH:MM] Name' blocks. Text before the first header is ignored."""
    msgs: list[dict] = []
    cur: dict | None = None
    for raw in lines:
        line = unescape(raw).replace("\xa0", " ").strip()
        m = _HEADER.match(line)
        if m and 0 <= int(m.group(1)) < 24 and 0 <= int(m.group(2)) < 60:
            cur = {"clock": f"{int(m.group(1)):02d}:{m.group(2)}", "author": m.group(3), "lines": [], "has_image": False}
            msgs.append(cur)
            continue
        if cur is None:
            continue
        if IMG in line:
            cur["has_image"] = True
            line = line.replace(IMG, " ").strip()
        if line:
            cur["lines"].append(" ".join(line.split()))
    return [{"clock": c["clock"], "author": c["author"], "text": "\n".join(c["lines"]), "has_image": c["has_image"]}
            for c in msgs]


def read_chat_file(name: str, data: bytes) -> list[dict]:
    suffix = Path(name).suffix.lower()
    if suffix == ".txt":
        return parse_lines(data.decode("utf-8-sig", errors="replace").splitlines())
    if suffix != ".msg":
        raise ApiError(ErrorCode.unsupported_file_type, "A meeting chat must be an Outlook .msg or a .txt file.",
                       {"filename": name})
    import extract_msg  # only needed for .msg

    with tempfile.TemporaryDirectory(prefix="dso-chat-") as t:
        p = Path(t) / "chat.msg"
        p.write_bytes(data)
        try:
            msg = extract_msg.openMsg(str(p))
        except Exception as e:  # noqa: BLE001
            raise ApiError(ErrorCode.validation_error, f"Could not read the .msg file: {e}", {"filename": name}) from e
        try:
            html = msg.htmlBody
            if isinstance(html, bytes):
                html = html.decode("utf-8", errors="replace")
            lines = html_to_lines(html) if html else (msg.body or "").splitlines()
        finally:
            msg.close()
    return parse_lines(lines)


def start_from_filename(filename: str) -> str | None:
    m = _START_IN_NAME.search(filename)
    if not m:
        return None
    try:
        return datetime(*map(int, m.groups())).strftime("%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None


def estimate_t(clock: str, start: str | None, duration: float | None) -> float | None:
    if start is None:
        return None
    s = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S")
    hh, mm = map(int, clock.split(":"))
    delta = (hh * 3600 + mm * 60) - (s.hour * 3600 + s.minute * 60 + s.second)
    if delta < -UNCERTAINTY_S:
        delta += 86400  # the meeting went past midnight
    if delta < 0:
        delta = 0.0  # same minute as the start
    if duration is not None and delta > duration + UNCERTAINTY_S:
        return None  # after the recording ended
    return float(delta)


def _duration(row) -> float | None:
    try:
        d = json.loads(row["metadata_json"] or "{}").get("duration_seconds")
        return float(d) if d is not None else None
    except (ValueError, TypeError, AttributeError):
        return None


def _note(basis: str, start: str | None, duration: float | None, msgs: list[dict]) -> str:
    if start is None:
        return "No recording start time found, so chat messages are not placed on the recording timeline."
    where = "from the recording file name" if basis == "filename" else "entered by the user"
    parts = [f"Recording start {start.replace('T', ' ')} ({where}; assumed to be the same local clock as the chat).",
             "Chat times are written to the minute, so each place on the timeline can be up to 59 s early.",
             "Not checked against the speech."]
    if duration is None:
        parts.append("The recording length is not known yet, so times were not range-checked.")
    else:
        outside = sum(1 for m in msgs if m["t"] is None)
        parts.append(f"{len(msgs) - outside} of {len(msgs)} messages fall inside the recording"
                     + (f"; {outside} fall outside and have no time." if outside else "."))
    return " ".join(parts)


def attach(asset_id: str, filename: str | None, data: bytes, recording_start: str | None = None) -> ChatLog:
    name = Path((filename or "").replace("\\", "/")).name
    if not name:
        raise ApiError(ErrorCode.validation_error, "The chat file needs a file name.", {"filename": filename})
    if len(data) > MAX_BYTES:
        raise ApiError(ErrorCode.validation_error, "The chat file is too large (max 20 MB).", {"bytes": len(data)})
    with db.read() as conn:
        row = get_asset_row(conn, asset_id)
    if row["kind"] != "video":
        raise ApiError(ErrorCode.validation_error, "A meeting chat can only be attached to a recording (video).",
                       {"asset_id": asset_id})
    if recording_start:
        try:
            start = datetime.fromisoformat(recording_start.strip()).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError as e:
            raise ApiError(ErrorCode.validation_error, "recording_start must look like 2024-01-05T09:15:03.",
                           {"recording_start": recording_start}) from e
        basis = "manual"
    else:
        start = start_from_filename(row["filename"])
        basis = "filename" if start else "unknown"
    msgs = read_chat_file(name, data)
    if not msgs:
        raise ApiError(ErrorCode.validation_error, "No chat messages found (expected lines like '[16:44] Name').",
                       {"filename": name})
    duration = _duration(row)
    for m in msgs:
        m["t"] = estimate_t(m["clock"], start, duration)
    with db.write() as conn:
        conn.execute("DELETE FROM chat_messages WHERE asset_id = ?", (asset_id,))
        conn.execute("DELETE FROM search_fts WHERE asset_id = ? AND item_type = 'chat'", (asset_id,))
        conn.execute(
            "INSERT INTO chat_sources (asset_id, filename, bytes, sha256, recording_start, basis, attached_at) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT(asset_id) DO UPDATE SET filename = excluded.filename, "
            "bytes = excluded.bytes, sha256 = excluded.sha256, recording_start = excluded.recording_start, "
            "basis = excluded.basis, attached_at = excluded.attached_at",
            (asset_id, name, len(data), hashlib.sha256(data).hexdigest(), start, basis, db.utc_now()))
        for i, m in enumerate(msgs, start=1):
            cid = f"c{i}"
            conn.execute("INSERT INTO chat_messages (asset_id, id, clock, t, author, text, has_image) "
                         "VALUES (?,?,?,?,?,?,?)",
                         (asset_id, cid, m["clock"], m["t"], m["author"], m["text"], int(m["has_image"])))
            if m["text"].strip():
                conn.execute("INSERT INTO search_fts (text, asset_id, item_type, item_id) VALUES (?,?,?,?)",
                             (f"{m['author']}: {m['text']}", asset_id, "chat", cid))
    return get_chat(asset_id)


def get_chat(asset_id: str) -> ChatLog:
    with db.read() as conn:
        row = get_asset_row(conn, asset_id)
        src = conn.execute("SELECT * FROM chat_sources WHERE asset_id = ?", (asset_id,)).fetchone()
        rows = conn.execute("SELECT * FROM chat_messages WHERE asset_id = ? ORDER BY CAST(substr(id, 2) AS INTEGER)",
                            (asset_id,)).fetchall()
    if src is None:
        return ChatLog(asset_id=asset_id, source=None, alignment=None, messages=[])
    msgs = [dict(clock=r["clock"], t=r["t"], author=r["author"], text=r["text"], has_image=bool(r["has_image"]),
                 id=r["id"]) for r in rows]
    start = src["recording_start"]
    alignment = ChatAlignment(
        recording_start=start, basis=src["basis"], uncertainty_seconds=UNCERTAINTY_S if start else None,
        status="estimated" if start else "unknown", note=_note(src["basis"], start, _duration(row), msgs))
    return ChatLog(
        asset_id=asset_id,
        source=ChatSource(filename=src["filename"], bytes=src["bytes"], sha256=src["sha256"],
                          attached_at=src["attached_at"]),
        alignment=alignment,
        messages=[ChatMessage(**m) for m in msgs])
