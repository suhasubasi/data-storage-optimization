# data/ (git-ignored contents)

- `originals/<asset_id>/<filename>` — uploaded originals. Written once by the backend, then read-only. **Never deleted** by any stream.
- `derived/<asset_id>/` — written only by the pipeline: `manifest.json`, `transcript.json`, `frames/f<n>.webp`, `pages/p<n>.webp`, optional `progress.json` / `error.json` (status files, not counted as derived bytes).
- `samples/` — Ericsson samples and our synthetic test files. Never sent to any cloud service.
- `dso.sqlite` — backend database (+ FTS5 index). Its measured size is `I` in the storage report.
