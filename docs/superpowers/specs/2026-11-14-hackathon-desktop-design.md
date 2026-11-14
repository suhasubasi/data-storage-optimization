# Hackathon desktop frontend

## Intent and source

The user delegated frontend improvements to make the strongest hackathon demonstration, explicitly desktop-only and frontend-only. Keep the selected calm blue workspace. Source: `C:/Users/suhas/Desktop/ericsson.pdf`, all three pages. The final pitch must cover addressed use cases, technical approach, scenario percentage savings, future AI data strategy and unresolved problems.

## Approach

Add an evidence-led Impact overview to the existing application, then tighten the Library and Storage views. A cosmetic-only pass would leave the value hard to discover; a separate pitch mode would duplicate application flows and risk stale numbers. The selected approach uses the existing backend as the only source of measurements, and links to working screens for evidence.

## Design

- `/overview` becomes the landing page. Show the combined hypothetical scenario with explicit approval wording, original versus projected total bytes, current disk usage alongside it, processed real-file counts and exact-copy overhead. Never label potential savings as storage already freed. Suppress savings emphasis for empty, invalid or non-positive scenarios.
- A four-step evidence path links to a ready recording, search, duplicate analysis and AI exports. Select example assets from actual ready, non-test files; do not invent examples. Explain the current local processing/provenance approach and distinguish future connectors, retention policy, quality evaluation and richer reconstruction from implemented features.
- Preserve every existing route and deep link. Keep the sidebar and typography visually familiar. Use readable desktop body/control sizes and smaller page headers.
- Library: collapse upload and processing into an expandable section, opened by the global upload action or processing action. Keep files prominent. Move ID/hash/date into row details, preserve every action and reprocessing confirmation, keep test-file counts consistent with the selected scope.
- Storage: add a compact comparison table for all four scenarios before detailed evidence; retain formula validation, loss disclosures, removal lists and test-data controls. Label hypothetical savings accurately.

## Constraints

No changes to backend, pipeline, contracts, API client/configuration, endpoint paths or payloads. No new dependencies. No public deployment. No uploads, processing or settings writes to user data for testing. Preserve baseline source backup and hash protected code before editing.

## Verification

Test scenario arithmetic and real-file selection with Node's built-in test runner and the installed TypeScript compiler. Run typecheck/build. Browse all routes on desktop, test upload expansion, filters, reprocess cancellation, search-to-recording navigation, overview links, zero-data and unavailable-backend states. Verify protected source hashes after changes. Independent final review.
