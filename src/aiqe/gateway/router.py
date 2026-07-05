"""
AIQE Task Router.

Selects the best available AI provider and model for each
request based on task type, provider availability, and
configured preferences.

Routing rules (Phase 1 — simple availability-first routing):
    1. If preferred_provider is set and available, use it.
    2. Else use the configured default_provider.
    3. If default is unavailable, iterate through available providers.
    4. If no providers available, raise AllProvidersExhaustedError.

Phase 2 additions (after real usage data exists, ADR-005):
    - Cost-optimised routing (use cheaper models for QUICK tasks)
    - Latency-optimised routing (use fastest provider for browser tests)
    - Privacy routing (use local Ollama for sensitive enterprise code)
    - Load balancing across providers by token usage

Why a separate router instead of logic in the gateway?
    Routing logic is complex enough to warrant isolation.
    The router is testable independently (no AI calls needed).
    Phase 2 routing strategies can be added here without
    touching the gateway's completion flow.
"""

from __future__ import annotations

from typing import Any

from aiqe.gateway.keys import APIKeyManager
from aiqe.gateway.types import AIRequest, AITaskType
from aiqe.shared.exceptions import AllProvidersExhaustedError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

# Default model recommendations per provider
_PROVIDER_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o",
    "anthropic": "claude-sonnet-4-6",
    "gemini": "gemini-1.5-pro",
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "openai/gpt-4o",
    "azure": "gpt-4o",
    "ollama": "llama3",
}

# Task type to model preference mapping
# Lighter models for quick tasks, more capable for analysis/generation
_TASK_MODEL_OVERRIDES: dict[str, dict[str, str]] = {
    "openai": {
        AITaskType.QUICK: "gpt-4o-mini",
        AITaskType.EMBEDDING: "text-embedding-3-small",
    },
    "anthropic": {
        AITaskType.QUICK: "claude-haiku-4-5-20251001",
    },
}


class TaskRouter:
    """
    Routes AI requests to the appropriate provider.

    Args:
        key_manager: The API Key Manager for checking availability.
        default_provider: Provider to use when no preference is set.
        provider_priority: Ordered list of providers to try as fallback.
    """

    def __init__(
        self,
        key_manager: APIKeyManager,
        default_provider: str = "openai",
        provider_priority: list[str] | None = None,
    ) -> None:
        self._key_manager = key_manager
        self._default_provider = default_provider
        self._provider_priority = provider_priority or [
            "openai", "anthropic", "gemini", "groq",
            "openrouter", "azure", "ollama",
        ]

    def select_provider(self, request: AIRequest) -> tuple[str, str]:
        """
        Select the best available provider and model for a request.

        Args:
            request: The AI request to route.

        Returns:
            Tuple of (provider_name, model_name).

        Raises:
            AllProvidersExhaustedError: If no providers are available.
        """
        # Try preferred provider first
        if request.preferred_provider:
            if self._key_manager.has_provider(request.preferred_provider):
                model = self._select_model(
                    request.preferred_provider, request.task_type
                )
                logger.debug(
                    "router_selected_preferred_provider",
                    provider=request.preferred_provider,
                    model=model,
                    task_type=request.task_type,
                    workflow_id=request.workflow_id,
                )
                return request.preferred_provider, model
            else:
                logger.warning(
                    "preferred_provider_unavailable",
                    provider=request.preferred_provider,
                    workflow_id=request.workflow_id,
                )

        # Try default provider
        if self._key_manager.has_provider(self._default_provider):
            model = self._select_model(
                self._default_provider, request.task_type
            )
            logger.debug(
                "router_selected_default_provider",
                provider=self._default_provider,
                model=model,
                task_type=request.task_type,
                workflow_id=request.workflow_id,
            )
            return self._default_provider, model

        # Fallback: try providers in priority order
        available = self._key_manager.available_providers()
        for provider in self._provider_priority:
            if provider in available:
                model = self._select_model(provider, request.task_type)
                logger.info(
                    "router_fallback_provider",
                    provider=provider,
                    model=model,
                    task_type=request.task_type,
                    workflow_id=request.workflow_id,
                )
                return provider, model

        raise AllProvidersExhaustedError(
            f"No AI providers are available. "
            f"Configured providers: {self._key_manager.stats().keys()}. "
            f"Check API keys in .env file."
        )

    def _select_model(
        self, provider: str, task_type: AITaskType
    ) -> str:
        """
        Select the best model for a task type within a provider.

        Args:
            provider: The provider name.
            task_type: The type of task being requested.

        Returns:
            Model identifier string.
        """
        overrides = _TASK_MODEL_OVERRIDES.get(provider, {})
        if task_type in overrides:
            return overrides[task_type]
        return _PROVIDER_DEFAULT_MODELS.get(provider, "gpt-4o")

    def available_providers(self) -> list[str]:
        """Return list of currently available providers."""
        return self._key_manager.available_providers()
