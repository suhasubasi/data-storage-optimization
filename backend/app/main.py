"""FastAPI entrypoint — Stream 2. Implements contracts/openapi.yaml (frozen v1.0) with the generated
models in dso_contracts.models.

Rules: there is NO DELETE endpoint and no code path deletes or modifies originals; every non-2xx
body is ErrorResponse; job progress is never faked; no cloud AI (everything is local).
"""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, Path as PathParam, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse

from dso_contracts.models import (
    Asset, AssetDetail, AssetList, DuplicateReport, DuplicateType, ExportAsset, Health, Job,
    OffboardingReview, SearchResponse, SlideList, SourceSystem, StorageReport, Timeline,
)

from . import db, errors, jobs, services, settings, uploads
from .errors import not_found

logging.basicConfig(level=os.environ.get("DSO_LOG_LEVEL", "INFO"))

ASSET_ID = r"^a_[A-Za-z0-9]+$"
AssetIdParam = Annotated[str, PathParam(pattern=ASSET_ID)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    jobs.fail_stale_jobs()
    yield


app = FastAPI(title="Ericsson DSO MVP API", version=settings.API_VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_methods=["GET", "POST"],
                   allow_headers=["*"], expose_headers=["Content-Range", "Accept-Ranges", "Content-Length"])
errors.install(app)


@app.get("/health", response_model=Health)
def health() -> Health:
    return Health(status="ok", version=settings.API_VERSION)


# ---------------------------------------------------------------------------------------------
# assets
# ---------------------------------------------------------------------------------------------
@app.post("/api/assets", response_model=Asset, status_code=201)
def upload_asset(
    file: Annotated[UploadFile, File()],
    source_system: Annotated[SourceSystem, Form()],
    owner: Annotated[str, Form(min_length=1)],
) -> Asset:
    asset_id = uploads.save_original(file.file, file.filename, source_system.value, owner)
    return services.get_asset(asset_id)


@app.get("/api/assets", response_model=AssetList)
def list_assets(owner: str | None = None) -> AssetList:
    return AssetList(assets=services.list_assets(owner))


@app.get("/api/assets/{asset_id}", response_model=AssetDetail)
def get_asset(asset_id: AssetIdParam) -> AssetDetail:
    return services.asset_detail(asset_id)


@app.post("/api/assets/{asset_id}/process", response_model=Job, status_code=202)
def process_asset(asset_id: AssetIdParam) -> Job:
    return jobs.start_job(asset_id)


@app.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    return jobs.get_job(job_id)


@app.get("/api/assets/{asset_id}/timeline", response_model=Timeline)
def get_timeline(asset_id: AssetIdParam) -> Timeline:
    return services.timeline(asset_id)


@app.get("/api/assets/{asset_id}/slides", response_model=SlideList)
def get_slides(asset_id: AssetIdParam) -> SlideList:
    return services.slide_list(asset_id)


# ---------------------------------------------------------------------------------------------
# search, duplicates, storage, offboarding, export
# ---------------------------------------------------------------------------------------------
@app.get("/api/search", response_model=SearchResponse)
def search(q: Annotated[str, Query(min_length=1)], limit: Annotated[int, Query(ge=1, le=100)] = 20) -> SearchResponse:
    return services.search(q, limit)


@app.get("/api/duplicates", response_model=DuplicateReport)
def get_duplicates(type: DuplicateType | None = None) -> DuplicateReport:  # noqa: A002 (contract name)
    return services.duplicate_report(type.value if type else None)


@app.get("/api/storage/report", response_model=StorageReport)
def get_storage_report() -> StorageReport:
    return services.storage_report()


@app.get("/api/offboarding", response_model=OffboardingReview)
def get_offboarding(owner: Annotated[str, Query(min_length=1)]) -> OffboardingReview:
    return services.offboarding(owner)


@app.get("/api/assets/{asset_id}/export", response_model=ExportAsset)
def export_asset(asset_id: AssetIdParam) -> ExportAsset:
    return services.export_asset(asset_id)


@app.get("/api/export.jsonl", response_class=StreamingResponse,
         responses={200: {"content": {"application/x-ndjson": {}}}})
def export_jsonl() -> StreamingResponse:
    return StreamingResponse(services.export_jsonl(), media_type="application/x-ndjson",
                             headers={"Content-Disposition": 'attachment; filename="dso-export.jsonl"'})


# ---------------------------------------------------------------------------------------------
# files (read-only). FileResponse supports HTTP Range (206) for video seeking.
# ---------------------------------------------------------------------------------------------
def _inside(base: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


@app.get("/files/originals/{asset_id}/{filename}")
def get_original_file(asset_id: str, filename: str) -> FileResponse:
    with db.read() as conn:
        row = conn.execute("SELECT filename, original_path FROM assets WHERE id = ?", (asset_id,)).fetchone()
    if row is None or row["filename"] != filename:
        raise not_found(f"Original {asset_id}/{filename} was not found.")
    path = settings.DATA_DIR / row["original_path"]
    if not path.is_file() or not _inside(settings.ORIGINALS_DIR, path):
        raise not_found(f"The original file for {asset_id} is not on this machine (demo data has no real file).")
    return FileResponse(path, filename=filename, content_disposition_type="inline")


@app.get("/files/derived/{asset_id}/{path:path}")
def get_derived_file(asset_id: str, path: str) -> FileResponse:
    base = settings.DERIVED_DIR / asset_id
    target = base / path
    if not _inside(base, target) or not target.is_file():
        raise not_found(f"Derived file {asset_id}/{path} was not found.")
    return FileResponse(target, content_disposition_type="inline")
