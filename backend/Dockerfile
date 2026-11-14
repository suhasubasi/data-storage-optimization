# Backend + Pipeline runtime container (CPU by default; pass TORCH_INDEX_URL for CUDA)
FROM python:3.12-slim-bookworm

ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cpu

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DSO_DATA_DIR=/app/data \
    DSO_DB_PATH=/app/data/dso.sqlite \
    DSO_PIPELINE_PYTHON=/opt/venv-pipeline/bin/python \
    DSO_PIPELINE_CWD=/app/pipeline \
    DSO_CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:8000,http://127.0.0.1:8000 \
    HF_HOME=/root/.cache/huggingface

# System deps: ffmpeg (media + diarization), libsndfile1 (soundfile), LibreOffice + fonts (.pptx slide rendering)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    libglib2.0-0 \
    libreoffice-impress \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy shared contracts & dependency manifests first for layer caching
COPY contracts/python /app/contracts/python
COPY contracts/schemas /app/contracts/schemas
COPY contracts/openapi.yaml /app/contracts/openapi.yaml
COPY contracts/schema.sql /app/contracts/schema.sql
COPY contracts/thresholds.json /app/contracts/thresholds.json
COPY contracts/CONTRACTS.md /app/contracts/CONTRACTS.md
COPY backend/requirements.txt /app/backend/requirements.txt
COPY pipeline/requirements.txt /app/pipeline/requirements.txt
COPY pipeline/pyproject.toml /app/pipeline/pyproject.toml

# 1) Lightweight backend virtualenv (FastAPI, SQLite FTS5, export/chat/duplicate engines)
RUN python -m venv /opt/venv-backend \
    && /opt/venv-backend/bin/pip install --no-cache-dir --upgrade pip setuptools \
    && /opt/venv-backend/bin/pip install --no-cache-dir \
       -e /app/contracts/python \
       -r /app/backend/requirements.txt

# 2) Isolated pipeline virtualenv (ffmpeg bindings, faster-whisper, Silero VAD, SpeechBrain, PyMuPDF)
RUN python -m venv /opt/venv-pipeline \
    && /opt/venv-pipeline/bin/pip install --no-cache-dir --upgrade pip setuptools \
    && /opt/venv-pipeline/bin/pip install --no-cache-dir \
       --index-url "${TORCH_INDEX_URL}" \
       --extra-index-url https://pypi.org/simple \
       "torch>=2.7.1" "torchaudio>=2.7.1" \
    && /opt/venv-pipeline/bin/pip install --no-cache-dir \
       -r /app/pipeline/requirements.txt \
       -e /app/contracts/python

# Copy application source (and contract fixtures for in-container pytest)
COPY contracts/fixtures /app/contracts/fixtures
COPY backend /app/backend
COPY pipeline /app/pipeline

RUN /opt/venv-pipeline/bin/pip install --no-cache-dir --no-deps --no-build-isolation -e /app/pipeline \
    && mkdir -p /app/data /root/.cache/huggingface

WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=5s --start-period=15s --retries=6 \
    CMD /opt/venv-backend/bin/python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["/opt/venv-backend/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
