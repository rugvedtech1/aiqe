"""
AIQE AI Gateway Type Contracts.

All requests to and responses from the AI Gateway use these
typed dataclasses. Agents never construct raw provider API
calls — they construct AIRequest objects and receive AIResponse
objects. The gateway handles everything in between.

Design decisions:
    - AIRequest carries the model-agnostic parameters: messages,
      max_tokens, temperature, system prompt. The gateway maps
      these to whatever format each provider requires.
    - AIResponse carries the response text, token counts, provider
      used, and model used — so agents can log this for ADR-012.
    - PromptMessage is the universal message format. Provider
      adapters convert it to OpenAI/Anthropic/Gemini format.
    - EmbeddingRequest / EmbeddingResponse for the vector store.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MessageRole(str, Enum):
    """Message roles in a conversation."""
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


class AITaskType(str, Enum):
    """
    The type of AI task being requested.

    The Task Router uses this to select the most appropriate
    provider and model for the job. See ADR-005.

    Task types and their characteristics:
        ANALYSIS    — structured reasoning, needs accuracy > speed
        GENERATION  — code/test generation, needs quality + length
        EXPLANATION — explain findings, needs clarity
        STRATEGY    — planning and prioritisation, needs reasoning
        EMBEDDING   — vector embeddings, needs speed + volume
        QUICK       — short classification tasks, needs speed + low cost
    """
    ANALYSIS = "analysis"
    GENERATION = "generation"
    EXPLANATION = "explanation"
    STRATEGY = "strategy"
    EMBEDDING = "embedding"
    QUICK = "quick"


@dataclass(frozen=True)
class PromptMessage:
    """
    A single message in an AI conversation.

    Args:
        role: The role of the message sender.
        content: The message text content.
    """
    role: MessageRole
    content: str

    @classmethod
    def system(cls, content: str) -> PromptMessage:
        """Create a system message."""
        return cls(role=MessageRole.SYSTEM, content=content)

    @classmethod
    def user(cls, content: str) -> PromptMessage:
        """Create a user message."""
        return cls(role=MessageRole.USER, content=content)

    @classmethod
    def assistant(cls, content: str) -> PromptMessage:
        """Create an assistant message."""
        return cls(role=MessageRole.ASSISTANT, content=content)


@dataclass
class AIRequest:
    """
    A request to the AI Gateway.

    Agents construct this and pass it to gateway.complete().
    The gateway handles provider selection, key rotation,
    retry logic, and response normalisation.

    Attributes:
        messages: The conversation messages.
        task_type: What kind of task this is (for routing).
        max_tokens: Maximum tokens in the response.
        temperature: Sampling temperature (0.0 = deterministic).
        system_prompt: Optional system prompt (added as first message
                       if not already in messages list).
        workflow_id: For audit trail correlation (ADR-012).
        agent_name: Which agent is making this request.
        preferred_provider: Optional provider preference. Gateway
                            may override if provider is unavailable.
        prompt_version: Version of the prompt template used.
                        Tracked in audit log for reproducibility.
        metadata: Additional context for logging/auditing.
        stream: Whether to stream the response (not yet implemented).
    """
    messages: list[PromptMessage]
    task_type: AITaskType = AITaskType.ANALYSIS
    max_tokens: int = 4096
    temperature: float = 0.1
    system_prompt: str | None = None
    workflow_id: str = ""
    agent_name: str = ""
    preferred_provider: str | None = None
    prompt_version: str = "1.0"
    metadata: dict[str, Any] = field(default_factory=dict)
    stream: bool = False

    def __post_init__(self) -> None:
        """Add system prompt as first message if provided."""
        if self.system_prompt:
            sys_msg = PromptMessage.system(self.system_prompt)
            if not self.messages or self.messages[0].role != MessageRole.SYSTEM:
                self.messages = [sys_msg, *self.messages]

    @property
    def user_messages_only(self) -> list[PromptMessage]:
        """Return only non-system messages."""
        return [m for m in self.messages if m.role != MessageRole.SYSTEM]


@dataclass
class AIResponse:
    """
    A response from the AI Gateway.

    Contains the response text plus complete metadata for
    audit trail logging (ADR-012) and cost tracking.

    Attributes:
        content: The AI response text.
        provider: Which provider generated this response.
        model: Which model within the provider was used.
        prompt_tokens: Tokens consumed by the prompt.
        completion_tokens: Tokens in the response.
        total_tokens: Total tokens (prompt + completion).
        latency_seconds: Time from request to response.
        workflow_id: Workflow context for audit correlation.
        agent_name: Agent that made this request.
        prompt_version: Prompt template version used.
        key_index: Which key index was used (for rotation tracking).
        retry_count: How many retries were needed.
        metadata: Additional provider-specific metadata.
    """
    content: str
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_seconds: float = 0.0
    workflow_id: str = ""
    agent_name: str = ""
    prompt_version: str = "1.0"
    key_index: int = 0
    retry_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_audit_dict(self) -> dict[str, Any]:
        """
        Serialize to audit log format.

        Note: content is NOT included in the audit dict to avoid
        logging potentially large AI responses. The agent stores
        its processed output separately.
        """
        return {
            "provider": self.provider,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "latency_seconds": self.latency_seconds,
            "workflow_id": self.workflow_id,
            "agent_name": self.agent_name,
            "prompt_version": self.prompt_version,
            "key_index": self.key_index,
            "retry_count": self.retry_count,
        }


@dataclass
class EmbeddingRequest:
    """
    A request for vector embeddings.

    Args:
        texts: List of texts to embed.
        workflow_id: For audit correlation.
        agent_name: Requesting agent.
        model: Embedding model preference (provider may override).
    """
    texts: list[str]
    workflow_id: str = ""
    agent_name: str = ""
    model: str = ""


@dataclass
class EmbeddingResponse:
    """
    Vector embedding response.

    Attributes:
        embeddings: List of embedding vectors, one per input text.
        model: Model that generated the embeddings.
        provider: Provider that generated the embeddings.
        total_tokens: Total tokens processed.
    """
    embeddings: list[list[float]]
    model: str = ""
    provider: str = ""
    total_tokens: int = 0


@dataclass
class GatewayStats:
    """
    Runtime statistics for the AI Gateway.

    Used for monitoring, cost tracking, and Phase 2 optimisations.
    """
    total_requests: int = 0
    total_tokens: int = 0
    total_retries: int = 0
    total_errors: int = 0
    requests_by_provider: dict[str, int] = field(default_factory=dict)
    tokens_by_provider: dict[str, int] = field(default_factory=dict)
    errors_by_provider: dict[str, int] = field(default_factory=dict)
    average_latency_seconds: float = 0.0
