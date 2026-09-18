"""Web service health check."""

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
