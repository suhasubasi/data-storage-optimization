# backend/ — Stream 2 (FastAPI + SQLite FTS5)

Skeleton only (`/health`). Implement **exactly** `../contracts/openapi.yaml` with the generated
Pydantic models (`from dso_contracts.models import ...`). DB schema: `../contracts/schema.sql`.

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -e ../contracts/python
uvicorn app.main:app --reload --port 8000   # http://localhost:8000/health , /docs
pytest -q
```

Responsibilities (design Page): save original untouched + SHA-256, job runner (background thread),
call the pipeline as a subprocess (see CONTRACTS.md §4), ingest `manifest.json` into SQLite, then
search / duplicates / storage report / offboarding / export. If Stream 3 slips, ingest
`../contracts/fixtures/manifests/*.json`. Never write a DELETE endpoint for originals.
