import pathlib
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.templating import Jinja2Templates

from labserver_web.auth import ViewerContext, get_current_viewer
from labserver_web.clients.core import CoreClientError
from labserver_web.dependencies import CoreClientDep

router = APIRouter(tags=["dashboard"])

ViewerDep = Annotated[ViewerContext, Depends(get_current_viewer)]

TEMPLATES = Jinja2Templates(
    directory=str(pathlib.Path(__file__).resolve().parent.parent / "templates")
)


def _core_error_page(request: Request, error: CoreClientError) -> Any:
    return TEMPLATES.TemplateResponse(
        request,
        "schedule/error.html",
        {"request": request, "message": error.message},
        status_code=503 if error.status_code >= 500 else error.status_code,
    )


@router.get("/")
@router.get("/dashboard")
def view_dashboard(
    request: Request,
    core: CoreClientDep,
    viewer: ViewerDep,
) -> Any:
    token = request.cookies.get("labserver_session")
    cookies = {"labserver_session": token} if token else None

    try:
        dashboard = core.get_dashboard(cookies=cookies)
    except CoreClientError as error:
        return _core_error_page(request, error)

    return TEMPLATES.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "request": request,
            "viewer": viewer,
            "dashboard": dashboard,
            "cards": dashboard.cards,
            "active_tab": "dashboard",
        },
    )
