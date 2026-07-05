"""Unit tests for AIGateway with mock providers."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from pydantic import SecretStr
from aiqe.gateway.gateway import AIGateway
from aiqe.gateway.keys import APIKeyManager
from aiqe.gateway.providers.base import BaseProviderAdapter
from aiqe.gateway.retry import RetryConfig, RetryManager
from aiqe.gateway.router import TaskRouter
from aiqe.gateway.types import (
    AIRequest,
    AIResponse,
    AITaskType,
    PromptMessage,
)
from aiqe.shared.exceptions import ProviderError


class MockAdapter(BaseProviderAdapter):
    """Mock provider adapter for testing."""

    def __init__(self, response_content: str = "mock response"):
        self._response = response_content
        self.call_count = 0

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def default_model(self) -> str:
        return "mock-model"

    async def complete(self, request, api_key):
        self.call_count += 1
        return AIResponse(
            content=self._response,
            provider="mock",
            model="mock-model",
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
            latency_seconds=0.1,
            workflow_id=request.workflow_id,
            agent_name=request.agent_name,
        )


class FailingAdapter(BaseProviderAdapter):
    """Mock adapter that always fails."""

    @property
    def provider_name(self) -> str:
        return "failing"

    @property
    def default_model(self) -> str:
        return "fail-model"

    async def complete(self, request, api_key):
        raise ProviderError("Always fails", provider="failing", status_code=500)


@pytest.fixture
def gateway_with_mock():
    key_manager = APIKeyManager()
    key_manager.register_provider("mock", [SecretStr("mock-key")])

    router = TaskRouter(
        key_manager=key_manager,
        default_provider="mock",
    )
    retry_manager = RetryManager(RetryConfig(
        max_attempts=3,
        base_delay_seconds=0.001,
    ))
    mock_adapter = MockAdapter("Test response from mock AI")

    gateway = AIGateway(
        key_manager=key_manager,
        router=router,
        retry_manager=retry_manager,
        adapters={"mock": mock_adapter},
    )
    return gateway, mock_adapter


class TestAIGateway:
    @pytest.mark.asyncio
    async def test_complete_returns_response(self, gateway_with_mock):
        gateway, adapter = gateway_with_mock
        request = AIRequest(
            messages=[PromptMessage.user("Analyse this code.")],
            workflow_id="wf_001",
            agent_name="test_strategy",
        )
        response = await gateway.complete(request)
        assert response.content == "Test response from mock AI"
        assert response.provider == "mock"
        assert response.total_tokens == 150

    @pytest.mark.asyncio
    async def test_stats_updated_after_completion(self, gateway_with_mock):
        gateway, adapter = gateway_with_mock
        request = AIRequest(
            messages=[PromptMessage.user("test")],
            workflow_id="wf_001",
            agent_name="test_agent",
        )
        await gateway.complete(request)
        assert gateway.stats.total_requests == 1
        assert gateway.stats.total_tokens == 150
        assert "mock" in gateway.stats.requests_by_provider

    @pytest.mark.asyncio
    async def test_adapter_called_once_on_success(self, gateway_with_mock):
        gateway, adapter = gateway_with_mock
        request = AIRequest(
            messages=[PromptMessage.user("test")],
            workflow_id="wf_001",
            agent_name="agent",
        )
        await gateway.complete(request)
        assert adapter.call_count == 1

    def test_available_providers(self, gateway_with_mock):
        gateway, _ = gateway_with_mock
        providers = gateway.available_providers()
        assert "mock" in providers
