"""LabServer web application factory."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from labserver_web.clients.core import CoreClient
from labserver_web.config import WebSettings, load_settings
from labserver_web.routes import auth, dashboard, health, running, schedule

STATIC_DIR = Path(__file__).resolve().parent / "static"
TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
TEMPLATES = Jinja2Templates(directory=str(TEMPLATES_DIR))


def create_app(settings: WebSettings | None = None) -> FastAPI:
    application = FastAPI(title="LabServer Web")
    application.state.settings = settings or load_settings()
    application.state.core_client = CoreClient(application.state.settings.core_base_url)

    @application.exception_handler(HTTPException)
    async def custom_http_exception_handler(request: Request, exc: HTTPException) -> Response:
        if exc.status_code == 401:
            accept = request.headers.get("accept", "")
            if "application/json" in accept and "text/html" not in accept:
                return JSONResponse({"detail": exc.detail}, status_code=401)
            return TEMPLATES.TemplateResponse(
                request,
                "auth/login.html",
                {
                    "error": None if exc.detail == "Authentication required" else exc.detail,
                    "username": "",
                },
                status_code=401,
            )
        return await http_exception_handler(request, exc)

    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(dashboard.router)
    application.include_router(running.router)
    application.include_router(schedule.router)
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return application


app = create_app()
