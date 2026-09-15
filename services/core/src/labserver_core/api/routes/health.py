from fastapi import APIRouter, Depends

from labserver_core.api.dependencies import require_database_ready

router = APIRouter(tags=["health"])


@router.get("/healthz", dependencies=[Depends(require_database_ready)])
def health() -> dict[str, str]:
    return {"status": "ok"}
