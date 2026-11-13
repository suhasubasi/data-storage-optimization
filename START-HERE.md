# Start here – run the app on Windows

This is a hackathon prototype, not an official Ericsson product.
Nothing is deleted: originals stay on disk, and offboarding only recommends.

## What you need

- Node.js 20 or newer
- Python 3.11 or 3.12 (not 3.13+)
- ffmpeg on your PATH (for video processing)

The first video you process downloads a local faster-whisper model. After that it works offline.

## 1. First-time setup (once)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -e ..\contracts\python

cd ..\pipeline
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -e ..\contracts\python -e .

cd ..\frontend
"VITE_USE_MOCKS=false" | Set-Content -NoNewline .env.local
npm install
```

The database is created automatically the first time the backend starts.

> **Warning:** do not run `app.cli load-fixtures --reset`. It wipes the database,
> including every file you have processed, and loads generated demo data instead.

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

1. **Library** – upload a real MP4 or PDF. A 52-minute talk takes about 10 minutes on a laptop CPU.
2. **Recording** – click a sentence and the slide on screen at that time follows.
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
