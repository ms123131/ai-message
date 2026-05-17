from fastapi import APIRouter

from app.api.v1 import health, integrations, webhooks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(integrations.router)
api_router.include_router(webhooks.router)
