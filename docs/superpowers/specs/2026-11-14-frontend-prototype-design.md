# Frontend prototype: calm blue workspace

Status: proposed for approval. Scope: `frontend-prototype/` only.

## Intent

Redesign all nine existing screens into a coherent, approachable workspace. Use `frontend-prototype/sample-ui.webp` as inspiration for hierarchy, whitespace, and organized navigation, with an original muted blue visual treatment. Preserve existing backend compatibility and all existing function, variable, component, prop, type, and CSS custom-property names.

## Approaches

1. Calm blue workspace (recommended): navy navigation, pale blue-gray canvas, white panels, readable tables, and muted blue emphasis. Suits long sessions reviewing documents and recordings.
2. Fully dark studio: more cinematic for recordings, but less suitable for dense tables and document inspection.
3. Close recreation of the reference: familiar compact dashboard, but constrains the distinct media and governance workflows unnecessarily.

The implementation approach is presentation-only React markup and CSS using the existing Vite stack. No new UI dependencies or external font requests. This is the designer's recommendation, pending user approval.

## Visual design

- Navy sidebar (#172f4b), muted denim primary actions (#365f89), powder-blue selections (#e8f0f8), canvas (#f3f6fa), white surfaces, dark slate text (#20334a).
- Retain semantic success, warning, and error colors with subdued backgrounds and readable text. No neon, luminous gradients, or fake trend indicators.
- System sans-serif typography; strong page titles, concise descriptions, clearly differentiated section headings and helper text.
- Consistent spacing, soft borders, restrained shadows, approximately 12–16 px panel corners and 8–10 px control corners.
- A compact brand block, visually separated navigation groups, clear active item, and a concise prototype/source-data disclosure.
- Search and upload remain prominent in the shared top bar. Keyboard shortcut stays visible.
- Page headers have a subtle blue visual motif using CSS, with no invented metrics or product capabilities.

## Layout sketch

```text
┌─────────────────┬──────────────────────────────────────────────┐
│ DSO workspace   │ Search everything…  /     API status  Upload │
│                 ├──────────────────────────────────────────────┤
│ Workspace       │ Library & ingest                             │
│  Library        │ Your recordings and documents, in one place. │
│  Search         │                                              │
│ Media & slides  │ [ Assets ] [ Originals ] [ Index ] [ Tests ] │
│  Recordings     │                                              │
│  Documents      │ [ Upload a file            ] [ Processing ] │
│ Governance      │                                              │
│  …              │ [ File filters               Search files ] │
│                 │ [ Readable asset table and existing actions] │
│ Originals safe  │                                              │
└─────────────────┴──────────────────────────────────────────────┘
```

## Screen coverage

- Library: emphasize asset overview, make the upload form inviting and legible, clarify the upload/processing sequence, improve table scanning and queued-job feedback.
- Search: prominent search field, clear result categories, readable preview cards, useful empty/loading/error states, existing keyboard navigation retained.
- Recording: cohesive preview and transcript panels, clear active frames and transcript rows, readable speaker controls, all playback, chat, filter, seek, and download actions retained.
- Documents: calm reading surface, clear selected thumbnail, better distinction between previews, extracted text, metadata, and match evidence; preserve reader/grid modes.
- Duplicates: readable comparison surfaces, differentiated evidence and review status, existing scope controls and links retained.
- Storage: consistent summary cards and scenario charts, clearly distinguish measured data from hypothetical savings, preserve formulas and explanations.
- Offboarding: approachable owner selection and review table, retain recommendation-only notice, approvals, and export actions.
- Export: clearer asset selection, tabs, filters, and code panels; retain all exported data, field names, and formats.
- Settings: legible model/device choices, clear selection and disabled states, effective configuration and save feedback retained.

## Compatibility constraints

- Do not rename any existing functions, variables, parameters, components, types, props, CSS custom properties, DOM IDs, or existing classes. Additional presentation classes and semantic attributes are allowed.
- Keep API code, contracts, helper logic, hooks, endpoint paths, request fields, response fields, routes, query parameters, enums, export schemas, and event-handler expressions unchanged.
- Preserve all conditional rendering, data expressions, calculations, form bindings, media references, and existing controls. Do not replace live data with demonstration data.
- Visible labels and explanatory prose may be simplified without changing their meaning or machine-readable values. Keep prototype disclosures and accurate data/source caveats accessible.
- Do not change `frontend/`, backend, contracts, dependencies, or the reference image. Preserve pre-existing `.v1-backup` contents.

## Responsive and accessible behavior

Desktop retains a sidebar and spacious main canvas. Tablet layouts stack dense panels. At phone widths, navigation becomes compact and scrollable, controls wrap, and tables scroll inside their containers instead of overflowing the viewport. Keep every route reachable. Use visible keyboard focus, readable contrast, adequate control sizes, semantic labels, and reduced-motion support. Do not visually reorder interactive content in a way that conflicts with keyboard order.

## Verification

Before editing, snapshot source files and compute an inventory of existing identifiers, handler expressions, route values, request code, and protected file hashes. After editing, compare these to verify preservation. Run existing typecheck/build commands. Inspect all nine routes in a browser at desktop and phone sizes; exercise search, filters, document selection, recording controls, and navigation using existing data when available. Avoid triggering uploads, processing, or settings mutations solely for visual inspection; verify their bindings against the snapshot. Report unavailable backend-dependent checks honestly. Use temporary browser fixtures only for visual verification if the backend is unavailable, never in delivered product code.

## Builder discretion

Exact spacing, decorative CSS details, icon placement using existing icons, concise visible wording, and responsive breakpoints may be chosen during implementation and refined after browser inspection. Do not add features or change functional behavior.
