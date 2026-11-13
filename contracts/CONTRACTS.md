# Shared contracts — FROZEN v1.0 (Thu 12 Nov 2026, 23:00 Stockholm)

Source of truth: the approved design Page "Data Storage Optimization — System Design & MVP Plan"
(which follows the Ericsson challenge PDF). Anything **not** on the Page is marked
**REC** (= our recommendation) in the schema descriptions / SQL comments, and kept minimal.

**Change rule:** files in `contracts/` change only when all three streams agree (a real conflict
was found). After a change: edit `schemas/*.json` → `scripts/generate.sh` → `scripts/make_fixtures.py`
→ `scripts/check_contracts.py` must print `CONTRACTS OK` → one commit `contracts: …` → tell the others.
Exception: `thresholds.json` is tunable by Stream 3 (announce changes).

## 1. Files

| File | What | Consumed by |
|---|---|---|
| `schemas/manifest.schema.json` | Per-file hand-off manifest (pipeline → backend) | S2, S3 |
| `schemas/api.schema.json` | All API types: Asset, Job, Timeline, SlideList, **SearchHit**, **DuplicateGroup**, **StorageReport/StorageScenario**, **OffboardingReview/Row**, **ExportAsset/ExportChunk**, **HashRecord**, **MediaRef**, ErrorResponse | S1, S2 |
| `openapi.yaml` | Endpoints, params, status codes, error model (OpenAPI 3.1, refs the schemas) | S1, S2 |
| `schema.sql` | SQLite tables + FTS5 `search_fts` | S2 only |
| `thresholds.json` | pHash / similarity thresholds, frame sampling, whisper model (tunable) | S2 (duplicates), S3 |
| `ts/dso-contracts.ts` | GENERATED TypeScript types | S1 |
| `python/dso_contracts/models.py` | GENERATED Pydantic v2 models (`pip install -e contracts/python`) | S2, S3 |
| `fixtures/*.json`, `fixtures/export.jsonl` | Synthetic example per API response, **test-only** (contract check + backend tests; never shown to users) | contract check, S2 (tests) |
| `fixtures/manifests/a_0{1..4}.manifest.json` | Synthetic example manifests (1 video, 3 PDFs incl. `(1).pdf` copy), test-only | S2 (tests), S3 (target shape) |
| `scripts/` | `generate.sh`, `bundle_schemas.py`, `make_fixtures.py`, `check_contracts.py` | everyone |

## 2. Ownership (one folder per stream, nothing else is shared)

| Stream | Folder | Builds | Starts on |
|---|---|---|---|
| **1 · Frontend** | `frontend/` | React + Vite + TS, 8 screens (Library, Recording, Document, Search, Duplicates, Storage report, Offboarding, Export) | the real API only (mock mode removed in v1.2) |
| **2 · Backend** | `backend/` | FastAPI + SQLite FTS5: upload + SHA-256, job runner, manifest ingest, search, duplicate engine, storage report, offboarding, export, file serving | `openapi.yaml`, `schema.sql`, fixture manifests |
| **3 · Pipeline** | `pipeline/` | ffmpeg + faster-whisper (local, small/base int8) + key frames + PyMuPDF + image hashing → derived files + `manifest.json` | nothing from the others |

Streams never import each other's code. They share only `contracts/` and hand off via **one
`manifest.json` per file**. Checkpoints: Fri 12:00, Fri 16:00; feature freeze Fri 19:00.

## 3. Manifest hand-off

1. Backend saves the upload to `data/originals/<asset_id>/<filename>` (then makes it read-only — REC), computes SHA-256.
2. `POST /api/assets/{id}/process` → backend job runner (background thread) runs the pipeline (§4).
3. Pipeline writes derived files into `data/derived/<asset_id>/` and **last** writes `manifest.json`
   atomically (write `manifest.json.tmp`, then rename) — REC.
4. Backend validates it with `dso_contracts.models.Manifest`, measures `manifest.json` size on disk,
   and ingests into `assets / segments / frames / slides / derived_files / search_fts`.
5. Duplicate engine (backend, over SQLite) writes `matches`.

Conventions:
- Paths in the manifest are relative to `data/derived/<asset_id>/`; `original.path` is relative to `data/`.
- Local ids: segments `s<n>`, frames `f<n>`, slides `p<page>` (1-based). Global refs: `<asset_id>:<local_id>`; a whole file is just `<asset_id>`.
- `derived_files` lists **every** kept derived file (transcript, every frame, every page image, optional audio). Not `manifest.json` itself. Temp files are deleted, not listed.
- Time link: frame covers `[t_start, t_end)`; a segment's `frame_id` = frame on screen when the segment **starts**.
- Text hash: `NFKC → lowercase → collapse whitespace → strip → SHA-256 (UTF-8)`. pHash: `imagehash.phash(hash_size=8)` as 16 lowercase hex chars.
- Metadata (`doc_number`, `revision`, …) only when really present in the file/name; otherwise `null`. `speaker` is always `null` (out of scope).
- API URLs are relative: `/files/originals/<asset_id>/<filename>` and `/files/derived/<asset_id>/<path>`.

## 4. Pipeline invocation (REC — the Page only says "job runner, background thread")

```
<pipeline/.venv/bin/python> -m dso_pipeline process --asset-id a_01 --kind video|document \
    --input data/originals/a_01/<file> --out data/derived/a_01
```
Exit 0 + `manifest.json` present = done. Non-zero = failed; reason on stderr and in `error.json`.
Optional `progress.json` = `{"stage": "transcribing", "progress": 0.4}` for real job progress.
`progress.json` / `error.json` are status files, not derived data (never counted). A subprocess keeps
the heavy ML deps out of the backend venv. Backend path: env `DSO_PIPELINE_PYTHON`.

## 5. Duplicate classes (backend engine, thresholds from `thresholds.json`)

| Group type | `matches` row | Rule |
|---|---|---|
| `exact_file` | level `file`, type `exact`, method `sha256` | Same file SHA-256. File name never decides. |
| `shared_slide` | level `slide`, type `shared`, method `text_sha256+phash` | Same normalised-text SHA-256 **and** pHash distance ≤ `shared_slide_max_phash_distance` |
| `similar_slide` | level `slide`, type `similar`, method `phash` or `text_ratio` | Close pHash or text ratio ≥ min, but not shared → `needs_review: true`, never exact |

REC to avoid noise: never match an asset with itself; store pairs once with `a_id < b_id`; for slide
matching use one representative per exact-file group (the earliest upload), so `deck.pdf` and
`deck (1).pdf` don't produce duplicate slide groups; pages with fewer than
`min_normalised_text_chars_for_text_match` chars can't be `shared` by text alone.

## 6. Storage savings — formula (frozen)

**Processing alone saves nothing.** Derived files and the index ADD bytes. Storage is freed only if an
approved process later removes or archives an original or a copy. The tool never deletes, so
scenario 0 (today, real) is negative and is always shown.

```
Savings % = (O − A) / O × 100      (null if O = 0)
O = bytes of all original files in scope (every copy on every simulated system), measured on disk
D = all derived files (manifest.derived_files) + every manifest.json, measured
I = measured size of the SQLite file incl. FTS (data/dso.sqlite)
A = kept original bytes + D + I
```

| id | key | Removed (hypothetical, after approval) | A |
|---|---|---|---|
| 0 | `today` | nothing | `O + D + I` |
| 1 | `replace_videos` | every **processed (`ready`)** video original | `(O − ready video originals) + D + I` |
| 2 | `remove_exact_duplicates` | all but the earliest-uploaded copy in each SHA-256 group | `(O − extra exact copies) + D + I` |
| 3 | `both` | union of 1 and 2, each file once | `(O − both, no double counting) + D + I` |

- Shared/similar slides free nothing (files differ).
- `D` and `I` are counted in **every** scenario (conservative; see README "Ambiguities").
- Not counted: backups, replication, archive tiers, compute, model weights, money. Data volume only.
- Always show bytes before/after, the removed list, and what is lost (motion, gestures, live demos, tone of voice).
- Ericsson's ~1 GB → ~50 KB + ~2 MB "roughly 99%" (PDF p.2) is their illustration; we quote measured numbers.
- Reference calculation: `scripts/make_fixtures.py` (storage section) + check in `check_contracts.py`.

## 7. No-auto-delete rule (all streams)

- No code path deletes or modifies a file in `data/originals/`. There is **no DELETE endpoint**.
- Offboarding only recommends: `eligible_after_approval` iff an **exact** (SHA-256) copy exists that is
  owned by **someone else** (REC: so a leaver's two copies never both get recommended); otherwise `keep`.
  Response always has `deletes_performed: false`.
- The pipeline may delete only its own temp files.

## 8. Error model

Every non-2xx body: `{"error": {"code": ErrorCode, "message": "simple English", "details": {...}|null}}`.
Codes: `not_found` 404, `validation_error` 422 (override FastAPI's default shape), `unsupported_file_type` 415
(only `.mp4` → video, `.pdf` or `.pptx` → document; v1.2), `conflict` 409 (job already running), `pipeline_failed`, `internal_error` 500.
