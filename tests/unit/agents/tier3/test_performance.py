"""Unit tests for Performance Agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiqe.agents.performance.agent import (
    PerformanceAgent,
    PerformanceInput,
    PerformanceOutput,
    APILatencyResult,
    CoreWebVitals,
    THRESHOLDS,
)


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.set = AsyncMock()
    memory.get = AsyncMock(return_value=None)
    return memory


@pytest.fixture
def sample_api_graph():
    return {
        "nodes": {
            "endpoint:GET:/users": {
                "metadata": {
                    "method": "GET",
                    "path": "/users",
                    "requires_auth": True,
                },
            },
            "endpoint:GET:/health": {
                "metadata": {
                    "method": "GET",
                    "path": "/health",
                    "requires_auth": False,
                },
            },
        },
        "edges": [],
    }


class TestPerformanceAgentClassVars:
    def test_name(self):
        assert PerformanceAgent.NAME == "performance"

    def test_tier(self):
        assert PerformanceAgent.TIER == 3

    def test_dependencies(self):
        assert "project_analysis" in PerformanceAgent.DEPENDENCIES
        assert "api_validation" in PerformanceAgent.DEPENDENCIES


class TestPerformanceAgentExecution:
    @pytest.mark.asyncio
    async def test_dry_run_simulates_results(
        self, mock_memory, sample_api_graph
    ):
        mock_memory.get = AsyncMock(side_effect=[
            sample_api_graph,
            {"routes": []},
        ])
        agent = PerformanceAgent(memory_store=mock_memory)
        input_data = PerformanceInput(
            workflow_id="wf_001",
            project_path="/tmp",
            base_url="http://localhost:8000",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert output.total_endpoints_tested >= 0

    @pytest.mark.asyncio
    async def test_unreachable_api_uses_simulation(
        self, mock_memory, sample_api_graph
    ):
        mock_memory.get = AsyncMock(side_effect=[
            sample_api_graph,
            {"routes": []},
        ])
        agent = PerformanceAgent(memory_store=mock_memory)

        with patch.object(agent, "_check_reachable", return_value=False):
            input_data = PerformanceInput(
                workflow_id="wf_001",
                project_path="/tmp",
                dry_run=False,
            )
            output = await agent.run(input_data)

        assert output.success is True
        assert output.confidence <= 0.6

    @pytest.mark.asyncio
    async def test_overall_grade_computed(
        self, mock_memory, sample_api_graph
    ):
        mock_memory.get = AsyncMock(side_effect=[
            sample_api_graph,
            {"routes": []},
        ])
        agent = PerformanceAgent(memory_store=mock_memory)
        input_data = PerformanceInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.overall_grade in {"A", "B", "C", "D", "F", "N/A"}

    @pytest.mark.asyncio
    async def test_writes_to_memory(self, mock_memory):
        agent = PerformanceAgent(memory_store=mock_memory)
        input_data = PerformanceInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        await agent.run(input_data)
        assert mock_memory.set.call_count >= 1

    def test_grade_all_passing(self):
        agent = PerformanceAgent()
        results = [APILatencyResult(p95_ms=100, exceeds_threshold=False)]
        assert agent._compute_grade(results, 0) == "A"

    def test_grade_all_failing(self):
        agent = PerformanceAgent()
        results = [APILatencyResult(p95_ms=2000, exceeds_threshold=True)]
        assert agent._compute_grade(results, 1) == "F"

    def test_grade_empty(self):
        agent = PerformanceAgent()
        assert agent._compute_grade([], 0) == "N/A"

    def test_simulate_core_web_vitals(self):
        agent = PerformanceAgent()
        vitals = agent._simulate_core_web_vitals("http://localhost")
        assert vitals.is_passing is True
        assert vitals.lcp_ms > 0
        assert vitals.cls_score >= 0


class TestAPILatencyResult:
    def test_to_dict_rounds_values(self):
        result = APILatencyResult(
            endpoint="/users",
            method="GET",
            p95_ms=123.456789,
            mean_ms=98.765432,
        )
        d = result.to_dict()
        assert d["p95_ms"] == 123.46
        assert d["mean_ms"] == 98.77
