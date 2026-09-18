"""LabServer web application factory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from labserver_web.clients.core import CoreClient
from labserver_web.config import WebSettings, load_settings
from labserver_web.routes import auth, dashboard, health, schedule

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: WebSettings | None = None) -> FastAPI:
    application = FastAPI(title="LabServer Web")
    application.state.settings = settings or load_settings()
    application.state.core_client = CoreClient(application.state.settings.core_base_url)
    application.include_router(health.router)
    application.include_router(auth.router)
    application.include_router(dashboard.router)
    application.include_router(schedule.router)
    application.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    return application



app = create_app()
