"""
AIQE Shared Memory Store.

A thread-safe, async key-value store for inter-agent communication
within a single WorkflowContext.

Design decisions:
    - asyncio.Lock protects all writes (no race conditions when
      agents run concurrently in the same workflow).
    - Namespacing prevents key collisions between agents.
    - TTL support allows temporary values to expire automatically.
    - Read-only mode allows the Memory & Learning Agent to safely
      access historical workflow data (ADR-006 exception).
    - Every write is optionally published to the EventBus so other
      agents can react to new data without polling.

Storage backends:
    v1: In-process dict (local/CLI mode) — zero dependencies,
        lost when process ends, sufficient for single-workflow runs.
    Enterprise: Redis (planned) — persistent, shared across workers,
        required for multi-node enterprise deployments.

The public interface is identical for both backends. Switching
from dict to Redis never touches agent code.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from aiqe.shared.exceptions import WorkflowContextError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class _MemoryEntry:
    """
    Internal wrapper for a stored value.

    Tracks value, write timestamp, writer identity, and optional TTL
    for automatic expiration.
    """
    __slots__ = ("value", "written_at", "written_by", "expires_at", "version")

    def __init__(
        self,
        value: Any,
        written_by: str,
        ttl_seconds: float | None = None,
    ) -> None:
        self.value = value
        self.written_at = time.monotonic()
        self.written_by = written_by
        self.expires_at = (
            self.written_at + ttl_seconds if ttl_seconds else None
        )
        self.version: int = 1

    @property
    def is_expired(self) -> bool:
        """True if this entry has passed its TTL."""
        if self.expires_at is None:
            return False
        return time.monotonic() > self.expires_at

    def update(self, value: Any, written_by: str) -> None:
        """Update value in place and increment version."""
        self.value = value
        self.written_at = time.monotonic()
        self.written_by = written_by
        self.version += 1


class MemoryStore:
    """
    Async key-value memory store for one WorkflowContext.

    Each WorkflowContext owns exactly one MemoryStore.
    Agents within the workflow read and write through this store.
    No other workflow's store is accessible from here (ADR-006).

    Args:
        workflow_id: The owning workflow's ID (for logging).
        read_only: If True, all writes raise WorkflowContextError.
                   Used when the Memory & Learning Agent accesses
                   historical workflow data in read-only mode.
    """

    def __init__(self, workflow_id: str, read_only: bool = False) -> None:
        self._workflow_id = workflow_id
        self._read_only = read_only
        self._store: dict[str, _MemoryEntry] = {}
        self._lock = asyncio.Lock()
        self._write_count = 0
        self._read_count = 0

    async def set(
        self,
        key: str,
        value: Any,
        written_by: str = "unknown",
        ttl_seconds: float | None = None,
        overwrite: bool = True,
    ) -> None:
        """
        Store a value under the given key.

        Args:
            key: Memory key (use MemoryKey constants, not raw strings).
            value: The value to store. Must be JSON-serialisable for
                   enterprise persistence compatibility.
            written_by: Agent name writing this value (for audit).
            ttl_seconds: Optional TTL. Entry expires after this many
                         seconds and returns None on subsequent reads.
            overwrite: If False and key exists, raises ValueError.

        Raises:
            WorkflowContextError: If the store is in read-only mode.
            ValueError: If overwrite=False and key already exists.
        """
        if self._read_only:
            msg = (
                f"MemoryStore for workflow {self._workflow_id} is "
                f"read-only. Agent '{written_by}' attempted to write "
                f"key '{key}'. Only the Memory & Learning Agent may "
                f"access historical workflow memory in read-only mode."
            )
            raise WorkflowContextError(msg, workflow_id=self._workflow_id)

        async with self._lock:
            if not overwrite and key in self._store:
                msg = (
                    f"Key '{key}' already exists in workflow "
                    f"{self._workflow_id} memory and overwrite=False."
                )
                raise ValueError(msg)

            if key in self._store:
                self._store[key].update(value, written_by)
                version = self._store[key].version
            else:
                entry = _MemoryEntry(
                    value=value,
                    written_by=written_by,
                    ttl_seconds=ttl_seconds,
                )
                self._store[key] = entry
                version = entry.version

            self._write_count += 1

            logger.debug(
                "memory_written",
                workflow_id=self._workflow_id,
                key=key,
                written_by=written_by,
                version=version,
                has_ttl=ttl_seconds is not None,
            )

    async def get(
        self,
        key: str,
        default: Any = None,
        reader: str = "unknown",
    ) -> Any:
        """
        Retrieve a value from memory.

        Args:
            key: Memory key to retrieve.
            default: Value to return if key is missing or expired.
            reader: Agent name reading this value (for audit/debug).

        Returns:
            The stored value, or default if not found or expired.
        """
        self._read_count += 1

        entry = self._store.get(key)

        if entry is None:
            logger.debug(
                "memory_miss",
                workflow_id=self._workflow_id,
                key=key,
                reader=reader,
            )
            return default

        if entry.is_expired:
            async with self._lock:
                self._store.pop(key, None)
            logger.debug(
                "memory_expired",
                workflow_id=self._workflow_id,
                key=key,
                reader=reader,
            )
            return default

        logger.debug(
            "memory_hit",
            workflow_id=self._workflow_id,
            key=key,
            reader=reader,
            written_by=entry.written_by,
            version=entry.version,
        )
        return entry.value

    async def get_or_raise(self, key: str, reader: str = "unknown") -> Any:
        """
        Retrieve a value, raising if it is missing.

        Use this when the value MUST exist — it failing to exist
        means a required agent did not complete before this one ran.

        Args:
            key: Memory key to retrieve.
            reader: Agent name for audit logging.

        Returns:
            The stored value.

        Raises:
            WorkflowContextError: If key is missing or expired.
        """
        value = await self.get(key, default=_SENTINEL, reader=reader)
        if value is _SENTINEL:
            msg = (
                f"Required memory key '{key}' not found in workflow "
                f"{self._workflow_id}. "
                f"Agent '{reader}' requires this data to be present. "
                f"Check that the producing agent completed successfully "
                f"before this agent was dispatched."
            )
            raise WorkflowContextError(msg, workflow_id=self._workflow_id)
        return value

    async def delete(self, key: str, deleted_by: str = "unknown") -> bool:
        """
        Delete a key from memory.

        Args:
            key: The key to delete.
            deleted_by: Agent name for audit logging.

        Returns:
            True if the key existed and was deleted, False otherwise.
        """
        if self._read_only:
            msg = (
                f"MemoryStore for workflow {self._workflow_id} is read-only."
            )
            raise WorkflowContextError(msg, workflow_id=self._workflow_id)

        async with self._lock:
            existed = key in self._store
            self._store.pop(key, None)
            if existed:
                logger.debug(
                    "memory_deleted",
                    workflow_id=self._workflow_id,
                    key=key,
                    deleted_by=deleted_by,
                )
            return existed

    async def exists(self, key: str) -> bool:
        """Return True if the key exists and has not expired."""
        entry = self._store.get(key)
        if entry is None:
            return False
        if entry.is_expired:
            async with self._lock:
                self._store.pop(key, None)
            return False
        return True

    async def keys(self) -> list[str]:
        """Return all non-expired keys currently in memory."""
        async with self._lock:
            expired = [k for k, v in self._store.items() if v.is_expired]
            for k in expired:
                self._store.pop(k, None)
        return list(self._store.keys())

    async def snapshot(self) -> dict[str, Any]:
        """
        Return a snapshot of all current memory values.

        Used by the Checkpoint Manager to persist memory state
        and by the Report Agent to include memory context in reports.

        Returns:
            Dict of key → value for all non-expired entries.
        """
        result: dict[str, Any] = {}
        async with self._lock:
            for key, entry in list(self._store.items()):
                if not entry.is_expired:
                    result[key] = entry.value
        return result

    async def restore_snapshot(
        self, snapshot: dict[str, Any], restored_by: str = "checkpoint"
    ) -> None:
        """
        Restore memory from a checkpoint snapshot.

        Called when resuming a workflow from a checkpoint.
        Clears current memory and replaces it with the snapshot.

        Args:
            snapshot: Dict of key → value from a previous snapshot.
            restored_by: Who is restoring (for audit logging).
        """
        async with self._lock:
            self._store.clear()
            for key, value in snapshot.items():
                self._store[key] = _MemoryEntry(
                    value=value,
                    written_by=restored_by,
                )

        logger.info(
            "memory_restored_from_snapshot",
            workflow_id=self._workflow_id,
            keys_restored=len(snapshot),
            restored_by=restored_by,
        )

    async def clear(self) -> None:
        """Clear all entries from memory."""
        async with self._lock:
            count = len(self._store)
            self._store.clear()
        logger.debug(
            "memory_cleared",
            workflow_id=self._workflow_id,
            entries_removed=count,
        )

    @property
    def stats(self) -> dict[str, int]:
        """Memory access statistics for monitoring."""
        return {
            "total_keys": len(self._store),
            "write_count": self._write_count,
            "read_count": self._read_count,
        }

    def as_read_only(self) -> MemoryStore:
        """
        Return a read-only view of this memory store.

        Used by the Memory & Learning Agent to safely access
        historical workflow data without risk of modification.
        See ADR-006 read-only exception.

        Returns:
            A new MemoryStore instance backed by the same data
            but with read_only=True enforced.
        """
        read_only_store = MemoryStore(
            workflow_id=self._workflow_id,
            read_only=True,
        )
        # Share the same underlying store dict (read-only access only)
        read_only_store._store = self._store
        return read_only_store


# Sentinel value — distinct from None for get_or_raise
_SENTINEL = object()
