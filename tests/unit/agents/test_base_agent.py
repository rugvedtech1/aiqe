"""Unit tests for BaseAgent abstract class."""
import pytest
from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput
from aiqe.shared.exceptions import AgentError


# Concrete agent implementations for testing

class GoodAgent(BaseAgent):
    NAME = "good_agent"
    DESCRIPTION = "A well-behaved test agent."
    TIER = 1
    DEPENDENCIES = []

    async def run_impl(self, input_data: AgentInput) -> AgentOutput:
        output = AgentOutput()
        output.reasoning = "I did my job correctly."
        output.confidence = 0.9
        output.add_evidence("log", "Everything OK", "agent.log")
        return output


class FailingAgent(BaseAgent):
    NAME = "failing_agent"
    DESCRIPTION = "An agent that always fails."
    TIER = 2
    DEPENDENCIES = ["good_agent"]

    async def run_impl(self, input_data: AgentInput) -> AgentOutput:
        raise RuntimeError("Simulated failure")


class NoReasoningAgent(BaseAgent):
    NAME = "no_reasoning_agent"
    DESCRIPTION = "An agent that forgets to add reasoning."
    TIER = 1
    DEPENDENCIES = []

    async def run_impl(self, input_data: AgentInput) -> AgentOutput:
        output = AgentOutput()
        # Intentionally no reasoning set — should trigger warning
        return output


class TestBaseAgentClassValidation:
    def test_missing_name_raises_at_class_definition(self):
        with pytest.raises(TypeError, match="NAME"):
            class BadAgent(BaseAgent):
                NAME = ""
                DESCRIPTION = "bad"
                TIER = 1
                async def run_impl(self, input_data):
                    pass

    def test_invalid_tier_raises_at_class_definition(self):
        with pytest.raises(TypeError, match="TIER"):
            class BadTierAgent(BaseAgent):
                NAME = "bad_tier"
                DESCRIPTION = "bad"
                TIER = 5  # Invalid
                async def run_impl(self, input_data):
                    pass


class TestBaseAgentRun:
    @pytest.mark.asyncio
    async def test_successful_run(self):
        agent = GoodAgent()
        input_data = AgentInput(workflow_id="wf_001", project_path="/tmp/project")
        output = await agent.run(input_data)
        assert output.success is True
        assert output.reasoning == "I did my job correctly."
        assert output.confidence == 0.9
        assert len(output.evidence) == 1
        assert output.duration_seconds > 0

    @pytest.mark.asyncio
    async def test_missing_workflow_id_returns_error(self):
        agent = GoodAgent()
        input_data = AgentInput(workflow_id="", project_path="/tmp")
        output = await agent.run(input_data)
        assert output.success is False
        assert "workflow_id" in output.error.lower()

    @pytest.mark.asyncio
    async def test_failing_agent_raises_agent_error(self):
        agent = FailingAgent()
        input_data = AgentInput(workflow_id="wf_001", project_path="/tmp")
        with pytest.raises(AgentError):
            await agent.run(input_data)

    @pytest.mark.asyncio
    async def test_missing_reasoning_adds_warning(self):
        agent = NoReasoningAgent()
        input_data = AgentInput(workflow_id="wf_001", project_path="/tmp")
        output = await agent.run(input_data)
        assert output.success is True
        assert len(output.warnings) > 0
        assert "reasoning" in output.warnings[0].lower()

    @pytest.mark.asyncio
    async def test_dry_run(self):
        agent = GoodAgent()
        input_data = AgentInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert "DRY RUN" in output.reasoning
        assert output.metadata.get("dry_run") is True

    def test_repr(self):
        agent = GoodAgent()
        assert "GoodAgent" in repr(agent)
        assert "good_agent" in repr(agent)


class TestOrchestratorAgent:
    @pytest.mark.asyncio
    async def test_orchestrator_builds_plan(self):
        from aiqe.agents.orchestrator.agent import OrchestratorAgent, OrchestratorInput
        agent = OrchestratorAgent()
        input_data = OrchestratorInput(workflow_id="wf_001")
        output = await agent.run(input_data)
        assert output.success is True
        assert isinstance(output.reasoning, str)
        assert len(output.reasoning) > 0
        assert output.confidence == 1.0

    def test_orchestrator_class_variables(self):
        from aiqe.agents.orchestrator.agent import OrchestratorAgent
        assert OrchestratorAgent.NAME == "orchestrator"
        assert OrchestratorAgent.TIER == 1
        assert OrchestratorAgent.DEPENDENCIES == []
