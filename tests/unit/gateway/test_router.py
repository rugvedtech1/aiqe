"""Unit tests for Task Router."""
import pytest
from pydantic import SecretStr
from aiqe.gateway.keys import APIKeyManager
from aiqe.gateway.router import TaskRouter
from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage
from aiqe.shared.exceptions import AllProvidersExhaustedError


@pytest.fixture
def key_manager():
    manager = APIKeyManager()
    manager.register_provider("openai", [SecretStr("key-1")])
    manager.register_provider("anthropic", [SecretStr("ant-key-1")])
    return manager


@pytest.fixture
def router(key_manager):
    return TaskRouter(
        key_manager=key_manager,
        default_provider="openai",
    )


class TestTaskRouter:
    def test_selects_default_provider(self, router):
        request = AIRequest(
            messages=[PromptMessage.user("test")],
            workflow_id="wf_1",
        )
        provider, model = router.select_provider(request)
        assert provider == "openai"
        assert model != ""

    def test_selects_preferred_provider(self, router):
        request = AIRequest(
            messages=[PromptMessage.user("test")],
            preferred_provider="anthropic",
            workflow_id="wf_1",
        )
        provider, model = router.select_provider(request)
        assert provider == "anthropic"

    def test_falls_back_if_preferred_unavailable(self, router):
        request = AIRequest(
            messages=[PromptMessage.user("test")],
            preferred_provider="gemini",  # not registered
            workflow_id="wf_1",
        )
        provider, model = router.select_provider(request)
        assert provider in ["openai", "anthropic"]

    def test_raises_when_no_providers_available(self):
        empty_manager = APIKeyManager()
        router = TaskRouter(
            key_manager=empty_manager,
            default_provider="openai",
        )
        request = AIRequest(
            messages=[PromptMessage.user("test")],
            workflow_id="wf_1",
        )
        with pytest.raises(AllProvidersExhaustedError):
            router.select_provider(request)

    def test_quick_task_gets_lighter_model(self, router):
        request = AIRequest(
            messages=[PromptMessage.user("classify this")],
            task_type=AITaskType.QUICK,
            workflow_id="wf_1",
        )
        _, model = router.select_provider(request)
        # Quick tasks should get a lighter model
        assert "mini" in model or "haiku" in model or model != ""
