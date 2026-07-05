"""Unit tests for MemoryStore."""
import asyncio
import pytest
from aiqe.memory.store import MemoryStore
from aiqe.shared.exceptions import WorkflowContextError


@pytest.fixture
def store():
    return MemoryStore(workflow_id="wf_test_001")


@pytest.fixture
def readonly_store():
    s = MemoryStore(workflow_id="wf_readonly")
    return s.as_read_only()


class TestMemoryStoreBasics:
    @pytest.mark.asyncio
    async def test_set_and_get(self, store):
        await store.set("key1", {"data": 42}, written_by="agent_a")
        value = await store.get("key1", reader="agent_b")
        assert value == {"data": 42}

    @pytest.mark.asyncio
    async def test_get_missing_returns_default(self, store):
        result = await store.get("missing", default="fallback")
        assert result == "fallback"

    @pytest.mark.asyncio
    async def test_get_or_raise_missing_raises(self, store):
        with pytest.raises(WorkflowContextError, match="not found"):
            await store.get_or_raise("missing_key", reader="agent")

    @pytest.mark.asyncio
    async def test_get_or_raise_existing(self, store):
        await store.set("present", "value", written_by="agent")
        result = await store.get_or_raise("present", reader="agent")
        assert result == "value"

    @pytest.mark.asyncio
    async def test_overwrite_false_raises_on_existing(self, store):
        await store.set("key", "v1", written_by="a")
        with pytest.raises(ValueError):
            await store.set("key", "v2", written_by="b", overwrite=False)

    @pytest.mark.asyncio
    async def test_overwrite_true_updates_value(self, store):
        await store.set("key", "v1", written_by="a")
        await store.set("key", "v2", written_by="a")
        result = await store.get("key")
        assert result == "v2"

    @pytest.mark.asyncio
    async def test_delete(self, store):
        await store.set("temp", "value", written_by="a")
        deleted = await store.delete("temp", deleted_by="a")
        assert deleted is True
        result = await store.get("temp")
        assert result is None

    @pytest.mark.asyncio
    async def test_exists(self, store):
        assert not await store.exists("key")
        await store.set("key", "val", written_by="a")
        assert await store.exists("key")

    @pytest.mark.asyncio
    async def test_keys(self, store):
        await store.set("k1", 1, written_by="a")
        await store.set("k2", 2, written_by="a")
        keys = await store.keys()
        assert "k1" in keys
        assert "k2" in keys

    @pytest.mark.asyncio
    async def test_snapshot(self, store):
        await store.set("a", 1, written_by="x")
        await store.set("b", 2, written_by="x")
        snap = await store.snapshot()
        assert snap == {"a": 1, "b": 2}

    @pytest.mark.asyncio
    async def test_restore_snapshot(self, store):
        snap = {"restored_key": "restored_value"}
        await store.restore_snapshot(snap, restored_by="checkpoint")
        result = await store.get("restored_key")
        assert result == "restored_value"


class TestReadOnlyStore:
    @pytest.mark.asyncio
    async def test_read_only_set_raises(self, readonly_store):
        with pytest.raises(WorkflowContextError, match="read-only"):
            await readonly_store.set("key", "value", written_by="agent")

    @pytest.mark.asyncio
    async def test_read_only_delete_raises(self, readonly_store):
        with pytest.raises(WorkflowContextError):
            await readonly_store.delete("key", deleted_by="agent")


class TestTTL:
    @pytest.mark.asyncio
    async def test_expired_entry_returns_default(self, store):
        await store.set("temp", "value", written_by="a", ttl_seconds=0.001)
        await asyncio.sleep(0.01)
        result = await store.get("temp", default="gone")
        assert result == "gone"
