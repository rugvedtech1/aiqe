"""
AIQE Provider Adapter Base Class.

Every AI provider (OpenAI, Anthropic, Gemini, etc.) implements
this interface. The gateway calls complete() and never knows
which provider it is talking to.

Why adapters instead of direct provider SDK calls?
    Provider SDKs change their APIs, parameter names, and error
    types independently. If agents called provider SDKs directly:
    - Changing from OpenAI to Anthropic requires changing every agent
    - Rate limit handling differs per provider and leaks into agents
    - Token counting differs per provider

    The adapter pattern isolates all provider-specific behaviour
    in one class per provider. Changing providers = swapping one
    adapter. Agents are untouched.
"""

from __future__ import annotations

import abc
from typing import Any

from aiqe.gateway.types import AIRequest, AIResponse, EmbeddingRequest, EmbeddingResponse


class BaseProviderAdapter(abc.ABC):
    """
    Abstract base for all AI provider adapters.

    Each provider subclass translates between AIQE's universal
    AIRequest/AIResponse format and the provider's specific API.
    """

    @property
    @abc.abstractmethod
    def provider_name(self) -> str:
        """The provider identifier (e.g. 'openai', 'anthropic')."""

    @property
    @abc.abstractmethod
    def default_model(self) -> str:
        """Default model to use if none specified in the request."""

    @abc.abstractmethod
    async def complete(
        self,
        request: AIRequest,
        api_key: str,
    ) -> AIResponse:
        """
        Send a completion request to this provider.

        Args:
            request: The AIQE-format AI request.
            api_key: The decrypted API key to use for this call.

        Returns:
            Normalised AIResponse.

        Raises:
            ProviderError: For API errors (rate limits, auth, etc.)
            GatewayError: For unexpected errors.
        """

    async def embed(
        self,
        request: EmbeddingRequest,
        api_key: str,
    ) -> EmbeddingResponse:
        """
        Generate embeddings for a list of texts.

        Default implementation raises NotImplementedError.
        Providers that support embeddings override this method.

        Args:
            request: The embedding request.
            api_key: The API key to use.

        Returns:
            EmbeddingResponse with embedding vectors.
        """
        raise NotImplementedError(
            f"Provider '{self.provider_name}' does not support embeddings."
        )

    def _messages_to_provider_format(
        self, request: AIRequest
    ) -> list[dict[str, str]]:
        """
        Convert PromptMessages to the standard OpenAI message format.

        Most providers (OpenAI, Groq, OpenRouter, Ollama) use the same
        message format. Providers with different formats override this.

        Args:
            request: The AI request containing messages.

        Returns:
            List of message dicts in OpenAI format.
        """
        return [
            {"role": msg.role.value, "content": msg.content}
            for msg in request.messages
        ]
