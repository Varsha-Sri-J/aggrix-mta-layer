"""
API route definitions.
"""
from app.api.routes.analytics import router as analytics_router
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.ingest import router as ingest_router
from app.api.routes.manager import router as manager_router
from app.api.routes.platform import router as platform_router

__all__ = [
    "health_router",
    "analytics_router",
    "auth_router",
    "ingest_router",
    "manager_router",
    "platform_router",
]

