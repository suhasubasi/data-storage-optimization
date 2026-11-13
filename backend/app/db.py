"""SQLite access. The schema comes verbatim from contracts/schema.sql (frozen)."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from . import settings

# One writer at a time (job threads + requests). Reads use their own connections.
WRITE_LOCK = threading.RLock()


def utc_now() -> str:
    """ISO 8601 UTC with milliseconds and 'Z' (same shape as the schema's created_at default)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def connect() -> sqlite3.Connection:
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


@contextmanager
def read() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def write() -> Iterator[sqlite3.Connection]:
    """Serialised write transaction: commit on success, roll back on error."""
    with WRITE_LOCK:
        conn = connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db() -> None:
    """Create tables from contracts/schema.sql (idempotent: every statement is IF NOT EXISTS)."""
    sql = settings.SCHEMA_SQL.read_text(encoding="utf-8")
    with WRITE_LOCK:
        conn = connect()
        try:
            conn.executescript(sql)
            conn.commit()
        finally:
            conn.close()


def index_bytes() -> int:
    """I in the storage report: measured size of the SQLite database incl. FTS.

    The DB runs in WAL mode, so we checkpoint first and also count any remaining -wal file.
    """
    with WRITE_LOCK:
        conn = connect()
        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        finally:
            conn.close()
    total = 0
    for suffix in ("", "-wal"):
        p = settings.DB_PATH.with_name(settings.DB_PATH.name + suffix)
        if p.exists():
            total += p.stat().st_size
    return total
