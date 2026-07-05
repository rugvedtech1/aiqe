"""
AIQE FastAPI Dependencies.

Shared dependencies injected into route handlers via FastAPI's
dependency injection system.

Why dependency injection in FastAPI?
    Instead of importing singletons directly in route handlers,
    we declare dependencies. This makes routes testable by
    overriding dependencies with test doubles, without changing
    route code.

    Example override in tests:
        app.dependency_overrides[get_workflow_engine] = mock_engine

Available dependencies:
    get_workflow_engine   — WorkflowEngine singleton
    get_repository_bundle — RepositoryBundle singleton
    get_ai_gateway        — AIGateway singleton
    get_plugin_registry   — PluginRegistry singleton
    verify_api_key        — API key authentication (enterprise mode)
    get_correlation_id    — request correlation ID for audit logging
"""

from __future__ import annotations

from typing import Annotated, AsyncGenerator

from fastapi import Depends, Header, HTTPException, Request, status

from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


# ==================================================
# CORE INFRASTRUCTURE DEPENDENCIES
# ==================================================

async def get_workflow_engine():
    """Get the global WorkflowEngine singleton."""
    from aiqe.workflow.engine import get_engine
    return get_engine()


async def get_repository_bundle():
    """Get the global RepositoryBundle singleton."""
    from aiqe.persistence.factory import get_repository_bundle as _get
    return await _get()


async def get_ai_gateway():
    """Get the global AIGateway singleton."""
    from aiqe.gateway.gateway import get_gateway
    return get_gateway()


async def get_plugin_registry():
    """Get the global PluginRegistry singleton."""
    from aiqe.plugins.registry import get_plugin_registry as _get
    return _get()


# ==================================================
# CORRELATION ID
# Every request gets a unique ID for audit trail correlation.
# ==================================================

async def get_correlation_id(request: Request) -> str:
    """
    Extract or generate a correlation ID for this request.

    Checks X-Correlation-ID header first (passed by API gateways
    and upstream services). Generates a new UUID if not present.
    The correlation ID is attached to all log records for this request.
    """
    import uuid
    correlation_id = request.headers.get(
        "X-Correlation-ID",
        str(uuid.uuid4()),
    )
    return correlation_id


# ==================================================
# AUTHENTICATION
# Enterprise mode uses API key authentication.
# Local mode (AIQE_ENTERPRISE_MODE=false) skips auth.
# ==================================================

async def verify_api_key(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> str | None:
    """
    Verify the AIQE API key for enterprise mode.

    In local/development mode (AIQE_ENTERPRISE_MODE=false),
    authentication is skipped and None is returned.

    In enterprise mode, the X-API-Key header must be present
    and match the configured AIQE_API_KEY.

    Returns:
        The API key value if authenticated, None in local mode.

    Raises:
        HTTPException 401: If enterprise mode and key is invalid.
        HTTPException 403: If enterprise mode and key is missing.
    """
    from aiqe.shared.config import get_settings
    settings = get_settings()

    if not settings.core.enterprise_mode:
        return None

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "missing_api_key",
                "message": (
                    "X-API-Key header is required in enterprise mode. "
                    "Contact your AIQE administrator for an API key."
                ),
            },
        )

    # In a full enterprise implementation, this would check
    # a database of valid API keys. For v1 we use a single
    # configured key.
    configured_key = getattr(settings, "api_key", None)
    if configured_key and x_api_key != configured_key:
        logger.warning(
            "invalid_api_key_attempt",
            client_ip=request.client.host if request.client else "unknown",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": "invalid_api_key",
                "message": "The provided API key is invalid.",
            },
        )

    return x_api_key


# ==================================================
# PAGINATION
# ==================================================

async def get_pagination(
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """
    Standard pagination parameters.

    Args:
        page: Page number (1-indexed).
        page_size: Items per page (max 100).

    Returns:
        Dict with page, page_size, and offset.
    """
    if page < 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="page must be >= 1",
        )
    if page_size < 1 or page_size > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="page_size must be between 1 and 100",
        )
    return {
        "page": page,
        "page_size": page_size,
        "offset": (page - 1) * page_size,
    }


# Type aliases for cleaner route signatures
WorkflowEngineDep = Annotated[object, Depends(get_workflow_engine)]
RepositoryBundleDep = Annotated[object, Depends(get_repository_bundle)]
AIGatewayDep = Annotated[object, Depends(get_ai_gateway)]
PluginRegistryDep = Annotated[object, Depends(get_plugin_registry)]
CorrelationIDDep = Annotated[str, Depends(get_correlation_id)]
AuthDep = Annotated[str | None, Depends(verify_api_key)]
PaginationDep = Annotated[dict, Depends(get_pagination)]
