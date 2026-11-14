# frontend/ — Stream 1 (React + Vite + TypeScript)

The desktop app, using the design promoted from `frontend-prototype/`, with an Impact overview and all nine working screens.
It always uses the real FastAPI backend: there is no mock mode and no
built-in demo data. Every number, image and text comes from real files processed by the backend.
Team prototype; not an official Ericsson product.

```bash
cd frontend
npm install
cp .env.example .env.local   # optional: only VITE_API_BASE_URL (empty = Vite proxy to :8000)
npm run dev                  # http://localhost:5173 (start the backend first)
npm run typecheck && npm run build
npm test                     # scenario arithmetic and real-file evidence selection
```

Both `npm run dev` and `npm run preview` serve on port 5173 and proxy `/api`, `/files`, `/health`
to `http://127.0.0.1:8000`. Stop the dev server before using preview (`npm run build` first).
Port 5173 must be available; the app does not silently switch ports. The top bar shows Live API (and
"backend offline" if `/health` fails). An old `VITE_USE_MOCKS` line in `.env.local` is ignored.

## Screens

| Route | Screen | Endpoints |
|---|---|---|
| `/overview` (also `/`) | Live impact summary, potential vs current storage, links to real evidence, current scope and future work | `GET /api/storage/report`, `GET /api/assets` |
| `/library` | Library & ingest: upload (.mp4/.pdf/.pptx + simulated source + owner), Process, job progress polling | `GET/POST /api/assets`, `POST /api/assets/{id}/process`, `GET /api/jobs/{id}` |
| `/search?q=` | One box; hit = snippet + frame/slide image + timestamp/page; ↑/↓/Enter, `/` focuses | `GET /api/search` |
| `/recording/:id?seg=` | Transcript ⇄ key frames by time, time ruler, frame strip, phrase filter, original video (live) | `GET /api/assets/{id}/timeline`, `GET /api/assets/{id}` |
| `/document/:id?page=` | Pages with text, 3 hashes, "also in"/"similar to" badges, exact-copy banner, metadata (null = "not found in file") | `GET /api/assets/{id}/slides`, `GET /api/duplicates` |
| `/duplicates?type=` | Exact file / shared slide / similar (needs review) with evidence; word diff for similar slides | `GET /api/duplicates`, `/slides` |
| `/storage` | Totals O/D/I, 4 scenarios with bars, formula re-checked in the browser (✓/✗), not counted, info lost, Ericsson illustration kept separate | `GET /api/storage/report` |
| `/offboarding?owner=` | Recommendation only (`deletes_performed: false`), CSV/JSON download for the approver, local flags | `GET /api/offboarding` |
| `/export` | JSONL table with provenance + download; one-asset JSON preview + download | `GET /api/export.jsonl`, `GET /api/assets/{id}/export` |
| `/settings` | Speech model and device selection, installed-model status, save settings | `GET/PUT /api/settings` |

Navigation groups these screens into Workspace, Media & slides, Storage governance, and AI & runtime.
The default landing page is Impact overview. All positive savings are hypothetical and require approval;
current disk usage is shown alongside them. The Library keeps intake collapsed until you choose Upload
or Process; file hashes, IDs and timestamps remain available under each row's File details.
The shared top bar provides quick search and an upload shortcut. Recording and document routes without
an asset ID show a file picker.

`frontend-prototype/` remains a reference; make future app changes in `frontend/`.
The pre-promotion frontend source/configuration is saved locally in `.pre-promotion-backup/` (git-ignored).
The pre-hackathon-refinement source is in `.hackathon-ui-backup/` (git-ignored), with protected-source hashes.

## Code map

- `src/api/config.ts` — API base URL (`absUrl`) and download links.
- `src/api/types.ts` — `Api` interface, one method per endpoint in `contracts/openapi.yaml`.
- `src/api/live.ts` — fetch client; parses the contract `ErrorResponse` into `ApiError`.
- Images: loaded from `/files/...`; if one is missing, a neutral "not available" card is shown (never fake artwork).
- Snippets: only `<mark>` is interpreted; everything else renders as plain text (no `dangerouslySetInnerHTML`).

## Rules kept

No delete button or delete call anywhere. Processing is shown as **adding** bytes. Scenario 0 (negative) always shown.
Ericsson's ~1 GB → ~50 KB + ~2 MB example is shown only as their illustration.
