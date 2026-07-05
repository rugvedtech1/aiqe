"""
AIQE Anthropic Provider Adapter.

Translates AIRequest to Anthropic Messages API calls and
normalises responses back to AIResponse.

Key difference from OpenAI:
    Anthropic separates system prompts from the messages list.
    The system prompt must be passed as a top-level field,
    not as a message with role="system".

Error mapping:
    429 → rate limit → mark key failed, retry
    401 → auth error → mark key failed permanently
    529 → overloaded → retry with backoff
    400 → bad request → do not retry
"""

from __future__ import annotations

import time

import httpx

from aiqe.gateway.providers.base import BaseProviderAdapter
from aiqe.gateway.types import AIRequest, AIResponse, MessageRole
from aiqe.shared.exceptions import GatewayError, ProviderError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"


class AnthropicAdapter(BaseProviderAdapter):
    """Anthropic Claude provider adapter."""

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def default_model(self) -> str:
        return "claude-sonnet-4-6"

    async def complete(
        self, request: AIRequest, api_key: str
    ) -> AIResponse:
        """Send a request to the Anthropic Messages API."""
        model = request.metadata.get("model", self.default_model)

        # Anthropic: extract system prompt, keep only user/assistant messages
        system_prompt = ""
        conversation_messages = []

        for msg in request.messages:
            if msg.role == MessageRole.SYSTEM:
                system_prompt = msg.content
            else:
                conversation_messages.append({
                    "role": msg.role.value,
                    "content": msg.content,
                })

        # Anthropic requires at least one user message
        if not conversation_messages:
            conversation_messages = [
                {"role": "user", "content": "Please proceed."}
            ]

        payload: dict = {
            "model": model,
            "max_tokens": request.max_tokens,
            "messages": conversation_messages,
        }

        if system_prompt:
            payload["system"] = system_prompt

        if request.temperature != 0.1:
            payload["temperature"] = request.temperature

        start = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    ANTHROPIC_MESSAGES_URL,
                    json=payload,
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": ANTHROPIC_API_VERSION,
                        "content-type": "application/json",
                    },
                )

            latency = time.monotonic() - start

            if response.status_code == 429:
                raise ProviderError(
                    "Anthropic rate limit exceeded",
                    provider="anthropic",
                    status_code=429,
                )

            if response.status_code == 401:
                raise ProviderError(
                    "Anthropic authentication failed — check API key",
                    provider="anthropic",
                    status_code=401,
                )

            if response.status_code == 529:
                raise ProviderError(
                    "Anthropic API overloaded",
                    provider="anthropic",
                    status_code=529,
                )

            if response.status_code >= 400:
                error_body = response.json()
                raise ProviderError(
                    f"Anthropic API error: "
                    f"{error_body.get('error', {}).get('message', 'unknown')}",
                    provider="anthropic",
                    status_code=response.status_code,
                )

            data = response.json()
            content = ""
            if data.get("content"):
                text_blocks = [
                    b["text"] for b in data["content"]
                    if b.get("type") == "text"
                ]
                content = "\n".join(text_blocks)

            usage = data.get("usage", {})

            logger.debug(
                "anthropic_completion_success",
                model=model,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                latency_seconds=latency,
                workflow_id=request.workflow_id,
            )

            return AIResponse(
                content=content,
                provider="anthropic",
                model=model,
                prompt_tokens=usage.get("input_tokens", 0),
                completion_tokens=usage.get("output_tokens", 0),
                total_tokens=(
                    usage.get("input_tokens", 0)
                    + usage.get("output_tokens", 0)
                ),
                latency_seconds=latency,
                workflow_id=request.workflow_id,
                agent_name=request.agent_name,
                prompt_version=request.prompt_version,
            )

        except ProviderError:
            raise
        except httpx.TimeoutException as e:
            raise ProviderError(
                f"Anthropic request timed out: {e}",
                provider="anthropic",
            ) from e
        except Exception as e:
            raise GatewayError(
                f"Unexpected error in Anthropic adapter: {e}"
            ) from e
