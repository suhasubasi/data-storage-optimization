# Start here – run the app on Windows

This is a hackathon prototype, not an official Ericsson product.
Nothing is deleted: originals stay on disk, and offboarding only recommends.

## What you need

- Node.js 20 or newer
- Python 3.11 or 3.12 (not 3.13+)
- ffmpeg on your PATH (for video processing)

The first video you process downloads a local faster-whisper model. After that it works offline.

Optional: with an NVIDIA GPU, speech-to-text is much faster. Setup:
[pipeline/README.md → NVIDIA GPU](pipeline/README.md#nvidia-gpu-opt-in).

**Which speech model?** Pick it on the app's **Settings** page:

| Your computer | Pick in Settings |
|---|---|
| No NVIDIA GPU | **Fast** (`small`) on **CPU** (the default) |
| NVIDIA GPU, 4 GB or more | **Fast + accurate** (`large-v3-turbo`) on **GPU** (our pick) |
| NVIDIA GPU, 6 GB or more, best text matters more than time | **Most accurate** (`large-v3`) on **GPU** |

Download the big models once before you pick them, and see the measured times, in
[README.md → Which Whisper model?](README.md#which-whisper-model). On an RTX 5070 Laptop, `large-v3-turbo`
on the GPU took 20 s for a 16-minute video (`small` on the CPU: 84 s).

## 1. First-time setup (once)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -e ..\contracts\python

cd ..\pipeline
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -e ..\contracts\python -e .

cd ..\frontend
npm install
```

The database is created automatically the first time the backend starts.

The app only shows real files that you add. There is no mock mode and no demo data.
Never delete `data\dso.sqlite`: it holds everything you have processed.

## 2. Start the app (every time)

Terminal 1 – backend (API on port 8000):

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
```

Terminal 2 – frontend (UI on port 5173):

```powershell
cd frontend
npm run dev
```

Open http://localhost:5173. The top bar should say **LIVE API**. If it says "backend offline",
terminal 1 is not running. Check http://localhost:8000/health – it should return `"status":"ok"`.

If a command says the port is already in use, that server is already running.

## 3. Use it with real files

1. **Library** – upload a real MP4, PDF or PowerPoint `.pptx`. A 52-minute talk takes about 10 minutes on a laptop CPU.
   Slide images for `.pptx` are made with Microsoft PowerPoint (or LibreOffice if PowerPoint is missing).
2. **Recording** – click a sentence and the slide on screen at that time follows. Under it you can attach the
   meeting chat (`.msg` or `.txt`). Chat times are estimates (chat clock minus the start time in the file name, ±1 minute).
3. **Search** – searches spoken text, slide text, titles and file names.
4. **Duplicates** – exact copies (SHA-256), shared slides and similar slides.
5. **Storage report** – measured bytes, four scenarios. Scenario 0 is negative on purpose (processing adds files).
6. **Offboarding** – recommendations only; "Deletes performed: false".
7. **Export** – transcript `.txt`, unique slides as `.pptx` / `.pdf`, and JSON / JSONL for AI tools.

## Useful commands

```powershell
cd backend
.\.venv\Scripts\python.exe -m app.cli unique-slides <asset_id>   # merge near-duplicate frames (once per video)
.\.venv\Scripts\python.exe -m app.cli reindex-search             # rebuild the search index
```

Tip: if you see encoding errors in PowerShell, run `$env:PYTHONIOENCODING="utf-8"` first.
