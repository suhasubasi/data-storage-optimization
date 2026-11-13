# frontend/ — Stream 1 (React + Vite + TypeScript)

Blank shell: layout + nav for the 8 screens on the design Page. No feature UI yet.

```bash
cd frontend
npm install
cp .env.example .env.local   # VITE_USE_MOCKS=true until checkpoint 1
npm run dev                  # http://localhost:5173
npm run typecheck
```

- Types: `import type { SearchHit } from "@contracts/ts/dso-contracts"` (generated, never edit).
- Mock data: `src/mocks/index.ts` (typed views of `contracts/fixtures/*.json`).
- Switch to the real API: set `VITE_USE_MOCKS=false` (Vite proxies `/api`, `/files`, `/health` to :8000).
- URLs in API bodies are relative (`/files/...`): wrap with `absUrl()` from `src/api/config.ts`.
- Search snippets contain only `<mark>` tags; escape everything else before rendering.
