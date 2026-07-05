"""
AIQE FastAPI Application Factory.

Creates and configures the FastAPI application instance.
Uses a factory function (not a module-level singleton) so
the app can be created multiple times in tests with
different configurations.

Why a factory instead of a module-level app?
    Module-level app instances are shared across test files.
    A factory lets each test create a fresh app with overridden
    dependencies, clean state, and isolated middleware.

    Production code imports get_app() once. Test code calls
    create_app() directly.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from aiqe.api.middleware import (
    CorrelationIDMiddleware,
    RequestLoggingMiddleware,
    SecurityHeadersMiddleware,
)
from aiqe.api.routers import (
    gateway,
    health,
    plugins,
    reports,
    webhooks,
    workflows,
)
from aiqe.shared.config import get_settings
from aiqe.shared.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI lifespan context manager.

    Handles startup and shutdown:
        Startup:
            - Configure structured logging
            - Initialise database (create tables if needed)
            - Register all agents
            - Log server ready message

        Shutdown:
            - Graceful cleanup
            - Close database connections
    """
    settings = get_settings()
    configure_logging(
        log_level=settings.core.log_level.value,
        json_output=settings.core.env.value == "production",
    )

    logger.info(
        "aiqe_api_starting",
        version="0.1.0-alpha",
        environment=settings.core.env.value,
        database_mode=settings.database.mode.value,
        enterprise_mode=settings.core.enterprise_mode,
    )

    # Initialise database
    try:
        from aiqe.persistence.factory import get_repository_bundle
        await get_repository_bundle()
        logger.info("database_initialized")
    except Exception as e:
        logger.error("database_init_failed", error=str(e))

    # Register all agents
    try:
        from aiqe.agents.registry_setup import register_all_agents
        register_all_agents()
        logger.info("agents_registered")
    except Exception as e:
        logger.error("agent_registration_failed", error=str(e))

    logger.info("aiqe_api_ready")

    yield  # Server is running

    # Shutdown
    logger.info("aiqe_api_shutting_down")

    try:
        from aiqe.persistence.implementations.sqlite.connection import (
            dispose_engine,
        )
        await dispose_engine()
        logger.info("database_connections_closed")
    except Exception:
        pass

    logger.info("aiqe_api_stopped")


def create_app() -> FastAPI:
    """
    Create and configure the AIQE FastAPI application.

    Returns:
        Configured FastAPI application instance.
    """
    settings = get_settings()

    app = FastAPI(
        title="AIQE API",
        description=(
            "AI Quality Engineering Operating System — REST API.\n\n"
            "Provides endpoints for managing quality workflows, "
            "inspecting bugs, generating reports, and configuring "
            "plugins and AI providers.\n\n"
            "**Human review is always required before merging. "
            "AIQE never auto-modifies production code (ADR-009).**"
        ),
        version="0.1.0-alpha",
        contact={
            "name": "AIQE Contributors",
            "url": "https://github.com/rugvedtech1/aiqe",
        },
        license_info={
            "name": "Apache 2.0",
            "url": "https://www.apache.org/licenses/LICENSE-2.0",
        },
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # ==================================================
    # MIDDLEWARE (applied in reverse order)
    # ==================================================

    # 1. Security headers (outermost — applied last to responses)
    app.add_middleware(SecurityHeadersMiddleware)

    # 2. Request logging
    app.add_middleware(RequestLoggingMiddleware)

    # 3. Correlation ID injection
    app.add_middleware(CorrelationIDMiddleware)

    # 4. CORS (configure allowed origins from settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict in production
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # ==================================================
    # ROUTERS
    # ==================================================

    app.include_router(health.router)
    app.include_router(workflows.router, prefix="/api/v1")
    app.include_router(reports.router, prefix="/api/v1")
    app.include_router(plugins.router, prefix="/api/v1")
    app.include_router(gateway.router, prefix="/api/v1")
    app.include_router(webhooks.router, prefix="/api/v1")

    # ==================================================
    # GLOBAL EXCEPTION HANDLERS
    # ==================================================

    @app.exception_handler(Exception)
    async def global_exception_handler(request, exc: Exception):
        logger.error(
            "unhandled_exception",
            path=request.url.path,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "internal_server_error",
                "message": (
                    "An unexpected error occurred. "
                    "Check server logs for details."
                ),
            },
        )

    from aiqe.shared.exceptions import AIQEError

    @app.exception_handler(AIQEError)
    async def aiqe_exception_handler(request, exc: AIQEError):
        logger.error(
            "aiqe_exception",
            path=request.url.path,
            error_type=type(exc).__name__,
            error=exc.message,
            workflow_id=exc.workflow_id,
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": type(exc).__name__,
                "message": exc.message,
                "workflow_id": exc.workflow_id,
            },
        )

    return app


# Module-level app singleton for uvicorn
_app: FastAPI | None = None


def get_app() -> FastAPI:
    """
    Get the global FastAPI application singleton.

    Called by uvicorn: uvicorn aiqe.api.app:get_app --factory
    """
    global _app
    if _app is None:
        _app = create_app()
    return _app
