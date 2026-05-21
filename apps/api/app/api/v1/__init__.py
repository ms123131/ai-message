from fastapi import APIRouter

from app.api.v1 import (
    auth,
    conversations,
    dashboard,
    health,
    install,
    integrations,
    sla_targets,
    system,
    webhooks,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(integrations.router)
api_router.include_router(conversations.router)
api_router.include_router(dashboard.router)
api_router.include_router(sla_targets.router)
api_router.include_router(webhooks.router)
api_router.include_router(install.router)
api_router.include_router(system.router)
