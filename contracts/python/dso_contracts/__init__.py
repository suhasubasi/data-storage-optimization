"""Shared, FROZEN contract types for the Ericsson DSO MVP.

`models` is GENERATED from contracts/schemas/*.json by contracts/scripts/generate.sh. Do not edit it.
Install into a stream's venv with:  pip install -e ../contracts/python
"""
from pathlib import Path

CONTRACT_VERSION = "1.0"
SAVINGS_FORMULA = "Savings % = (O − A) / O × 100"
# Repo-relative location of the tunable thresholds (not frozen; owned by Stream 3).
THRESHOLDS_PATH = Path(__file__).resolve().parents[2] / "thresholds.json"
