from fastapi import APIRouter

from .routes import health, plans, requests, reservations, servers, users

router = APIRouter()
router.include_router(health.router)

api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(users.router)
api_v1.include_router(servers.router)
api_v1.include_router(plans.router)
api_v1.include_router(requests.router)
api_v1.include_router(reservations.router)
router.include_router(api_v1)
