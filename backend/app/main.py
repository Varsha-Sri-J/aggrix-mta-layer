"""
AGGRIX MTA Layer - Main FastAPI Application
Multi-Tenant Analytics & Aggregation Engine
"""

from typing import Any, Dict
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.health import router as health_router
from app.core.config import settings


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
    )

    # Cross-Origin Resource Sharing (CORS) Middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register Health Check router directly at root (/health)
    app.include_router(health_router, tags=["Health"])

    # Also register Health Check under the API version prefix (/api/v1/health)
    app.include_router(health_router, prefix=settings.API_V1_STR, tags=["Health (v1)"])

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
        }

    return app


app = create_application()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
