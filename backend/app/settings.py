"""Paths and settings. OUR RECOMMENDATION: everything is relative to the repo's data/ dir."""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("DSO_DATA_DIR", REPO_ROOT / "data")).resolve()
ORIGINALS_DIR = DATA_DIR / "originals"   # data/originals/<asset_id>/<filename>  (read-only, never deleted)
DERIVED_DIR = DATA_DIR / "derived"       # data/derived/<asset_id>/manifest.json + derived files (written by pipeline)
DB_PATH = Path(os.environ.get("DSO_DB_PATH", DATA_DIR / "dso.sqlite"))
SCHEMA_SQL = REPO_ROOT / "contracts" / "schema.sql"
THRESHOLDS = REPO_ROOT / "contracts" / "thresholds.json"
# The job runner calls the pipeline as a subprocess using the pipeline's own venv (keeps heavy deps separate).
PIPELINE_PYTHON = os.environ.get("DSO_PIPELINE_PYTHON", str(REPO_ROOT / "pipeline" / ".venv" / "bin" / "python"))
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
API_VERSION = "1.0.0"
