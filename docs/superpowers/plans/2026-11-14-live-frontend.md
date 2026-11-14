# Live Frontend Implementation Plan

> Execute inline, using the executing-plans workflow adapted to this non-Git workspace.

**Goal:** Make the user's selected prototype design the normal, backend-connected frontend.

**Architecture:** Promote existing UI files into `frontend`; retain its established API adapter and router future flags. Serve through Vite on 5173 with FastAPI proxies in development and preview.

**Tech Stack:** Existing React 18, Vite 5 and TypeScript; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-14-live-frontend-design.md`

## Global constraints

Real backend only. Preserve all nine routes and existing API contracts. Preserve originals and the prototype reference. Keep environment configuration and package dependencies intact.

## Review focus

API and download parity; direct navigation to media routes; responsive overflow; backend-unavailable states; preview proxy and documentation accuracy.

## Task 1: Promote and verify

- [x] Save `frontend/src`, entry HTML, Vite configuration and README under `frontend/.pre-promotion-backup`.
- [x] Copy prototype `App.tsx`, `styles.css`, `pages`, `components` and `lib`; keep `main.tsx` and `api` from the established frontend.
- [x] Promote favicon, set active workspace title/disclosure and configure IPv4 backend proxies for dev and preview on 5173.
- [x] Update frontend README and startup guide to identify the canonical app.
- [x] Run `npm run typecheck` and `npm run build` in `frontend` (exit 0).
- [x] Browser-check all routes and desktop interactions with real data, including search-to-recording navigation and API-offline recovery. Confirm preview health/API/file responses. User clarified desktop-only acceptance.
- [x] Complete a fresh code review against backup and prototype; record verification evidence.

## Execution notes

The selected design already exists; this is a source promotion, not a new design exercise. Authorization comes from the user's request to make the prototype the real frontend. No Git commands, commits or worktrees are possible because the supplied workspace has no `.git` directory. Build and browser checks cover the migration without tests that simply assert copied source text.

## Verification results

- Typecheck passed; final production build passed with 57 modules transformed.
- All nine screen families loaded against the existing backend, including recording and document ID routes.
- Desktop viewport 1440px: content width 1440px. Library loads 13 existing files; document filter returns 5; filename filter returns 1 matching file.
- Live search for Ericsson returns 50 hits; clicking a hit opens Recording studio.
- Simulated network outage shows Backend offline and the library error; restoring connectivity loads all 13 files again.
- Temporary build preview on 5183 returned HTTP 200 for health, assets, storage, JSONL export, a document SPA route and a real slide image through the file proxy.
- A matched-document label overflow found during preliminary mobile inspection was fixed with two wrapping rules and verified at 390px. The user subsequently clarified desktop-only use; no additional mobile work was performed.
- Fresh independent static review found no critical or important migration issues. API files and router entry are preserved.

## Known minor prototype issues (deferred)

- Top-bar runtime model/device badge refreshes on page reload, not immediately after saving settings.
- Recording meeting-chat tab count refreshes on page reload, not immediately after attaching chat.
- Library recording/document tab counts exclude test files even when those files are visible.

No upload, reprocessing or settings mutations were performed on the user's data for verification. Existing originals and processed results remain in place.
