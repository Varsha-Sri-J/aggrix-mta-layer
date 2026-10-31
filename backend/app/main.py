"""
AGGRIX MTA Layer - Main FastAPI Application
Multi-Tenant Analytics & Aggregation Engine
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.analytics.broadcaster import broadcaster
from app.api.routes.analytics import router as analytics_router, stream_analytics_events
from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.manager import router as manager_router
from app.api.routes.platform import router as platform_router
from app.core.config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan managing PostgreSQL event listener lifecycle."""
    try:
        broadcaster.start_postgres_listener()
    except Exception as exc:
        logger.warning("Could not initialize PostgreSQL LISTEN worker: %s", exc)
    yield
    try:
        broadcaster.stop_postgres_listener()
    except Exception:
        pass


def create_application() -> FastAPI:
    """
    Factory function to initialize and configure the FastAPI application.
    """
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        description=settings.DESCRIPTION,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Cross-Origin Resource Sharing (CORS) Middleware
    # Restrict strictly to explicit configured frontend origins; wildcard '*' is forbidden
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[str(origin).rstrip("/") for origin in settings.BACKEND_CORS_ORIGINS],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Register Health Check router directly at root (/health)
    app.include_router(health_router, tags=["Health"])

    # Also register Health Check under the API version prefix (/api/v1/health)
    app.include_router(health_router, prefix=settings.API_V1_STR, tags=["Health (v1)"])

    # Register Authentication routes under /api/v1/auth
    app.include_router(
        auth_router,
        prefix=f"{settings.API_V1_STR}/auth",
        tags=["Authentication"],
    )

    # Register Tenant Analytics Read API under /api/v1/analytics
    app.include_router(
        analytics_router,
        prefix=f"{settings.API_V1_STR}/analytics",
        tags=["Tenant Analytics"],
    )

    # Register Multi-Store Manager Analytics under /api/v1/analytics/manager
    app.include_router(
        manager_router,
        prefix=f"{settings.API_V1_STR}/analytics/manager",
        tags=["Manager Analytics"],
    )

    # Register Platform Admin Analytics under /api/v1/analytics/platform
    app.include_router(
        platform_router,
        prefix=f"{settings.API_V1_STR}/analytics/platform",
        tags=["Platform Admin Analytics"],
    )

    # Register SSE stream endpoint alias directly at /api/analytics/stream
    app.add_api_route(
        "/api/analytics/stream",
        stream_analytics_events,
        methods=["GET"],
        tags=["Tenant Analytics"],
        summary="Real-Time Analytics Event Stream (SSE Alias)",
        include_in_schema=True,
    )

    # Mount static assets directory
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get(
        "/dashboard",
        include_in_schema=False,
        summary="Live Analytics Dashboard Interface",
    )
    def render_dashboard() -> Any:
        """Serves the real-time analytics web dashboard."""
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path, media_type="text/html")
        return HTMLResponse(
            "<html><body><h1>AGGRIX Dashboard</h1><p>Static bundle initializing...</p></body></html>"
        )

    @app.get(
        "/",
        tags=["Root"],
        summary="Application Information",
        description="Returns basic system metadata, operating status, and API documentation location.",
    )
    def read_root() -> Dict[str, Any]:
        """
        Root endpoint providing engine identification and service status.
        """
        return {
            "name": settings.PROJECT_NAME,
            "version": settings.VERSION,
            "description": settings.DESCRIPTION,
            "environment": settings.ENVIRONMENT,
            "status": "running",
            "docs_url": "/docs",
            "dashboard_url": "/dashboard",
        }

    return app


app = create_application()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
