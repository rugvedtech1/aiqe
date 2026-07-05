"""Unit tests for MemoryManager."""
import pytest
from aiqe.memory.manager import MemoryManager
from aiqe.shared.exceptions import WorkflowContextError


@pytest.fixture
def manager():
    return MemoryManager()


class TestMemoryManager:
    @pytest.mark.asyncio
    async def test_create_and_get(self, manager):
        store = await manager.create("wf_001")
        retrieved = manager.get("wf_001")
        assert store is retrieved

    @pytest.mark.asyncio
    async def test_duplicate_create_raises(self, manager):
        await manager.create("wf_dup")
        with pytest.raises(WorkflowContextError):
            await manager.create("wf_dup")

    @pytest.mark.asyncio
    async def test_get_unknown_raises(self, manager):
        with pytest.raises(WorkflowContextError):
            manager.get("wf_nonexistent")

    @pytest.mark.asyncio
    async def test_destroy_removes_store(self, manager):
        await manager.create("wf_temp")
        await manager.destroy("wf_temp")
        with pytest.raises(WorkflowContextError):
            manager.get("wf_temp")

    @pytest.mark.asyncio
    async def test_read_only_access(self, manager):
        store = await manager.create("wf_ro")
        await store.set("key", "value", written_by="agent")
        ro_store = manager.read_only_access("wf_ro")
        result = await ro_store.get("key")
        assert result == "value"
        with pytest.raises(WorkflowContextError):
            await ro_store.set("key", "new", written_by="learning_agent")

    @pytest.mark.asyncio
    async def test_active_workflow_count(self, manager):
        assert manager.active_workflow_count == 0
        await manager.create("wf_a")
        await manager.create("wf_b")
        assert manager.active_workflow_count == 2
        await manager.destroy("wf_a")
        assert manager.active_workflow_count == 1
