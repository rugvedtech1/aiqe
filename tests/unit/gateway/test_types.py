"""Unit tests for gateway type contracts."""
import pytest
from aiqe.gateway.types import (
    AIRequest,
    AIResponse,
    AITaskType,
    EmbeddingRequest,
    MessageRole,
    PromptMessage,
)


class TestPromptMessage:
    def test_system_factory(self):
        msg = PromptMessage.system("You are a QA agent.")
        assert msg.role == MessageRole.SYSTEM
        assert msg.content == "You are a QA agent."

    def test_user_factory(self):
        msg = PromptMessage.user("Analyse this code.")
        assert msg.role == MessageRole.USER

    def test_assistant_factory(self):
        msg = PromptMessage.assistant("Here is my analysis.")
        assert msg.role == MessageRole.ASSISTANT

    def test_immutable(self):
        msg = PromptMessage.user("test")
        with pytest.raises((AttributeError, TypeError)):
            msg.content = "changed"  # type: ignore


class TestAIRequest:
    def test_basic_construction(self):
        request = AIRequest(
            messages=[PromptMessage.user("Hello")],
            workflow_id="wf_001",
            agent_name="test_strategy",
        )
        assert len(request.messages) == 1
        assert request.task_type == AITaskType.ANALYSIS
        assert request.max_tokens == 4096
        assert request.temperature == 0.1

    def test_system_prompt_prepended(self):
        request = AIRequest(
            messages=[PromptMessage.user("Analyse this.")],
            system_prompt="You are an expert QA engineer.",
        )
        assert request.messages[0].role == MessageRole.SYSTEM
        assert request.messages[0].content == "You are an expert QA engineer."
        assert len(request.messages) == 2

    def test_system_prompt_not_duplicated_if_already_set(self):
        request = AIRequest(
            messages=[
                PromptMessage.system("Existing system"),
                PromptMessage.user("Hello"),
            ],
            system_prompt="New system",
        )
        # Should not prepend because first message is already SYSTEM
        system_msgs = [
            m for m in request.messages if m.role == MessageRole.SYSTEM
        ]
        assert len(system_msgs) == 1

    def test_user_messages_only(self):
        request = AIRequest(
            messages=[
                PromptMessage.system("System"),
                PromptMessage.user("User message"),
                PromptMessage.assistant("Response"),
            ],
        )
        user_only = request.user_messages_only
        assert all(m.role != MessageRole.SYSTEM for m in user_only)
        assert len(user_only) == 2


class TestAIResponse:
    def test_to_audit_dict_excludes_content(self):
        response = AIResponse(
            content="This is a long AI response...",
            provider="openai",
            model="gpt-4o",
            total_tokens=500,
            workflow_id="wf_001",
        )
        audit = response.to_audit_dict()
        assert "content" not in audit
        assert audit["provider"] == "openai"
        assert audit["total_tokens"] == 500
