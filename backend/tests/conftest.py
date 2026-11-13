"""Test setup: every test session uses a throwaway data dir (never the real data/ folder)."""
import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="dso-backend-tests-")
os.environ["DSO_DATA_DIR"] = _TMP
os.environ.pop("DSO_DB_PATH", None)

import json  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import ingest, settings  # noqa: E402
from app.main import app  # noqa: E402

FIX = settings.FIXTURES_DIR
assert str(settings.DATA_DIR).startswith(_TMP), "tests must not touch the real data/ dir"


def fixture_json(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def fill_optional(obj):
    """Fixtures omit optional AssetMetadata.duration_seconds; the API sends it as null (schema-valid)."""
    if isinstance(obj, dict):
        if "doc_number" in obj and "revision" in obj:
            obj.setdefault("duration_seconds", None)
        for v in obj.values():
            fill_optional(v)
    elif isinstance(obj, list):
        for v in obj:
            fill_optional(v)
    return obj


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def demo(client):
    """Fresh DB with the contracts/fixtures demo dataset."""
    ingest.load_fixtures(reset=True)
    return client


@pytest.fixture
def empty(client):
    ingest.reset_database()
    from app import db
    db.init_db()
    return client


def write_file(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path
