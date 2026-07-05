"""
AIQE AI Gateway.

The single entry point for all AI interactions in AIQE.
Every agent that needs AI calls gateway.complete().

The gateway coordinates:
    1. Task Router — selects provider and model
    2. API Key Manager — retrieves the next available key
    3. Provider Adapter — makes the actual API call
    4. Retry Manager — retries on transient failures
    5. Audit logging — records every AI call (ADR-012)
    6. Stats tracking — accumulates usage metrics

What agents write:
    response = await gateway.complete(AIRequest(
        messages=[PromptMessage.user("Analyse this code...")],
        task_type=AITaskType.ANALYSIS,
        workflow_id=self.workflow_id,
        agent_name=self.NAME,
    ))
    print(response.content)    # The AI response
    print(response.total_tokens)  # Token usage

What agents never do:
    - Import any provider SDK (openai, anthropic, etc.)
    - Handle API keys directly
    - Implement retry logic
    - Know which provider ran

This implements ADR-005 Phase 1 (Provider Manager +
API Key Manager + Retry Manager).
"""

from __future__ import annotations

from typing import Any

from aiqe.gateway.keys import APIKeyManager
from aiqe.gateway.providers.anthropic_adapter import AnthropicAdapter
from aiqe.gateway.providers.base import BaseProviderAdapter
from aiqe.gateway.providers.ollama_adapter import OllamaAdapter
from aiqe.gateway.providers.openai_adapter import OpenAIAdapter
from aiqe.gateway.retry import RetryConfig, RetryManager
from aiqe.gateway.router import TaskRouter
from aiqe.gateway.types import (
    AIRequest,
    AIResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    GatewayStats,
)
from aiqe.shared.exceptions import AllProvidersExhaustedError, GatewayError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class AIGateway:
    """
    AIQE AI Gateway — the universal interface for AI calls.

    One AIGateway instance exists per AIQE process.
    All agents share the same gateway, key pools, and stats.

    Args:
        key_manager: Manages API key rotation per provider.
        router: Selects provider/model per request.
        retry_manager: Handles retries and backoff.
        adapters: Provider-specific API call implementations.
    """

    def __init__(
        self,
        key_manager: APIKeyManager,
        router: TaskRouter,
        retry_manager: RetryManager,
        adapters: dict[str, BaseProviderAdapter] | None = None,
    ) -> None:
        self._key_manager = key_manager
        self._router = router
        self._retry_manager = retry_manager
        self._adapters = adapters or self._default_adapters()
        self._stats = GatewayStats()

    async def complete(self, request: AIRequest) -> AIResponse:
        """
        Send a completion request to the best available AI provider.

        This is the primary method agents call. It handles all
        routing, key rotation, retry, and audit logging automatically.

        Args:
            request: The AI completion request.

        Returns:
            AIResponse with content and full metadata.

        Raises:
            AllProvidersExhaustedError: If no providers are available
                                        after all retries.
            GatewayError: For unexpected gateway-level failures.
        """
        logger.info(
            "gateway_completion_requested",
            task_type=request.task_type,
            agent_name=request.agent_name,
            workflow_id=request.workflow_id,
            message_count=len(request.messages),
            max_tokens=request.max_tokens,
        )

        self._stats.total_requests += 1

        async def _attempt() -> AIResponse:
            # Select provider and model for this request
            provider_name, model = self._router.select_provider(request)

            # Inject model into request metadata for the adapter
            request.metadata["model"] = model

            # Get API key for this provider
            api_key, key_index = await self._key_manager.get_key(
                provider_name
            )

            # Get the provider adapter
            adapter = self._adapters.get(provider_name)
            if adapter is None:
                raise GatewayError(
                    f"No adapter registered for provider '{provider_name}'. "
                    f"Registered adapters: {list(self._adapters.keys())}"
                )

            try:
                response = await adapter.complete(request, api_key)
                response.key_index = key_index

                # Track stats
                self._stats.total_tokens += response.total_tokens
                self._stats.requests_by_provider[provider_name] = (
                    self._stats.requests_by_provider.get(provider_name, 0) + 1
                )
                self._stats.tokens_by_provider[provider_name] = (
                    self._stats.tokens_by_provider.get(provider_name, 0)
                    + response.total_tokens
                )

                logger.info(
                    "gateway_completion_success",
                    provider=provider_name,
                    model=model,
                    total_tokens=response.total_tokens,
                    latency_seconds=response.latency_seconds,
                    workflow_id=request.workflow_id,
                    agent_name=request.agent_name,
                    key_index=key_index,
                )

                return response

            except Exception as e:
                from aiqe.shared.exceptions import ProviderError
                if isinstance(e, ProviderError):
                    # Mark the key as failed so rotation skips it
                    error_type = (
                        "rate_limit" if e.status_code == 429
                        else "auth_error" if e.status_code == 401
                        else "server_error"
                    )
                    await self._key_manager.mark_key_failed(
                        provider_name, key_index, error_type
                    )
                    self._stats.errors_by_provider[provider_name] = (
                        self._stats.errors_by_provider.get(provider_name, 0) + 1
                    )
                self._stats.total_errors += 1
                raise

        response = await self._retry_manager.execute_with_retry(
            operation=_attempt,
            operation_name=f"complete/{request.agent_name}",
            workflow_id=request.workflow_id,
        )

        response.retry_count = self._stats.total_retries
        return response

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """
        Generate vector embeddings for a list of texts.

        Args:
            request: The embedding request.

        Returns:
            EmbeddingResponse with embedding vectors.
        """
        # For embeddings, prefer OpenAI (best embedding quality)
        # Fall back to any available provider with embedding support
        embedding_providers = ["openai"]

        for provider_name in embedding_providers:
            if not self._key_manager.has_provider(provider_name):
                continue

            adapter = self._adapters.get(provider_name)
            if adapter is None:
                continue

            api_key, _ = await self._key_manager.get_key(provider_name)

            try:
                return await adapter.embed(request, api_key)
            except NotImplementedError:
                continue
            except Exception as e:
                logger.warning(
                    "embedding_provider_failed",
                    provider=provider_name,
                    error=str(e),
                )
                continue

        raise GatewayError(
            "No provider available that supports embeddings. "
            "Configure OPENAI_API_KEY_1 for embedding support."
        )

    @property
    def stats(self) -> GatewayStats:
        """Current gateway usage statistics."""
        return self._stats

    def available_providers(self) -> list[str]:
        """List of currently available AI providers."""
        return self._router.available_providers()

    @staticmethod
    def _default_adapters() -> dict[str, BaseProviderAdapter]:
        """Build the default set of provider adapters."""
        return {
            "openai": OpenAIAdapter(),
            "anthropic": AnthropicAdapter(),
            "ollama": OllamaAdapter(),
        }

    @classmethod
    def from_settings(cls) -> AIGateway:
        """
        Create an AIGateway instance from AIQE configuration.

        Reads provider keys from settings, initialises all components,
        and returns a ready-to-use gateway.

        Returns:
            Configured AIGateway singleton.
        """
        from aiqe.shared.config import get_settings

        settings = get_settings()
        key_manager = APIKeyManager.from_settings()

        router = TaskRouter(
            key_manager=key_manager,
            default_provider=settings.gateway.default_provider.value,
        )

        retry_config = RetryConfig(
            max_attempts=3,
            base_delay_seconds=1.0,
            max_delay_seconds=60.0,
        )
        retry_manager = RetryManager(config=retry_config)

        gateway = cls(
            key_manager=key_manager,
            router=router,
            retry_manager=retry_manager,
        )

        logger.info(
            "ai_gateway_initialized",
            available_providers=gateway.available_providers(),
            default_provider=settings.gateway.default_provider.value,
        )

        return gateway


# Module-level singleton
_gateway: AIGateway | None = None


def get_gateway() -> AIGateway:
    """
    Get the global AIGateway singleton.

    Initializes from settings on first call.
    All agents share this singleton instance.

    Returns:
        The global AIGateway.
    """
    global _gateway
    if _gateway is None:
        _gateway = AIGateway.from_settings()
    return _gateway
