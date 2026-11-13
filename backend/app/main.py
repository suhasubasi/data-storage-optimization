"""FastAPI entrypoint — Stream 2. Implements contracts/openapi.yaml (frozen v1.0) with the generated
models in dso_contracts.models.

Rules: there is NO DELETE endpoint and no code path deletes or modifies originals; every non-2xx
body is ErrorResponse; job progress is never faked; no cloud AI (everything is local).
"""
from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, Path as PathParam, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response, StreamingResponse

from dso_contracts.models import (
    Asset, AssetDetail, AssetList, DuplicateReport, DuplicateType, ExportAsset, Health, Job,
    OffboardingReview, SearchResponse, SlideList, SourceSystem, StorageReport, Timeline,
)

from . import db, errors, exports, ingest, jobs, services, settings, uploads
from .errors import not_found

logging.basicConfig(level=os.environ.get("DSO_LOG_LEVEL", "INFO"))

ASSET_ID = r"^a_[A-Za-z0-9]+$"
AssetIdParam = Annotated[str, PathParam(pattern=ASSET_ID)]


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    jobs.fail_stale_jobs()
    jobs.clean_stale_staging()
    ingest.reindex_asset_metadata()  # idempotent: title / file name / metadata rows in search (REC v1.1)
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
def get_storage_report(include_test_data: bool = False) -> StorageReport:
    return services.storage_report(include_test_data)


@app.get("/api/offboarding", response_model=OffboardingReview)
def get_offboarding(owner: Annotated[str, Query(min_length=1)]) -> OffboardingReview:
    return services.offboarding(owner)


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


@app.get("/api/assets/{asset_id}/export", response_model=ExportAsset,
         responses={200: {"content": {"application/json": {}, "text/plain": {}}}})
def export_asset(asset_id: AssetIdParam, format: Literal["json", "txt"] = "json"):  # noqa: A002 (query name)
    if format == "txt":  # never silently answer JSON when plain text was asked for
        return transcript_txt(asset_id)
    return services.export_asset(asset_id)


@app.get("/api/assets/{asset_id}/transcript.txt", response_class=PlainTextResponse,
         responses={200: {"content": {"text/plain": {}}}})
def transcript_txt(asset_id: AssetIdParam, timestamps: bool = True) -> PlainTextResponse:
    name, text = exports.transcript_text(asset_id, timestamps)
    return PlainTextResponse(text, media_type="text/plain; charset=utf-8", headers=_attachment(name))


PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@app.get("/api/assets/{asset_id}/slides.pptx", response_class=Response, responses={200: {"content": {PPTX_MIME: {}}}})
def slides_pptx(asset_id: AssetIdParam) -> Response:
    name, data = exports.slides_pptx(asset_id)
    return Response(data, media_type=PPTX_MIME, headers=_attachment(name))


@app.get("/api/assets/{asset_id}/slides.pdf", response_class=Response,
         responses={200: {"content": {"application/pdf": {}}}})
def slides_pdf(asset_id: AssetIdParam) -> Response:
    name, data = exports.slides_pdf(asset_id)
    return Response(data, media_type="application/pdf", headers=_attachment(name))


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
        raise not_found(f"The original file for {asset_id} is not on this machine.")
    return FileResponse(path, filename=filename, content_disposition_type="inline")


@app.get("/files/derived/{asset_id}/{path:path}")
def get_derived_file(asset_id: str, path: str) -> FileResponse:
    if not re.fullmatch(ASSET_ID, asset_id):  # never serve job staging / trash folders
        raise not_found(f"Derived file {asset_id}/{path} was not found.")
    base = settings.DERIVED_DIR / asset_id
    target = base / path
    if not _inside(base, target) or not target.is_file():
        raise not_found(f"Derived file {asset_id}/{path} was not found.")
    return FileResponse(target, content_disposition_type="inline")
