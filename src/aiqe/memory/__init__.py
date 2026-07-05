"""
AIQE Shared Memory package.

Provides per-workflow isolated key-value memory stores for
inter-agent communication. Each workflow gets its own store.
No workflow can access another's memory (ADR-006).

Public API:
    MemoryStore     — async key-value store for one workflow
    MemoryManager   — manages stores across all active workflows
    MemoryKeys      — typed constants for all memory keys
    get_memory_manager — get the global singleton
"""

from aiqe.memory.manager import MemoryManager, get_memory_manager
from aiqe.memory.schema import MemoryKey, MemoryKeys
from aiqe.memory.store import MemoryStore

__all__ = [
    "MemoryKey",
    "MemoryKeys",
    "MemoryManager",
    "MemoryStore",
    "get_memory_manager",
]
