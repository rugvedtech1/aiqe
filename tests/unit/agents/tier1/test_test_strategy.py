"""Unit tests for Test Strategy Agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiqe.agents.test_strategy.agent import TestStrategyAgent
from aiqe.agents.types import TestStrategyInput


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.set = AsyncMock()
    memory.get = AsyncMock(return_value=None)
    return memory


@pytest.fixture
def project_analysis_data():
    return {
        "language": "python",
        "framework": "fastapi",
        "has_database": True,
        "auth_method": "jwt",
        "routes": [
            {"method": "GET", "path": "/users"},
            {"method": "POST", "path": "/auth/login"},
        ],
        "source_files_count": 25,
    }


class TestTestStrategyAgentClassVars:
    def test_name(self):
        assert TestStrategyAgent.NAME == "test_strategy"

    def test_tier(self):
        assert TestStrategyAgent.TIER == 1

    def test_dependencies(self):
        assert "project_analysis" in TestStrategyAgent.DEPENDENCIES


class TestTestStrategyAgentExecution:
    @pytest.mark.asyncio
    async def test_generates_test_plan(self, mock_memory, project_analysis_data):
        agent = TestStrategyAgent(memory_store=mock_memory)
        input_data = TestStrategyInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            project_analysis=project_analysis_data,
            changed_files=["src/auth.py", "src/users.py"],
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert len(output.test_plan) > 0

    @pytest.mark.asyncio
    async def test_identifies_auth_as_critical(
        self, mock_memory, project_analysis_data
    ):
        agent = TestStrategyAgent(memory_store=mock_memory)
        input_data = TestStrategyInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            project_analysis=project_analysis_data,
            changed_files=["src/auth.py"],
            dry_run=True,
        )
        output = await agent.run(input_data)
        priorities = [area.get("priority") for area in output.test_plan]
        assert "Critical" in priorities or "High" in priorities

    @pytest.mark.asyncio
    async def test_detects_regression_risk_many_files(self, mock_memory):
        agent = TestStrategyAgent(memory_store=mock_memory)
        input_data = TestStrategyInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            changed_files=[f"src/file_{i}.py" for i in range(15)],
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.regression_risk is True

    @pytest.mark.asyncio
    async def test_detects_regression_risk_auth_files(self, mock_memory):
        agent = TestStrategyAgent(memory_store=mock_memory)
        input_data = TestStrategyInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            changed_files=["src/auth_middleware.py"],
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.regression_risk is True

    @pytest.mark.asyncio
    async def test_no_regression_risk_trivial_change(self, mock_memory):
        agent = TestStrategyAgent(memory_store=mock_memory)
        input_data = TestStrategyInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            changed_files=["README.md"],
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.regression_risk is False

    @pytest.mark.asyncio
    async def test_writes_to_memory(self, mock_memory, project_analysis_data):
        agent = TestStrategyAgent(memory_store=mock_memory)
        input_data = TestStrategyInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            project_analysis=project_analysis_data,
            changed_files=["src/main.py"],
            dry_run=True,
        )
        await agent.run(input_data)
        assert mock_memory.set.call_count >= 1

    @pytest.mark.asyncio
    async def test_ai_strategy_called_when_gateway_present(self, mock_memory):
        mock_gateway = MagicMock()
        import json
        mock_gateway.complete = AsyncMock()
        from aiqe.gateway.types import AIResponse
        mock_gateway.complete.return_value = AIResponse(
            content=json.dumps({
                "test_plan": [
                    {
                        "area": "Authentication",
                        "priority": "Critical",
                        "risk_score": 0.95,
                        "test_types": ["positive", "negative", "security"],
                        "estimated_cases": 15,
                        "reason": "Auth files changed",
                    }
                ],
                "risk_assessment": "High",
                "regression_risk": True,
                "regression_reason": "Core auth changed",
                "confidence": 0.92,
                "reasoning": "Auth changes require thorough testing",
            }),
            provider="openai",
            model="gpt-4o",
            total_tokens=400,
        )

        agent = TestStrategyAgent(
            memory_store=mock_memory,
            gateway=mock_gateway,
        )
        input_data = TestStrategyInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            changed_files=["src/auth.py"],
            dry_run=False,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert mock_gateway.complete.call_count == 1
        assert output.confidence >= 0.9
        auth_areas = [
            a for a in output.test_plan
            if "auth" in a.get("area", "").lower()
        ]
        assert len(auth_areas) > 0
