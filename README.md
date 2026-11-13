# Ericsson Data Storage Optimization — MVP (Campor × BUILD Hackathon 2026)

[![CI](https://github.com/suhasubasi/ericsson-data-storage-optimization/actions/workflows/ci.yml/badge.svg)](https://github.com/suhasubasi/ericsson-data-storage-optimization/actions/workflows/ci.yml)

Local tool that turns long recordings and documents into compact, searchable, AI-ready data and finds
duplicates across (simulated) SharePoint / OneDrive / Ericsson Play — **without deleting anything**.

- MP4 → timed local transcript (faster-whisper) + compressed key frames linked by time
- PDF and PowerPoint `.pptx` → per-page/slide text, page image, three hashes (file SHA-256, normalised-text SHA-256, pHash)
- Duplicates: exact file · shared slide · similar (needs review)
- Search → text + frame/slide + timestamp
- Offboarding review → recommends, never deletes
- Exports: transcript `.txt`, unique slides as `.pptx` / `.pdf`, AI-ready JSON / JSONL with source links
- Unique-slide pass: near-duplicate frames are merged, the transcript is not re-run
- Storage report from **measured bytes** with four scenarios (0 today/real, 1 replace videos, 2 remove exact copies, 3 both)

Out of scope: speaker ID, slide/video recreation, live SharePoint/OneDrive/Ericsson Play, chatbot, real deletion, cloud AI.

**How to run it:** see [`START-HERE.md`](START-HERE.md) (Windows, step by step).

## Layout and ownership

```
contracts/   SHARED, FROZEN. API (openapi.yaml), manifest + API JSON Schemas, schema.sql, generated TS + Python types, test-only example fixtures
frontend/    Stream 1 · React + Vite + TS           (always the real API, no mock mode)
backend/     Stream 2 · FastAPI + SQLite FTS5       (implements contracts/openapi.yaml)
pipeline/    Stream 3 · ffmpeg, faster-whisper, PyMuPDF, imagehash (writes derived files + manifest.json)
data/        originals/ (read-only, never deleted) · derived/<asset_id>/  — git-ignored
```

**Rule:** streams share ONLY `contracts/` and hand off via **one `manifest.json` per file**
(`data/derived/<asset_id>/manifest.json`). No stream imports another stream's code. Read
[`contracts/CONTRACTS.md`](contracts/CONTRACTS.md) before writing code. Work happens on a branch per change
(`feature/...`, `fix/...`, `docs/...`) and is merged to `main` through a pull request.

## Run

Windows step-by-step guide: [`START-HERE.md`](START-HERE.md). Short version for Linux/macOS:

```bash
# Backend – http://localhost:8000/health
cd backend && python3 -m venv .venv && . .venv/bin/activate \
  && pip install -r requirements.txt -e ../contracts/python \
  && uvicorn app.main:app --port 8000

# Pipeline (needs system ffmpeg) – used by the backend to process uploads
cd pipeline && python3 -m venv .venv && . .venv/bin/activate \
  && pip install -r requirements.txt -e ../contracts/python -e .

# Frontend – http://localhost:5173 (live API)
cd frontend && npm install && npm run dev
```

**Real data only.** The app has no mock mode and no built-in demo data. You add real files (MP4, PDF, PPTX) through
the Library page or `python -m app.cli add-file`. The synthetic examples in `contracts/fixtures/` and the decks/videos
built inside `pipeline/tests/` are used **only by the automated tests**; they are never loaded into a real database.

Contracts (only when all streams agree to change them):

```bash
python3 -m venv .venv-tools && .venv-tools/bin/pip install jsonschema referencing datamodel-code-generator pyyaml openapi-spec-validator pydantic
contracts/scripts/generate.sh && python3 contracts/scripts/make_fixtures.py && .venv-tools/bin/python contracts/scripts/check_contracts.py
```

## Safety rules

- Nothing deletes or modifies originals. No DELETE endpoint. Offboarding = recommendation only.
- Processing alone saves no storage; scenario 0 (negative) is always shown. Formula in CONTRACTS.md §6.
- All processing is local; sample files never leave the laptop and are never committed (see `.gitignore`).

## Ambiguities resolved at freeze (see CONTRACTS.md)

1. Page says "3 scenarios" in the MVP table but defines **4** (0–3) in the savings section → we ship 4.
2. Page's scenario formulas are shorthand (S1 lists only video derived; S2 omits derived/index), while its
   general definition says A = kept originals + **all** derived + index → we use the general definition in all
   scenarios (conservative, slightly lower %). Flag for team if you prefer the shorthand.
3. Page ids like `p4`/`f3` are only unique per asset → DB keys are `(asset_id, id)`, global refs `<asset_id>:<id>`.
4. Duplicate engine needs all files, the pipeline sees one → hashes come from the pipeline, matching runs in the backend over SQLite.
5. Offboarding "duplicate elsewhere" = exact SHA-256 copy owned by someone else (open question to organizers whether near-duplicates count).
6. `manifest.json` can't list its own size → backend measures it at ingest and adds it to D.
