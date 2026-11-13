"""Contract self-test. Run after ANY change in contracts/:
    .venv-tools/bin/python contracts/scripts/check_contracts.py
Checks: (1) every fixture validates against the JSON Schemas, (2) the generated Pydantic models
parse every fixture, (3) openapi.yaml is a valid OpenAPI 3.1 document, (4) schema.sql loads in
SQLite with FTS5, (5) storage fixture obeys the savings formula."""
import json
import sqlite3
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from dso_contracts import models as M  # noqa: E402

man = json.loads((ROOT / "schemas/manifest.schema.json").read_text())
api = json.loads((ROOT / "schemas/api.schema.json").read_text())
registry = Registry().with_resources([
    (man["$id"], Resource.from_contents(man)), ("manifest.schema.json", Resource.from_contents(man)),
    (api["$id"], Resource.from_contents(api)),
])


def validator(defname: str | None) -> Draft202012Validator:
    if defname is None:
        return Draft202012Validator(man, registry=registry)
    return Draft202012Validator({"$ref": f"{api['$id']}#/$defs/{defname}"}, registry=registry)


FIXTURES = {  # fixture file -> (schema def, pydantic model)
    "health.json": ("Health", M.Health),
    "assets.json": ("AssetList", M.AssetList),
    "asset_upload_response.json": ("Asset", M.Asset),
    "asset_detail_video.json": ("AssetDetail", M.AssetDetail),
    "asset_detail_document.json": ("AssetDetail", M.AssetDetail),
    "job.json": ("Job", M.Job),
    "job_running.json": ("Job", M.Job),
    "error.json": ("ErrorResponse", M.ErrorResponse),
    "settings.json": ("Settings", M.Settings),
    "timeline.json": ("Timeline", M.Timeline),
    "slides.json": ("SlideList", M.SlideList),
    "search.json": ("SearchResponse", M.SearchResponse),
    "duplicates.json": ("DuplicateReport", M.DuplicateReport),
    "storage_report.json": ("StorageReport", M.StorageReport),
    "offboarding.json": ("OffboardingReview", M.OffboardingReview),
    "export_asset.json": ("ExportAsset", M.ExportAsset),
}
errors = 0


def check(name: str, obj, v: Draft202012Validator, model) -> None:
    global errors
    errs = list(v.iter_errors(obj))
    for e in errs[:5]:
        print(f"  SCHEMA FAIL {name}: {list(e.path)} {e.message[:200]}")
    try:
        model.model_validate(obj)
    except Exception as e:  # pydantic ValidationError
        errs.append(e); print(f"  PYDANTIC FAIL {name}: {str(e)[:300]}")
    errors += bool(errs)


fx = ROOT / "fixtures"
for fname, (d, model) in FIXTURES.items():
    check(fname, json.loads((fx / fname).read_text()), validator(d), model)
for i, line in enumerate((fx / "export.jsonl").read_text().splitlines()):
    check(f"export.jsonl:{i+1}", json.loads(line), validator("ExportChunk"), M.ExportChunk)
for p in sorted((fx / "manifests").glob("*.json")):
    check(p.name, json.loads(p.read_text()), validator(None), M.Manifest)

# storage formula
r = json.loads((fx / "storage_report.json").read_text())
for s in r["scenarios"]:
    O, A = s["before_bytes"], s["after_bytes"]
    ok = (A == s["kept_original_bytes"] + s["derived_bytes"] + s["index_bytes"] and s["saved_bytes"] == O - A
          and abs(s["savings_pct"] - (O - A) / O * 100) < 1e-3 and s["kept_original_bytes"] == O - sum(x["bytes"] for x in s["removed"]))
    if not ok:
        errors += 1; print(f"  FORMULA FAIL scenario {s['id']}")
if r["scenarios"][0]["saved_bytes"] > 0:
    errors += 1; print("  FORMULA FAIL: scenario 0 must never show a positive saving")

# openapi
try:
    from openapi_spec_validator import validate
    spec = yaml.safe_load((ROOT / "openapi.yaml").read_text())
    validate(spec, base_uri=(ROOT / "openapi.yaml").as_uri())
except Exception as e:
    errors += 1; print(f"  OPENAPI FAIL: {str(e)[:400]}")

# sql
try:
    sqlite3.connect(":memory:").executescript((ROOT / "schema.sql").read_text())
except Exception as e:
    errors += 1; print(f"  SQL FAIL: {e}")

print("CONTRACTS OK" if not errors else f"CONTRACTS FAILED ({errors})")
sys.exit(1 if errors else 0)
