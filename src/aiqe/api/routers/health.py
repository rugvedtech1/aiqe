"""
AIQE FastAPI — Health and Readiness Endpoints.

GET /health  — liveness probe (is the service alive?)
GET /ready   — readiness probe (is the service ready to serve?)
GET /        — root info endpoint

Kubernetes and Docker health checks use these endpoints.
GitHub Actions uses /ready to verify the API is up before
sending webhooks.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from aiqe.api.schemas import HealthCheckResponse, HealthStatus, ReadyResponse

router = APIRouter(tags=["health"])

# Server start time for uptime calculation
_START_TIME = time.monotonic()


@router.get(
    "/",
    summary="API root info",
    include_in_schema=True,
)
async def root() -> dict[str, Any]:
    """
    AIQE API root endpoint.

    Returns basic API information and links to documentation.
    """
    return {
        "name": "AIQE API",
        "description": "AI Quality Engineering Operating System",
        "version": "0.1.0-alpha",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
        "health": "/health",
        "ready": "/ready",
    }


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Liveness probe",
    description=(
        "Returns the health status of the AIQE service. "
        "Used by container orchestrators to determine if the "
        "service needs to be restarted."
    ),
)
async def health_check() -> HealthCheckResponse:
    """
    Liveness probe — is the service alive?

    Returns 200 if the service is running, regardless of whether
    all dependencies are available. A 500 here means the service
    should be restarted.
    """
    uptime = time.monotonic() - _START_TIME

    checks = {
        "api": "healthy",
        "event_loop": "healthy",
    }

    return HealthCheckResponse(
        status=HealthStatus.HEALTHY,
        version="0.1.0-alpha",
        checks=checks,
        uptime_seconds=round(uptime, 2),
    )


@router.get(
    "/ready",
    response_model=ReadyResponse,
    summary="Readiness probe",
    description=(
        "Returns whether the service is ready to accept traffic. "
        "Checks database connectivity, AI gateway availability, "
        "and other critical dependencies."
    ),
)
async def readiness_check() -> ReadyResponse:
    """
    Readiness probe — is the service ready to serve requests?

    Returns 200 if all critical dependencies are available.
    Returns 503 if the service is not yet ready (e.g. database
    is still initialising). Container orchestrators will not
    route traffic to the service until this returns 200.
    """
    checks: dict[str, bool] = {}

    # Check database
    try:
        from aiqe.persistence.factory import get_repository_bundle
        await get_repository_bundle()
        checks["database"] = True
    except Exception:
        checks["database"] = False

    # Check AI gateway (at least one provider available)
    try:
        from aiqe.gateway.gateway import get_gateway
        gateway = get_gateway()
        checks["ai_gateway"] = len(gateway.available_providers()) > 0
    except Exception:
        checks["ai_gateway"] = False

    # Check workflow engine
    try:
        from aiqe.workflow.engine import get_engine
        get_engine()
        checks["workflow_engine"] = True
    except Exception:
        checks["workflow_engine"] = False

    all_ready = all(checks.values())

    if not all_ready:
        return JSONResponse(
            status_code=503,
            content=ReadyResponse(
                ready=False,
                checks=checks,
            ).model_dump(),
        )

    return ReadyResponse(ready=True, checks=checks)
