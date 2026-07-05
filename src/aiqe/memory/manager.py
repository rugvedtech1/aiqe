"""
AIQE Memory Manager.

Manages MemoryStore instances across workflow contexts.
The MemoryManager is the single access point for memory in AIQE.
Agents never construct MemoryStore directly — they go through
the manager.

Isolation guarantee (ADR-006):
    Each workflow has exactly one MemoryStore.
    The manager enforces that workflow A cannot access
    workflow B's store, even if both are active simultaneously.

Read-only access for Memory & Learning Agent:
    The manager provides a special read_only_access() method
    that returns a read-only view of a completed workflow's memory.
    This is the ONLY approved way for the Memory & Learning Agent
    to access historical workflow data.
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiqe.memory.store import MemoryStore
from aiqe.shared.exceptions import WorkflowContextError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class MemoryManager:
    """
    Manages memory stores for all active workflow contexts.

    One MemoryManager instance exists per AIQE process.
    It creates, provides, and destroys MemoryStores as workflows
    start and finish.

    Thread safety:
        asyncio.Lock protects the store registry dict.
        Individual MemoryStore operations have their own locks.
    """

    def __init__(self) -> None:
        self._stores: dict[str, MemoryStore] = {}
        self._lock = asyncio.Lock()

    async def create(self, workflow_id: str) -> MemoryStore:
        """
        Create a new MemoryStore for a workflow.

        Called by the Workflow Engine when creating a new context.

        Args:
            workflow_id: The unique ID of the new workflow.

        Returns:
            A fresh empty MemoryStore.

        Raises:
            WorkflowContextError: If a store already exists for this ID.
        """
        async with self._lock:
            if workflow_id in self._stores:
                msg = (
                    f"MemoryStore for workflow {workflow_id} already exists. "
                    f"Each workflow must have exactly one store."
                )
                raise WorkflowContextError(msg, workflow_id=workflow_id)

            store = MemoryStore(workflow_id=workflow_id)
            self._stores[workflow_id] = store

            logger.debug(
                "memory_store_created",
                workflow_id=workflow_id,
                active_stores=len(self._stores),
            )
            return store

    def get(self, workflow_id: str) -> MemoryStore:
        """
        Get the active MemoryStore for a workflow.

        Args:
            workflow_id: The workflow whose store to retrieve.

        Returns:
            The active MemoryStore.

        Raises:
            WorkflowContextError: If no store exists for this workflow.
        """
        store = self._stores.get(workflow_id)
        if store is None:
            msg = (
                f"No MemoryStore found for workflow {workflow_id}. "
                f"Was the workflow context created properly?"
            )
            raise WorkflowContextError(msg, workflow_id=workflow_id)
        return store

    def read_only_access(self, workflow_id: str) -> MemoryStore:
        """
        Get a read-only view of a workflow's memory.

        This is the ONLY approved way for the Memory & Learning Agent
        to access historical workflow data. See ADR-006.

        Args:
            workflow_id: The workflow to read from.

        Returns:
            A read-only MemoryStore view.

        Raises:
            WorkflowContextError: If no store exists.
        """
        store = self.get(workflow_id)
        return store.as_read_only()

    async def destroy(self, workflow_id: str) -> None:
        """
        Destroy a workflow's MemoryStore after the workflow completes.

        Called by the Workflow Engine during context cleanup.
        The memory is cleared and the store reference is removed.

        Args:
            workflow_id: The workflow whose store to destroy.
        """
        async with self._lock:
            store = self._stores.pop(workflow_id, None)
            if store:
                await store.clear()
                logger.debug(
                    "memory_store_destroyed",
                    workflow_id=workflow_id,
                    active_stores=len(self._stores),
                )

    @property
    def active_workflow_count(self) -> int:
        """Number of active workflow memory stores."""
        return len(self._stores)

    async def stats(self) -> dict[str, Any]:
        """Memory statistics across all active workflows."""
        return {
            "active_workflows": len(self._stores),
            "stores": {
                wf_id: store.stats
                for wf_id, store in self._stores.items()
            },
        }


# Module-level singleton
_memory_manager: MemoryManager | None = None


def get_memory_manager() -> MemoryManager:
    """Get the global MemoryManager singleton."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager
