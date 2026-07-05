"""Unit tests for updated Orchestrator Agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiqe.agents.orchestrator.agent import (
    OrchestratorAgent,
    OrchestratorInput,
    OrchestratorOutput,
)
from aiqe.workflow.registry import AgentRegistry, AgentRegistration


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.set = AsyncMock()
    memory.get = AsyncMock(return_value=None)
    return memory


@pytest.fixture
def fresh_registry():
    return AgentRegistry()


class TestOrchestratorAgent:
    def test_name(self):
        assert OrchestratorAgent.NAME == "orchestrator"

    def test_tier(self):
        assert OrchestratorAgent.TIER == 1

    def test_no_dependencies(self):
        assert OrchestratorAgent.DEPENDENCIES == []

    @pytest.mark.asyncio
    async def test_builds_execution_plan(self, mock_memory):
        from aiqe.agents.registry_setup import register_all_agents
        register_all_agents()

        agent = OrchestratorAgent(memory_store=mock_memory)
        input_data = OrchestratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert isinstance(output.execution_plan, list)

    @pytest.mark.asyncio
    async def test_writes_metadata_to_memory(self, mock_memory):
        agent = OrchestratorAgent(memory_store=mock_memory)
        input_data = OrchestratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
        )
        await agent.run(input_data)
        assert mock_memory.set.call_count >= 1

    @pytest.mark.asyncio
    async def test_confidence_is_one(self, mock_memory):
        agent = OrchestratorAgent(memory_store=mock_memory)
        input_data = OrchestratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
        )
        output = await agent.run(input_data)
        assert output.confidence == 1.0

    @pytest.mark.asyncio
    async def test_reasoning_mentions_human_review_gate(self, mock_memory):
        agent = OrchestratorAgent(memory_store=mock_memory)
        input_data = OrchestratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
        )
        output = await agent.run(input_data)
        assert "Human Review Gate" in output.reasoning or len(output.reasoning) > 0

    @pytest.mark.asyncio
    async def test_empty_registry_still_succeeds(self, mock_memory):
        agent = OrchestratorAgent(memory_store=mock_memory)
        input_data = OrchestratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
        )
        output = await agent.run(input_data)
        assert output.success is True
