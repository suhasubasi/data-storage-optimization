# backend/ — Stream 2 (FastAPI + SQLite FTS5)

Implements **all 16 operations** of `../contracts/openapi.yaml` with the generated models
(`dso_contracts.models`). DB = `../contracts/schema.sql` at `data/dso.sqlite` (git-ignored).
No DELETE/PUT/PATCH endpoints. No code path deletes or modifies originals. No cloud AI.

```bash
cd backend
python3 -m venv .venv && . .venv/bin/activate      # (or: uv venv && uv pip install ...)
pip install -r requirements.txt -e ../contracts/python
python -m app.cli init-db                         # empty database (also created on first start)
uvicorn app.main:app --port 8000                  # http://localhost:8000/health , /docs
pytest -q                                         # tests use a throwaway DB + synthetic contract examples
```

Real files (pipeline in `../pipeline/.venv`, called as a subprocess — faster-whisper never enters this venv):

```bash
# via API:  POST /api/assets (multipart: file, source_system, owner) -> POST /api/assets/{id}/process -> GET /api/jobs/{job_id}
python -m app.cli add-file "/path/to/real deck.pptx" --source sharepoint --owner <owner> --process
python -m app.cli add-file "/path/to/real talk.mp4" --source ericsson_play --owner <owner> --process
python -m app.cli ingest a_1234abcd                # re-ingest data/derived/<id>/manifest.json
python -m app.cli recompute-duplicates
```

Env: `DSO_DATA_DIR`, `DSO_DB_PATH`, `DSO_PIPELINE_PYTHON` (default `pipeline/.venv/bin/python`),
`DSO_PIPELINE_CWD`, `DSO_PIPELINE_TIMEOUT_S`, `DSO_CORS_ORIGINS`.

| Module | Does |
|---|---|
| `app/main.py` | routes (exactly the contract) + file serving (Range for video) |
| `app/uploads.py` | save original untouched, SHA-256 while streaming, chmod read-only |
| `app/jobs.py` | background thread → `python -m dso_pipeline process …`; real progress from `progress.json`, errors from `error.json`/stderr |
| `app/progress.py` | `elapsed_s` and `eta_s` for `GET /api/jobs/{id}`. `eta_s` is an ESTIMATE from the measured rate so far (elapsed / progress), hidden until ≥ 3 % and ≥ 10 s |
| `app/ingest.py` | validate `manifest.json` (Manifest model), **measure its size** (counted in D), write tables + FTS |
| `app/duplicates.py` | cross-file matching over SQLite → `matches` |
| `app/services.py` | search, timeline, slides, duplicates, storage report, offboarding, export |
| `app/errors.py` | contract `ErrorResponse` for every non-2xx (incl. 422/404/405) |

Backend-only recommendations (REC, not in the contracts):
- Slide matching uses one representative per SHA-256 group (earliest upload with slides); an exact copy's
  slide list *shows* the representative's matches (same bytes ⇒ same pages), but no extra groups are created.
- Shared slides that appear in 3+ decks form one group (connected components); similar slides stay pairwise.
- pHash-only "similar" is skipped for near-blank images and when **both** pages have enough text
  (`PHASH_ONLY_NEEDS_SHORT_TEXT` in `duplicates.py`): on real samples unrelated text slides in the same
  template had pHash distance 8–10 (threshold 12).
- If re-processing fails, a previously ingested asset stays `ready` (old data is still valid); the job shows the error.
- Jobs left running when the server stops are marked failed at next start (never faked).
- Search: each word must match (prefix); FTS syntax in user input is neutralised. Exact copies all appear as hits.
- `I` = SQLite file size after a WAL checkpoint (+ any remaining `-wal`).
