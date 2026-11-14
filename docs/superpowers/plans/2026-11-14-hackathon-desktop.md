# Hackathon Desktop Implementation Plan

> Execute inline using the executing-plans workflow; independent review after implementation.

**Goal:** Make the desktop frontend demonstrate Ericsson's storage and data-activation use cases clearly with real evidence.

**Architecture:** Existing React routes and API adapter; new overview reads existing assets/storage endpoints. Pure scenario checking and evidence selection helpers are shared with Storage and tested independently.

**Tech Stack:** React 18, Vite 5, TypeScript, Node test runner; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-14-hackathon-desktop-design.md`

## Global constraints

Desktop only. Backend, pipeline, contracts and API files remain byte-for-byte unchanged. Real data only; all hypothetical scenarios require explicit labels. No deletion, data migration or live mutation for testing.

## Review focus

Zero original bytes and negative savings; invalid formulas; synthetic or unprocessed example files; upload deep-link expansion and job visibility; long filenames and desktop table overflow.

## Tasks

- [x] Save frontend baseline and protected-file hashes. Add failing behavior tests for scenario validation and example selection, implement `checkScenario` and `selectEvidence`, run tests.
- [x] Implement `pages/Overview.tsx`, navigation and landing route, using existing API methods. Add compact scenario comparison to Storage, reuse validation helper. Preserve all evidence and disclosures.
- [x] Refine Library intake disclosure and row details, keep upload/process/reprocess handlers and payloads. Scope tab counts consistently. Add `desktop.css` for typography, layout and overview styling; no dependency changes.
- [x] Run tests/typecheck/build, desktop browser checks including empty/error states, verify protected hashes, independent review, address findings and record results.

## Execution record

User authorized design judgment and implementation; no separate design approval needed. Workspace has no Git repository, so use source backup and SHA-256 comparison rather than branches or commits.

## Final verification

- `npm test`: 6/6 pass. Covers complete storage arithmetic, null percentages with zero originals, negative savings, invalid figures, ready real-file selection and empty libraries. Tests were first run before the new helper existed and failed, then passed with implementation.
- `npm run typecheck`: pass. `npm run build`: pass; 60 modules, 83.02 KB gzipped JavaScript, no added dependencies.
- All ten screen families rendered on desktop with no page errors. Overview, Library and Storage were checked at 1440px and 1280px; no horizontal page overflow. Other existing screens checked at 1440px, including real recording/document deep links, search, duplicates, offboarding, exports and settings.
- Library: global Upload expands intake; missing-file validation; document and filename filtering; expandable ID/date/hash; reprocessing cancellation; Open navigates to the document.
- Overview: root route opens overview; first evidence card opens an actual ready recording. Empty data has zero-width bars and upload fallback; storage growth produces a longer projected bar and no positive-savings claim; invalid arithmetic suppresses the headline; unavailable report shows an error without stale savings.
- Browser-only intercepted processing request verified error feedback and scroll into view. No upload, real processing, settings write or deletion was performed.
- Independent code review found no critical or important issues. It identified two minor issues: empty/growth bar scaling and off-screen processing feedback. Both were fixed. The empty-chart test first reproduced a 431px filled bar for zero bytes, then passed with 0px. Proportional negative-savings and feedback visibility checks also passed.
- SHA-256 comparison: all 81 protected API/backend/contracts/pipeline source files unchanged. Existing 13 live assets still present. Built preview `/overview`: HTTP 200.
- Final screenshot: `output/playwright/hackathon-overview-final.png`; earlier desktop comparison captures are alongside it.

## Decisions and remaining boundaries

Ruling: add a live overview as the default landing page while preserving `/library` and every existing route. This makes the challenge outcomes visible first; existing links remain valid.

Ruling: replace the prominent zero test-file KPI with ready-file count; retain synthetic-file controls and counts in the Library table. This gives real content priority without hiding test-data scope.

Backend capabilities, processing accuracy and real platform connectors are unchanged. Existing top-bar settings and recording chat-count refresh quirks are outside this refinement and remain as recorded in the preceding migration notes.
