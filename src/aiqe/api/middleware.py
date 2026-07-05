"""
AIQE FastAPI Middleware.

Middleware processes every request before it reaches a route
handler and every response before it leaves the application.

Middleware stack (applied in reverse order — last added = first run):
    1. SecurityHeadersMiddleware — adds security response headers
    2. CorrelationIDMiddleware   — injects X-Correlation-ID
    3. RequestLoggingMiddleware  — structured request/response logging

Why middleware instead of route decorators?
    Middleware applies to EVERY request automatically.
    Route decorators require opting in per route, which is
    fragile — someone forgets to add it and a route is unprotected.
    Security headers, correlation IDs, and audit logging must
    be universal, not optional.
"""

from __future__ import annotations

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Injects a correlation ID into every request and response.

    Checks for X-Correlation-ID in the request headers.
    Generates a new UUID if not present.
    Adds the correlation ID to the response headers.

    Why: The correlation ID allows tracing a single request
    across multiple log entries, services, and audit trail
    entries. Essential for debugging and ADR-012.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = request.headers.get(
            "X-Correlation-ID", str(uuid.uuid4())
        )

        # Store in request state for route handlers to access
        request.state.correlation_id = correlation_id

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Structured logging for every HTTP request and response.

    Logs:
    - Method, path, client IP
    - Status code
    - Request duration
    - Correlation ID

    Excludes:
    - /health and /ready endpoints (too noisy in production)
    - Request/response bodies (may contain sensitive data)
    """

    EXCLUDED_PATHS = frozenset({"/health", "/ready", "/favicon.ico"})

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.url.path in self.EXCLUDED_PATHS:
            return await call_next(request)

        start_time = time.monotonic()
        correlation_id = getattr(
            request.state, "correlation_id", "unknown"
        )

        logger.info(
            "http_request_started",
            method=request.method,
            path=request.url.path,
            client_ip=(
                request.client.host if request.client else "unknown"
            ),
            correlation_id=correlation_id,
        )

        try:
            response = await call_next(request)
            duration = time.monotonic() - start_time

            logger.info(
                "http_request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_seconds=round(duration, 4),
                correlation_id=correlation_id,
            )

            response.headers["X-Request-Duration"] = str(
                round(duration * 1000, 2)
            )
            return response

        except Exception as e:
            duration = time.monotonic() - start_time
            logger.error(
                "http_request_error",
                method=request.method,
                path=request.url.path,
                error_type=type(e).__name__,
                error=str(e),
                duration_seconds=round(duration, 4),
                correlation_id=correlation_id,
            )
            raise


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security-focused HTTP response headers to every response.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Referrer-Policy: strict-origin-when-cross-origin
    - Content-Security-Policy: restrictive policy
    - Strict-Transport-Security: HTTPS enforcement

    Why: Defence in depth. Even if AIQE is accidentally exposed
    to a browser, these headers reduce XSS and clickjacking risk.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = (
            "strict-origin-when-cross-origin"
        )
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'none'; "
            "object-src 'none';"
        )
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

        return response
