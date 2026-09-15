from fastapi import HTTPException, status

from labserver_core.application.actors import CurrentActor


def get_current_actor() -> CurrentActor:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication adapter is not configured",
    )
