# pipeline/ — Stream 3 (ffmpeg + faster-whisper + PyMuPDF + imagehash)

Skeleton only (CLI argument parsing). The pipeline **only writes derived files + one
`manifest.json`** per original into `data/derived/<asset_id>/`. It never touches the database and
**never deletes or modifies originals**. Temporary files (e.g. extracted WAV) are deleted and not listed.

```bash
cd pipeline
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -e ../contracts/python -e .
ffmpeg -version            # system dependency
python -m dso_pipeline process --asset-id a_01 --kind video --input ../data/samples/x.mp4 --out ../data/derived/a_01
pytest -q
```

Use `import pymupdf` (not the deprecated `fitz` alias).
Manifest shape: `../contracts/schemas/manifest.schema.json` (validate with `dso_contracts.models.Manifest`).
Tunable thresholds: `../contracts/thresholds.json` (Stream 3 owns tuning; announce changes).
Test data: put synthetic files (incl. `deck (1).pdf`, a revised page, a 2-min clip) in `../data/samples/`.
