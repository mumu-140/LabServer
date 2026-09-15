from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from labserver_core.domain.errors import (
    CapacityExceeded,
    DomainError,
    DomainValidationError,
    Forbidden,
    InvalidTransition,
    NotFound,
    ServerDisabled,
)


def _body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def _domain_status(error: DomainError) -> int:
    if isinstance(error, Forbidden):
        return status.HTTP_403_FORBIDDEN
    if isinstance(error, NotFound):
        return status.HTTP_404_NOT_FOUND
    if isinstance(error, (InvalidTransition, ServerDisabled, CapacityExceeded)):
        return status.HTTP_409_CONFLICT
    if isinstance(error, DomainValidationError):
        return status.HTTP_422_UNPROCESSABLE_CONTENT
    return status.HTTP_400_BAD_REQUEST


def _http_code(status_code: int) -> str:
    return {
        status.HTTP_401_UNAUTHORIZED: "unauthorized",
        status.HTTP_403_FORBIDDEN: "forbidden",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
        status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
    }.get(status_code, "http_error")


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=_domain_status(exc),
            content=_body(exc.code, exc.message),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else None
        message = str(first.get("msg")) if first else "Request validation failed"
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            content=_body("validation_error", message),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else "HTTP request failed"
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(_http_code(exc.status_code), message),
            headers=exc.headers,
        )
