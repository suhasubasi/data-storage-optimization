"""Contract error model (CONTRACTS.md §8): every non-2xx body is
{"error": {"code": ErrorCode, "message": "simple English", "details": {...}|null}}."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from dso_contracts.models import Error, ErrorCode, ErrorResponse

log = logging.getLogger("dso.errors")

STATUS_FOR = {
    ErrorCode.not_found: 404,
    ErrorCode.validation_error: 422,
    ErrorCode.unsupported_file_type: 415,
    ErrorCode.conflict: 409,
    ErrorCode.pipeline_failed: 500,
    ErrorCode.internal_error: 500,
}


class ApiError(Exception):
    def __init__(self, code: ErrorCode, message: str, details: dict[str, Any] | None = None, status: int | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.status = status or STATUS_FOR[code]


def not_found(message: str) -> ApiError:
    return ApiError(ErrorCode.not_found, message)


def error_response(status: int, code: ErrorCode, message: str, details: dict[str, Any] | None = None) -> JSONResponse:
    body = ErrorResponse(error=Error(code=code, message=message, details=details))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


def _jsonable_errors(errors: list[dict]) -> list[dict]:
    out = []
    for e in errors:
        out.append({"loc": [str(x) for x in e.get("loc", [])], "msg": str(e.get("msg", "")), "type": str(e.get("type", ""))})
    return out


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return error_response(exc.status, exc.code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errs = _jsonable_errors(exc.errors())
        fields = ", ".join(".".join(e["loc"][1:]) or e["loc"][0] for e in errs if e["loc"]) or "request"
        return error_response(422, ErrorCode.validation_error, f"Some input is missing or not valid: {fields}.",
                              {"errors": errs})

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        if exc.status_code == 404:
            return error_response(404, ErrorCode.not_found, "Nothing was found at this address.")
        if exc.status_code == 405:
            return error_response(405, ErrorCode.validation_error, "This method is not allowed here.")
        code = ErrorCode.internal_error if exc.status_code >= 500 else ErrorCode.validation_error
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        log.exception("unhandled error")
        return error_response(500, ErrorCode.internal_error, "Something went wrong on the server.",
                              {"type": type(exc).__name__})
