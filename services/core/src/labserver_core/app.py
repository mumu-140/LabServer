from fastapi import FastAPI

from labserver_core.adapters.monitoring import (
    BeszelAdapter,
    FakeHostMetricsProvider,
    HostMetricsProvider,
)
from labserver_core.api.errors import install_exception_handlers
from labserver_core.api.router import router
from labserver_core.application.auth_service import AuthService
from labserver_core.application.passwords import Argon2PasswordHasher
from labserver_core.application.ports import UnitOfWork
from labserver_core.application.runtime_store import RuntimeStore
from labserver_core.config import Settings
from labserver_core.persistence.database import create_engine_and_session_factory
from labserver_core.persistence.unit_of_work import SqlAlchemyUnitOfWork


def create_app(
    settings: Settings | None = None,
    metrics_provider: HostMetricsProvider | None = None,
    runtime_store: RuntimeStore | None = None,
) -> FastAPI:
    resolved = settings or Settings.from_environment()
    engine, session_factory = create_engine_and_session_factory(resolved.database_url)

    def uow_factory() -> UnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    hasher = Argon2PasswordHasher()
    auth_service = AuthService(uow_factory, hasher, resolved)

    if metrics_provider is not None:
        provider = metrics_provider
    elif resolved.beszel_enabled and resolved.beszel_hub_url:
        provider = BeszelAdapter(
            hub_url=resolved.beszel_hub_url,
            public_url=resolved.beszel_public_url,
            username=resolved.beszel_username,
            password=resolved.beszel_password,
            token=resolved.beszel_token,
            timeout_seconds=resolved.beszel_timeout_seconds,
            cache_ttl_seconds=resolved.beszel_cache_ttl_seconds,
            freshness_threshold_seconds=resolved.beszel_freshness_threshold_seconds,
            key_map=resolved.beszel_key_map,
        )
    else:
        provider = FakeHostMetricsProvider()

    app = FastAPI(title="LabServer Core", version="0.1.0")
    app.state.settings = resolved
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.uow_factory = uow_factory
    app.state.hasher = hasher
    app.state.auth_service = auth_service
    app.state.metrics_provider = provider
    app.state.runtime_store = runtime_store or RuntimeStore()
    install_exception_handlers(app)
    app.include_router(router)
    return app



app = create_app()
