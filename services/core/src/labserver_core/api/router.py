from fastapi import APIRouter

from .routes import auth, health, monitoring, plans, servers, users

router = APIRouter()
router.include_router(health.router)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(users.router)
api_v1.include_router(servers.router)
api_v1.include_router(plans.router)
api_v1.include_router(monitoring.router)
router.include_router(api_v1)

