"""
AIQE AI Gateway.

The universal interface for all AI provider interactions.
Agents never import provider SDKs directly — they use this gateway.

Public API:
    AIGateway        — the main gateway class
    AIRequest        — request type for completions
    AIResponse       — response type from completions
    AITaskType       — task type enum for routing
    PromptMessage    — message type for conversations
    EmbeddingRequest — request type for embeddings
    EmbeddingResponse— response type for embeddings
    get_gateway      — get the global singleton

Phase 1 (current):
    Provider Manager, API Key Manager, Retry Manager.

Phase 2 (after usage telemetry):
    Cost Optimizer, Prompt Cache, Token Budget Manager,
    Privacy Routing, Health Monitor.
"""

from aiqe.gateway.gateway import AIGateway, get_gateway
from aiqe.gateway.keys import APIKeyManager
from aiqe.gateway.retry import RetryConfig, RetryManager
from aiqe.gateway.router import TaskRouter
from aiqe.gateway.types import (
    AIRequest,
    AIResponse,
    AITaskType,
    EmbeddingRequest,
    EmbeddingResponse,
    GatewayStats,
    MessageRole,
    PromptMessage,
)

__all__ = [
    "AIGateway",
    "AIRequest",
    "AIResponse",
    "AITaskType",
    "APIKeyManager",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "GatewayStats",
    "MessageRole",
    "PromptMessage",
    "RetryConfig",
    "RetryManager",
    "TaskRouter",
    "get_gateway",
]
