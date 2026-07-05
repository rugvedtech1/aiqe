"""
AIQE FastAPI — AI Gateway Endpoints.

GET  /gateway/status    — gateway stats and provider availability
POST /gateway/test      — test AI provider connectivity
GET  /gateway/providers — list all configured providers
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from aiqe.api.dependencies import AIGatewayDep, AuthDep
from aiqe.api.schemas import (
    GatewayStatusResponse,
    GatewayTestRequest,
    GatewayTestResponse,
)

router = APIRouter(prefix="/gateway", tags=["gateway"])


@router.get(
    "/status",
    response_model=GatewayStatusResponse,
    summary="AI Gateway status",
    description="Returns AI Gateway availability and usage statistics.",
)
async def gateway_status(
    gateway: AIGatewayDep,
    auth: AuthDep,
) -> GatewayStatusResponse:
    """Get AI Gateway status and statistics."""
    stats = gateway.stats
    return GatewayStatusResponse(
        available_providers=gateway.available_providers(),
        total_requests=stats.total_requests,
        total_tokens=stats.total_tokens,
        total_errors=stats.total_errors,
        requests_by_provider=stats.requests_by_provider,
        tokens_by_provider=stats.tokens_by_provider,
    )


@router.post(
    "/test",
    response_model=GatewayTestResponse,
    summary="Test AI provider connectivity",
    description=(
        "Sends a test message to verify AI provider connectivity. "
        "Useful for validating API key configuration."
    ),
)
async def test_gateway(
    request: GatewayTestRequest,
    gateway: AIGatewayDep,
    auth: AuthDep,
) -> GatewayTestResponse:
    """Test AI Gateway connectivity."""
    from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage
    from aiqe.shared.exceptions import GatewayError, ProviderError

    ai_request = AIRequest(
        messages=[PromptMessage.user(request.message)],
        task_type=AITaskType.QUICK,
        max_tokens=request.max_tokens,
        preferred_provider=request.provider,
        workflow_id="api-test",
        agent_name="api-gateway-test",
        prompt_version="1.0",
    )

    try:
        response = await gateway.complete(ai_request)
        return GatewayTestResponse(
            success=True,
            provider=response.provider,
            model=response.model,
            response=response.content,
            total_tokens=response.total_tokens,
            latency_seconds=response.latency_seconds,
        )
    except (GatewayError, ProviderError) as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "gateway_unavailable",
                "message": str(e),
            },
        )


@router.get(
    "/providers",
    summary="List configured AI providers",
    description="Returns all configured AI providers and their key availability.",
)
async def list_providers(
    gateway: AIGatewayDep,
    auth: AuthDep,
) -> dict:
    """List all configured AI providers."""
    key_stats = gateway._key_manager.stats()

    providers = []
    for provider, stats in key_stats.items():
        providers.append({
            "provider": provider,
            "total_keys": stats.get("total_keys", 0),
            "available_keys": stats.get("available_keys", 0),
            "is_available": provider in gateway.available_providers(),
        })

    return {
        "providers": providers,
        "total": len(providers),
        "available_count": len(gateway.available_providers()),
    }
