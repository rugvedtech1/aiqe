"""
AIQE Ollama Provider Adapter.

Enables local AI model usage through Ollama.
No API key required — Ollama runs locally.

Why Ollama support matters:
    Enterprise users with air-gapped environments or strict data
    privacy requirements cannot send code to external AI providers.
    Ollama allows AIQE to run completely offline with local models
    (Llama 3, Mistral, CodeLlama, etc.).

    This directly supports the Privacy Routing feature planned
    for the AI Gateway Phase 2 (ADR-005).
"""

from __future__ import annotations

import time

import httpx

from aiqe.gateway.providers.base import BaseProviderAdapter
from aiqe.gateway.types import AIRequest, AIResponse
from aiqe.shared.config import get_settings
from aiqe.shared.exceptions import GatewayError, ProviderError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class OllamaAdapter(BaseProviderAdapter):
    """Ollama local model provider adapter."""

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def default_model(self) -> str:
        return "llama3"

    def _get_base_url(self) -> str:
        settings = get_settings()
        return settings.gateway.ollama_base_url.rstrip("/")

    async def complete(
        self, request: AIRequest, api_key: str
    ) -> AIResponse:
        """Send a completion request to local Ollama instance."""
        model = request.metadata.get("model", self.default_model)
        base_url = self._get_base_url()

        # Ollama uses OpenAI-compatible /v1/chat/completions
        messages = self._messages_to_provider_format(request)
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    f"{base_url}/api/chat",
                    json=payload,
                )

            latency = time.monotonic() - start

            if response.status_code != 200:
                raise ProviderError(
                    f"Ollama error: {response.status_code} — "
                    f"is Ollama running at {base_url}?",
                    provider="ollama",
                    status_code=response.status_code,
                )

            data = response.json()
            content = data.get("message", {}).get("content", "")

            return AIResponse(
                content=content,
                provider="ollama",
                model=model,
                latency_seconds=latency,
                workflow_id=request.workflow_id,
                agent_name=request.agent_name,
                prompt_version=request.prompt_version,
            )

        except ProviderError:
            raise
        except httpx.ConnectError as e:
            raise ProviderError(
                f"Cannot connect to Ollama at {base_url}. "
                f"Is Ollama running? Start with: ollama serve",
                provider="ollama",
            ) from e
        except Exception as e:
            raise GatewayError(
                f"Unexpected error in Ollama adapter: {e}"
            ) from e
