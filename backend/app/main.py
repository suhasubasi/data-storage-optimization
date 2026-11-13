"""FastAPI entrypoint — Stream 2 SKELETON.

Implement EXACTLY contracts/openapi.yaml using the generated models in dso_contracts.models.
Only /health exists now. No business logic yet.

TODO Stream 2 (from the design Page), in roadmap order:
  POST /api/assets  GET /api/assets  GET /api/assets/{id}  POST /api/assets/{id}/process  GET /api/jobs/{id}
  GET /api/assets/{id}/slides  GET /api/duplicates  GET /api/search  GET /api/assets/{id}/timeline
  GET /api/storage/report  GET /api/offboarding?owner=  GET /api/assets/{id}/export  GET /api/export.jsonl
  GET /files/originals/{asset_id}/{filename}  GET /files/derived/{asset_id}/{path}
Rules: no DELETE endpoint for originals; every non-2xx body is ErrorResponse; job progress never faked.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from dso_contracts.models import Health

from .settings import API_VERSION, CORS_ORIGINS

app = FastAPI(title="Ericsson DSO MVP API", version=API_VERSION)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", version=API_VERSION)
