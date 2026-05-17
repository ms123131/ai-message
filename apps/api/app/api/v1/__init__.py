from fastapi import APIRouter

from app.api.v1 import conversations, health, integrations, webhooks

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(integrations.router)
api_router.include_router(conversations.router)
api_router.include_router(webhooks.router)
