# frontend/ — Stream 1 (React + Vite + TypeScript)

Demo UI for the 8 screens on the design Page. Works fully on `contracts/fixtures` (mock mode) and switches to the
real FastAPI backend with one env var. Team prototype; not an official Ericsson product.

```bash
cd frontend
npm install
cp .env.example .env.local   # VITE_USE_MOCKS=true (default) until checkpoint 1
npm run dev                  # http://localhost:5173
npm run typecheck && npm run build
```

Live API: set `VITE_USE_MOCKS=false` in `.env.local` and restart `npm run dev`. Vite proxies `/api`, `/files`,
`/health` to `http://localhost:8000`. The nav badge shows MOCK DATA / LIVE API (and "backend offline" if `/health` fails).

## Screens

| Route | Screen | Endpoints |
|---|---|---|
| `/library` | Library & ingest: upload (.mp4/.pdf + simulated source + owner), Process, job progress polling | `GET/POST /api/assets`, `POST /api/assets/{id}/process`, `GET /api/jobs/{id}` |
| `/search?q=` | One box; hit = snippet + frame/slide image + timestamp/page; ↑/↓/Enter, `/` focuses | `GET /api/search` |
| `/recording/:id?seg=` | Transcript ⇄ key frames by time, time ruler, frame strip, phrase filter, original video (live) | `GET /api/assets/{id}/timeline`, `GET /api/assets/{id}` |
| `/document/:id?page=` | Pages with text, 3 hashes, "also in"/"similar to" badges, exact-copy banner, metadata (null = "not found in file") | `GET /api/assets/{id}/slides`, `GET /api/duplicates` |
| `/duplicates?type=` | Exact file / shared slide / similar (needs review) with evidence; word diff for similar slides | `GET /api/duplicates`, `/slides` |
| `/storage` | Totals O/D/I, 4 scenarios with bars, formula re-checked in the browser (✓/✗), not counted, info lost, Ericsson illustration kept separate | `GET /api/storage/report` |
| `/offboarding?owner=` | Recommendation only (`deletes_performed: false`), CSV/JSON download for the approver, local flags | `GET /api/offboarding` |
| `/export` | JSONL table with provenance + download; one-asset JSON preview + download | `GET /api/export.jsonl`, `GET /api/assets/{id}/export` |

## Code map

- `src/api/config.ts` — the one mock/live switch (`USE_MOCKS`, `absUrl`).
- `src/api/types.ts` — `Api` interface, one method per endpoint in `contracts/openapi.yaml`.
- `src/api/live.ts` — fetch client; parses the contract `ErrorResponse` into `ApiError`.
- `src/mocks/index.ts` — typed fixtures (incl. the 4 manifests and `export.jsonl?raw`).
- `src/mocks/mockApi.ts` — same `Api` built only from fixtures. Exact fixture returned where one exists; other
  assets derived from the manifests (same shape). Mock search = in-browser AND/prefix match over manifests.
  Uploads hash the file in the browser (SHA-256, ≤300 MB); job progress is **simulated** and labelled so.
- Images: mock mode draws labelled "MOCK IMAGE" SVGs; live mode loads `/files/...` with the same fallback on error.
- Snippets: only `<mark>` is interpreted; everything else renders as plain text (no `dangerouslySetInnerHTML`).

## Rules kept

No delete button or delete call anywhere. Processing is shown as **adding** bytes. Scenario 0 (negative) always shown.
Mock numbers are labelled "Mock fixture numbers"; Ericsson's ~1 GB → ~50 KB + ~2 MB example is shown only as their illustration.
