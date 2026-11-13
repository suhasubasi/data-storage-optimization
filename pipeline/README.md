# pipeline/ — Stream 3 (ffmpeg + faster-whisper + PyMuPDF + imagehash)

Reads ONE original (read-only) and writes derived files + ONE `manifest.json` into
`data/derived/<asset_id>/`. Never touches the database. **Never deletes or modifies originals.**
**Processing alone saves no storage** — it only adds derived bytes; savings are computed by the
backend storage report (CONTRACTS.md §6). Everything runs locally; no cloud AI / transcription API.

## Setup

```bash
cd pipeline
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt -e ../contracts/python -e .
ffmpeg -version            # system dependency (needs libwebp + libx264 + flite for the sample generator)
.venv/bin/pytest -q
```

## Run

```bash
# PDF
.venv/bin/python -m dso_pipeline process --asset-id a_01 --kind document \
    --input ../data/originals/a_01/deck.pdf --out ../data/derived/a_01
# MP4
.venv/bin/python -m dso_pipeline process --asset-id a_02 --kind video \
    --input ../data/originals/a_02/talk.mp4 --out ../data/derived/a_02
```

Exit 0 = `manifest.json` written (validated against `dso_contracts.models.Manifest`, written atomically
via `manifest.json.tmp` → rename, and LAST). Exit 1 = failed: message on stderr + `error.json`
(`{"error": {"code": "pipeline_failed", "message": ..., "details": {"stage": ...}}}`), no manifest.
Exit 2 = bad arguments. `progress.json` = `{"stage": "...", "progress": 0..1, "stage_progress": 0..1}` is updated during the run. `progress` is stage-weighted (fixed weights per step); `stage_progress` is the real fraction of the current step (key frames = video time / duration, transcribing = last finished Whisper segment end / duration, pages = pages done / pages). Reporting progress never changes Whisper settings or output.

At start, the pipeline removes only its own earlier outputs in `--out` (`manifest.json`, `error.json`,
`progress.json`, `transcript.json`, `frames/`, `pages/`), so re-processing never leaves stale files.
It refuses an `--out` that contains the input or lies inside an `originals/` folder, and checks that the
original's size/mtime did not change during the run.

## Output layout

```
data/derived/<asset_id>/
  manifest.json        # hand-off to backend (not listed in derived_files)
  progress.json        # status file (not derived data, never counted)
  error.json           # only on failure
  transcript.json      # video: {language, model, duration_seconds, segments[]}    kind=transcript
  frames/f<n>.webp     # video key frames, max 1280 px wide                        kind=frame
  pages/p<n>.webp      # PDF page images, max 1280 px wide                         kind=page_image
```
Temp files (16 kHz WAV) live in `.tmp-*` inside `--out` and are always deleted.

## What is computed

- **File SHA-256** (`original.sha256`), streamed.
- **PDF**: per page: text (PyMuPDF, `import pymupdf`), `text_sha256` = SHA-256 of NFKC→lower→collapse
  whitespace→strip, page image WebP, `phash` = `imagehash.phash(hash_size=8)` (16 hex) of the saved WebP.
  Metadata: title/author/date from PDF metadata; `doc_number` / `revision` only if literally present
  (file name, subject/keywords, page 1; revision needs a "Rev"/"Revision" label), else null. Pages without
  text get a warning (OCR is out of scope).
- **Video**: ffmpeg samples `sample_fps` frames/s and streams them through a pipe; a frame is kept when vs.
  the last kept frame pHash distance ≥ `frame_change_min_phash_distance` OR ≥ `frame_change_min_pixel_fraction`
  of a 160×90 gray thumbnail changed by > `frame_change_pixel_level` (catches same-template slides whose
  pHash barely moves). Frame `[t_start, t_end)`; segment `frame_id` = frame on screen at segment start.
  `phash` per frame (same algorithm as pages, so a frame of a slide gets the same hash as the PDF page).
- No cross-file grouping — the backend matches hashes across the corpus.

## Whisper model

Default from `../contracts/thresholds.json`: `faster-whisper small int8` on CPU (VAD on, beam 5).
Weights download once from Hugging Face into `~/.cache/huggingface` (outside git), then run offline
(`HF_HUB_OFFLINE=1`). Switch with env vars:

| Env | Default | Example |
|---|---|---|
| `DSO_WHISPER_MODEL` | `small` | `base` (≈2× faster), `medium`, `large-v3`, or a local CT2 model dir |
| `DSO_WHISPER_DEVICE` | `cpu` | `cuda` (NVIDIA GPU, fails if none), `auto` (GPU if found, else CPU) |
| `DSO_WHISPER_COMPUTE` | `int8` on CPU, `int8_float16` on GPU | `float32`, `float16` |
| `DSO_WHISPER_LANGUAGE` | auto-detect | `en`, `sv` |
| `DSO_WHISPER_BEAM` | `5` | `1` (fastest) |
| `DSO_WHISPER_MODEL_DIR` | HF cache | `/models` |
| `DSO_TRANSCRIBER` | `whisper` | `stub` = **fake transcript for tests only** |
| `DSO_THRESHOLDS` | `../contracts/thresholds.json` | path to another thresholds file |
| `DSO_DATA_DIR` | auto (parent of `originals/`) | used only for `original.path` |

### NVIDIA GPU (opt-in)

Whisper can run on an NVIDIA GPU. It is **off by default**, because GPU text is close to the CPU text
but not identical. Measured on an RTX 5070 Laptop (8 GB), model `small`, same settings (beam 5, VAD on):

| Video | CPU int8 | GPU int8_float16 | Word match vs CPU (case and punctuation ignored) |
|---|---|---|---|
| Jury and prizes (6 min) | 35.3 s | 9.7 s | 97.98% (13 of 568 words differ) |
| GraalVM talk (16 min) | 94.3 s | 26.0 s | 96.99% (67 of 1677 words differ) |

`float16` was about as fast but a little further from the CPU text (95.96% / 97.05%).
Typical differences: "Okay. Are we ready?" vs "Okay, are we ready?", "you're all doing great" vs
"you all are doing great", and a name heard differently ("Tommy, what's on this?" vs "Tommy Watson").

Setup (Windows, once):

```powershell
nvidia-smi                                   # must list the GPU
cd pipeline
.\.venv\Scripts\python.exe -m pip install "nvidia-cublas-cu12>=12.8,<13"
.\.venv\Scripts\python.exe -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"   # 1 = OK
```

ctranslate2 4.9 already ships cuDNN 9 (`cudnn64_9.dll`); the pipeline finds the cuBLAS DLLs from
the pip package by itself. Then turn it on with `"whisper_device": "cuda"` (or `"auto"`) in
`contracts/thresholds.json`, or set `DSO_WHISPER_DEVICE=cuda` before you start the backend.
A GPU transcript says `faster-whisper small int8_float16 cuda` in `transcript.json` and the
manifest; a CPU transcript still says `faster-whisper small int8`.

Note: we pass the WAV as a numpy array, because faster-whisper 1.2.1's own decoder breaks with PyAV ≥ 15.

Measured on the box (8 CPU cores): 22 s synthetic talk → 3.6–4 s total with `small`;
134 s clip → 11 s with `small`, 5 s with `base` (≈12× real time with small → a 30-min recording ≈ 2.5–3 min).
4-page PDF → ~0.5 s.
