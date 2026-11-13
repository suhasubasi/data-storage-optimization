import json
from pathlib import Path

from jsonschema import Draft202012Validator

from dso_contracts.models import Manifest

SCHEMA = json.loads((Path(__file__).resolve().parents[2] / "contracts" / "schemas" / "manifest.schema.json").read_text())
STATUS_FILES = {"manifest.json", "progress.json", "error.json"}


def check_manifest(out: Path) -> dict:
    m = json.loads((out / "manifest.json").read_text())
    Draft202012Validator(SCHEMA).validate(m)  # JSON Schema (source of truth)
    Manifest.model_validate(m)  # generated Pydantic model the backend uses
    # derived_files lists EVERY kept file with its real size, and nothing else is on disk
    listed = {d["path"]: d["bytes"] for d in m["derived_files"]}
    on_disk = {
        p.relative_to(out).as_posix(): p.stat().st_size
        for p in out.rglob("*") if p.is_file() and p.name not in STATUS_FILES
    }
    assert listed == on_disk
    assert not any(p.name.startswith(".tmp") or p.name.endswith(".tmp") for p in out.rglob("*"))
    # manifest.json is written LAST
    mt = (out / "manifest.json").stat().st_mtime_ns
    for p in out.rglob("*"):
        if p.is_file():
            assert p.stat().st_mtime_ns <= mt, f"{p} written after manifest.json"
    return m
