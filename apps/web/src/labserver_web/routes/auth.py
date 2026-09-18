import contextlib
import pathlib
from typing import Annotated

from fastapi import APIRouter, Form, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from labserver_web.clients.core import CoreClientError
from labserver_web.dependencies import CoreClientDep

router = APIRouter(tags=["auth"])

TEMPLATES = Jinja2Templates(
    directory=str(pathlib.Path(__file__).resolve().parent.parent / "templates")
)


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> Response:
    return TEMPLATES.TemplateResponse(
        request,
        "auth/login.html",
        {"error": None, "username": ""},
    )


@router.post("/login", response_class=HTMLResponse)
def login_submit(
    request: Request,
    core_client: CoreClientDep,
    username: Annotated[str, Form()],
    password: Annotated[str, Form()],
) -> Response:
    try:
        _, raw_token = core_client.login(username, password)
    except CoreClientError as exc:
        return TEMPLATES.TemplateResponse(
            request,
            "auth/login.html",
            {"error": exc.message, "username": username},
            status_code=exc.status_code,
        )

    redirect = RedirectResponse(url="/schedule", status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key="labserver_session",
        value=raw_token,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return redirect


@router.post("/logout")
def logout(request: Request, core_client: CoreClientDep) -> Response:
    token = request.cookies.get("labserver_session")
    if token:
        with contextlib.suppress(CoreClientError):
            core_client.logout(cookies={"labserver_session": token})

    redirect = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(key="labserver_session", path="/")
    return redirect
