"""
AIQE OpenAI Provider Adapter.

Translates AIRequest to OpenAI API calls and normalises
the response back to AIResponse.

Supports:
    - Chat completions (GPT-4o, GPT-4o-mini, GPT-4-turbo, etc.)
    - Text embeddings (text-embedding-3-small, text-embedding-3-large)

Error mapping:
    429 → rate limit → mark key failed, retry with next key
    401 → auth error → mark key failed permanently (bad key)
    500+ → server error → retry with backoff
    400 → bad request → do not retry (prompt issue)
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from aiqe.gateway.providers.base import BaseProviderAdapter
from aiqe.gateway.types import (
    AIRequest,
    AIResponse,
    EmbeddingRequest,
    EmbeddingResponse,
)
from aiqe.shared.exceptions import GatewayError, ProviderError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

OPENAI_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"


class OpenAIAdapter(BaseProviderAdapter):
    """OpenAI provider adapter."""

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def default_model(self) -> str:
        return "gpt-4o"

    async def complete(
        self, request: AIRequest, api_key: str
    ) -> AIResponse:
        """Send a chat completion request to OpenAI."""
        model = request.metadata.get("model", self.default_model)
        messages = self._messages_to_provider_format(request)

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }

        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    OPENAI_COMPLETIONS_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )

            latency = time.monotonic() - start

            if response.status_code == 429:
                raise ProviderError(
                    "OpenAI rate limit exceeded",
                    provider="openai",
                    status_code=429,
                    context={"retry_after": response.headers.get("retry-after")},
                )

            if response.status_code == 401:
                raise ProviderError(
                    "OpenAI authentication failed — check API key",
                    provider="openai",
                    status_code=401,
                )

            if response.status_code >= 500:
                raise ProviderError(
                    f"OpenAI server error: {response.status_code}",
                    provider="openai",
                    status_code=response.status_code,
                )

            if response.status_code >= 400:
                error_body = response.json()
                raise ProviderError(
                    f"OpenAI request error: "
                    f"{error_body.get('error', {}).get('message', 'unknown')}",
                    provider="openai",
                    status_code=response.status_code,
                )

            data = response.json()
            content = (
                data["choices"][0]["message"]["content"]
                if data.get("choices") else ""
            )
            usage = data.get("usage", {})

            logger.debug(
                "openai_completion_success",
                model=model,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                latency_seconds=latency,
                workflow_id=request.workflow_id,
            )

            return AIResponse(
                content=content,
                provider="openai",
                model=model,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                latency_seconds=latency,
                workflow_id=request.workflow_id,
                agent_name=request.agent_name,
                prompt_version=request.prompt_version,
            )

        except ProviderError:
            raise
        except httpx.TimeoutException as e:
            raise ProviderError(
                f"OpenAI request timed out: {e}",
                provider="openai",
            ) from e
        except httpx.RequestError as e:
            raise ProviderError(
                f"OpenAI network error: {e}",
                provider="openai",
            ) from e
        except Exception as e:
            raise GatewayError(
                f"Unexpected error in OpenAI adapter: {e}"
            ) from e

    async def embed(
        self, request: EmbeddingRequest, api_key: str
    ) -> EmbeddingResponse:
        """Generate embeddings using OpenAI's embedding API."""
        model = request.model or "text-embedding-3-small"

        payload = {
            "model": model,
            "input": request.texts,
        }

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    OPENAI_EMBEDDINGS_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                )

            if response.status_code != 200:
                raise ProviderError(
                    f"OpenAI embedding error: {response.status_code}",
                    provider="openai",
                    status_code=response.status_code,
                )

            data = response.json()
            embeddings = [item["embedding"] for item in data["data"]]
            usage = data.get("usage", {})

            return EmbeddingResponse(
                embeddings=embeddings,
                model=model,
                provider="openai",
                total_tokens=usage.get("total_tokens", 0),
            )

        except ProviderError:
            raise
        except Exception as e:
            raise GatewayError(
                f"Unexpected error in OpenAI embedding: {e}"
            ) from e
