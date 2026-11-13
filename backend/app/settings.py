"""Paths and settings. OUR RECOMMENDATION: everything is relative to the repo's data/ dir.

Every value can be overridden with an environment variable (tests use a temporary DSO_DATA_DIR).
"""
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"
DATA_DIR = Path(os.environ.get("DSO_DATA_DIR", REPO_ROOT / "data")).resolve()
ORIGINALS_DIR = DATA_DIR / "originals"   # data/originals/<asset_id>/<filename>  (read-only, never deleted)
DERIVED_DIR = DATA_DIR / "derived"       # data/derived/<asset_id>/manifest.json + derived files (written by pipeline)
DB_PATH = Path(os.environ.get("DSO_DB_PATH", DATA_DIR / "dso.sqlite"))
SCHEMA_SQL = CONTRACTS_DIR / "schema.sql"
THRESHOLDS = CONTRACTS_DIR / "thresholds.json"
FIXTURES_DIR = CONTRACTS_DIR / "fixtures"
# The job runner calls the pipeline as a subprocess using the pipeline's own venv (keeps heavy deps separate).
def _default_pipeline_python() -> str:
    win = REPO_ROOT / "pipeline" / ".venv" / "Scripts" / "python.exe"
    unix = REPO_ROOT / "pipeline" / ".venv" / "bin" / "python"
    return str(win if win.exists() else unix)


PIPELINE_PYTHON = os.environ.get("DSO_PIPELINE_PYTHON", _default_pipeline_python())
# REC: working directory for `python -m dso_pipeline` (so the module is importable even if not pip-installed).
PIPELINE_CWD = Path(os.environ.get("DSO_PIPELINE_CWD", REPO_ROOT / "pipeline"))
# REC: hard stop for one pipeline run (seconds). Long videos on CPU can be slow.
PIPELINE_TIMEOUT_S = float(os.environ.get("DSO_PIPELINE_TIMEOUT_S", 4 * 3600))
CORS_ORIGINS = os.environ.get("DSO_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
API_VERSION = "1.0.0"
