# Ericsson Data Storage Optimization — MVP (Campor × BUILD Hackathon 2026)

[![CI](https://github.com/suhasubasi/ericsson-data-storage-optimization/actions/workflows/ci.yml/badge.svg)](https://github.com/suhasubasi/ericsson-data-storage-optimization/actions/workflows/ci.yml)

Local tool that turns long recordings and documents into compact, searchable, AI-ready data and finds
duplicates across (simulated) SharePoint / OneDrive / Ericsson Play — **without deleting anything**.

- MP4 → timed local transcript (faster-whisper) + local speaker diarization & role classification (`Speaker 1..N`, `Presenter` / `Documentary` / `Overlap`) + compressed key frames linked by time
- PDF and PowerPoint `.pptx` → per-page/slide text, page image, three hashes (file SHA-256, normalised-text SHA-256, pHash)
- Duplicates: exact file · shared slide · similar (needs review), plus video frame → source-of-truth slide matching
- Search → text + frame/slide + timestamp (spoken text, slide text, titles, and an attached meeting chat)
- Meeting chat (Outlook `.msg` or `.txt`) attached to a recording, shown on the Recording page with estimated times
- Offboarding review → recommends, never deletes
- Exports: transcript `.txt`, unique slides as `.pptx` / `.pdf`, AI-ready JSON / JSONL with source links
- Unique-slide pass: near-duplicate frames are merged, the transcript is not re-run
- Storage report from **measured bytes** with four scenarios (0 today/real, 1 replace videos, 2 remove exact copies, 3 both)

Out of scope: real-world speaker name identification (anonymous `Speaker 1..N` + `Presenter`/`Documentary` roles are included), slide/video recreation, live SharePoint/OneDrive/Ericsson Play, chatbot, real deletion, cloud AI.

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

## Which Whisper model?

The app turns speech into text with Whisper (faster-whisper, runs on your own computer). You choose the
model on the **Settings** page. The choice is used for the next file you process. Files that are already
processed are never re-processed by themselves. Each transcript records the model and device that made it
(the "Model" box on the recording page).

| Model in Settings | Best for | NVIDIA GPU memory it used (measured) | On a CPU only | Download size |
|---|---|---|---|---|
| **Fast** · `small` (default) | Any computer, also without a GPU | about 0.6 GB | Yes, works well | about 0.5 GB |
| **Fast + accurate** · `large-v3-turbo` | A computer with an NVIDIA GPU (4 GB or more is comfortable) | about 1.3 GB | Possible but slow (about 3× slower than `small`) | about 1.5 GB |
| **Most accurate** · `large-v3` | A computer with an NVIDIA GPU (6 GB or more is comfortable) | about 2.4 GB | Not recommended (about 5× slower than `small`) | about 3 GB |

`medium` is not offered on purpose, to keep the choice simple. The "4 GB / 6 GB is comfortable" advice is our
recommendation with room to spare, not a measured limit.

**Our pick:** with an NVIDIA GPU, use **Fast + accurate (`large-v3-turbo`)** and Device **GPU**.
Without a GPU, keep **Fast (`small`)** on **CPU**.

### Download a model (once)

`small` downloads by itself the first time you process a video. Download the big ones before you pick them
(the Settings page shows "not installed" until then). Run this in the project folder (Windows, PowerShell):

```powershell
# Fast + accurate (about 1.5 GB)
pipeline\.venv\Scripts\python.exe -c "from faster_whisper.utils import download_model; print(download_model('large-v3-turbo'))"
# Most accurate (about 3 GB)
pipeline\.venv\Scripts\python.exe -c "from faster_whisper.utils import download_model; print(download_model('large-v3'))"
# Fast (about 0.5 GB)
pipeline\.venv\Scripts\python.exe -c "from faster_whisper.utils import download_model; print(download_model('small'))"
```

(Linux/macOS: `pipeline/.venv/bin/python` instead.) The models go to `~/.cache/huggingface/hub`, outside git.
For the GPU you also need the one-time GPU setup in [pipeline/README.md → NVIDIA GPU](pipeline/README.md#nvidia-gpu-opt-in).
Then open **Settings**, pick the model and the device, and press **Save**. Reload the page after a download.

If the backend was started with `DSO_WHISPER_MODEL` or `DSO_WHISPER_DEVICE` set, that value wins over the
Settings page (the page tells you when this happens).

### Measured speed (RTX 5070 Laptop GPU 8 GB, AMD Ryzen AI 7 350, 13 Nov 2026)

Only the speech-to-text step, same settings for all (beam 5, silence filter on). Model load time not included
(1.5 s for `small`, about 3.3 s for `large-v3-turbo`, 5–6.5 s for `large-v3`).

| Video | `small` CPU | `small` GPU | `large-v3-turbo` GPU | `large-v3` GPU |
|---|---|---|---|---|
| Jury and prizes (6 min) | 25.7 s | 7.8 s | **5.0 s** | 14.0 s |
| GraalVM talk (16 min) | 83.5 s | 24.7 s | **20.1 s** | 49.3 s |

CPU only, first 60 s of the Jury video: `small` 7.0 s, `large-v3-turbo` 22.8 s, `large-v3` 34.1 s.
So on a CPU, `large-v3-turbo` needs roughly 23 minutes for a 1-hour recording (an estimate from that 60-s test).

How accurate? We have no hand-checked "true" transcript, so we cannot give a real error rate. We compared the
texts and looked at clear cases:

- `small` wrote "the s computer and writehub in dynamic resource allocation"; both large models wrote
  "edge computing right having dynamic resource allocation".
- `small` wrote "holo fame"; `large-v3-turbo` wrote "hall of fame".
- `small` (CPU) wrote "ahead of time completion"; `large-v3-turbo` wrote "ahead of time compilation".
- `large-v3` alone wrote "more prizes" (the others: "more prices") and got the name "Tommy Watson" right,
  where `large-v3-turbo` wrote "me tell me".
- `large-v3-turbo` sometimes repeats a short word ("when when when"), and `large-v3` keeps "uh" and "um".

About 94–95% of the words are the same between `small` and the large models, and 96–98% between
`large-v3-turbo` and `large-v3`.

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
