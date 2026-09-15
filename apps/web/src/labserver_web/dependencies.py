from typing import Annotated

from fastapi import Depends, Request

from labserver_web.clients.core import CoreClient


def get_core_client(request: Request) -> CoreClient:
    client: CoreClient = request.app.state.core_client
    return client


CoreClientDep = Annotated[CoreClient, Depends(get_core_client)]
