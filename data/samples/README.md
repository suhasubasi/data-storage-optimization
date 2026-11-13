# data/samples — synthetic test files (not committed)

Generated locally, no Ericsson data:

```bash
cd pipeline && .venv/bin/python scripts/make_samples.py      # ~2 s
```

| File | Purpose |
|---|---|
| `deck.pdf` | 4-page deck, PDF metadata, "Doc. no. 1/221 02-FGB 101 Rev A" on page 1 |
| `deck (1).pdf` | byte-identical copy → exact_file duplicate (SHA-256), different name |
| `deck-revB.pdf` | Rev B: pages 2 and 4 unchanged (same text hash + pHash → shared), page 3 text changed (same pHash → similar, needs review) |
| `talk.mp4` | ~22 s: the deck pages as slides + synthetic speech (ffmpeg flite) incl. "as you see here" |

Optional ~2 min clip: `ffmpeg -stream_loop 5 -i talk.mp4 -c copy talk-2min.mp4`.
