"""Unit tests for API Validation Agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiqe.agents.api_validation.agent import (
    APIValidationAgent,
    APIValidationInput,
    APIValidationOutput,
    APITestResult,
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
                "id": "endpoint:GET:/users",
                "label": "GET /users",
                "node_type": "endpoint",
                "metadata": {
                    "method": "GET",
                    "path": "/users",
                    "requires_auth": True,
                    "source": "fastapi",
                },
            },
            "endpoint:POST:/auth/login": {
                "id": "endpoint:POST:/auth/login",
                "label": "POST /auth/login",
                "node_type": "endpoint",
                "metadata": {
                    "method": "POST",
                    "path": "/auth/login",
                    "requires_auth": False,
                    "source": "fastapi",
                },
            },
        },
        "edges": [],
    }


class TestAPIValidationClassVars:
    def test_name(self):
        assert APIValidationAgent.NAME == "api_validation"

    def test_tier(self):
        assert APIValidationAgent.TIER == 2

    def test_dependencies(self):
        assert "automation_generator" in APIValidationAgent.DEPENDENCIES
        assert "project_analysis" in APIValidationAgent.DEPENDENCIES


class TestAPIValidationExecution:
    @pytest.mark.asyncio
    async def test_dry_run_simulates_results(
        self, mock_memory, sample_api_graph
    ):
        mock_memory.get = AsyncMock(side_effect=[
            sample_api_graph,   # API_DEPENDENCY_GRAPH
            {"framework": "fastapi", "routes": []},  # PROJECT_ANALYSIS
            [],  # API_TEST_SCRIPTS
        ])

        agent = APIValidationAgent(memory_store=mock_memory)
        input_data = APIValidationInput(
            workflow_id="wf_001",
            project_path="/tmp",
            base_url="http://localhost:8000",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True

    @pytest.mark.asyncio
    async def test_no_endpoints_returns_warning(self, mock_memory):
        mock_memory.get = AsyncMock(return_value=None)
        agent = APIValidationAgent(memory_store=mock_memory)
        input_data = APIValidationInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True

    @pytest.mark.asyncio
    async def test_extracts_endpoints_from_graph(
        self, mock_memory, sample_api_graph
    ):
        agent = APIValidationAgent(memory_store=mock_memory)
        endpoints = agent._extract_endpoints(sample_api_graph)
        assert len(endpoints) == 2
        methods = {ep["method"] for ep in endpoints}
        assert "GET" in methods
        assert "POST" in methods

    @pytest.mark.asyncio
    async def test_merges_endpoints_no_duplicates(self, mock_memory):
        agent = APIValidationAgent(memory_store=mock_memory)
        graph_eps = [{"method": "GET", "path": "/users"}]
        route_eps = [
            {"method": "GET", "path": "/users"},
            {"method": "POST", "path": "/users"},
        ]
        merged = agent._merge_endpoints(graph_eps, route_eps)
        assert len(merged) == 2

    @pytest.mark.asyncio
    async def test_writes_to_memory(
        self, mock_memory, sample_api_graph
    ):
        mock_memory.get = AsyncMock(side_effect=[
            sample_api_graph,
            {},
            [],
        ])
        agent = APIValidationAgent(memory_store=mock_memory)
        input_data = APIValidationInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        await agent.run(input_data)
        assert mock_memory.set.call_count >= 1

    @pytest.mark.asyncio
    async def test_unreachable_api_uses_simulation(
        self, mock_memory, sample_api_graph
    ):
        mock_memory.get = AsyncMock(side_effect=[
            sample_api_graph,
            {},
            [],
        ])
        agent = APIValidationAgent(memory_store=mock_memory)

        with patch.object(agent, "_check_api", return_value=False):
            input_data = APIValidationInput(
                workflow_id="wf_001",
                project_path="/tmp",
                dry_run=False,
            )
            output = await agent.run(input_data)

        assert output.success is True
        assert output.confidence <= 0.6

    @pytest.mark.asyncio
    async def test_pass_rate_computed(
        self, mock_memory, sample_api_graph
    ):
        mock_memory.get = AsyncMock(side_effect=[
            sample_api_graph,
            {},
            [],
        ])
        agent = APIValidationAgent(memory_store=mock_memory)
        input_data = APIValidationInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert 0.0 <= output.pass_rate <= 1.0


class TestAPITestResult:
    def test_default_id(self):
        result = APITestResult()
        assert result.test_id.startswith("api_")

    def test_to_dict_truncates_response(self):
        result = APITestResult(
            endpoint="/users",
            method="GET",
            passed=True,
            response_snippet="x" * 500,
        )
        d = result.to_dict()
        assert len(d["response_snippet"]) <= 200


class TestRegistrySetupTier2:
    def test_all_tier2_agents_registered(self):
        from aiqe.workflow.registry import AgentRegistry, AgentRegistration
        fresh = AgentRegistry()

        from aiqe.agents.registry_setup import register_all_agents
        import aiqe.agents.registry_setup as setup_mod

        original = setup_mod.agent_registry
        import aiqe.agents.registry_setup
        import aiqe.workflow.registry as reg_mod

        orig_registry = reg_mod.agent_registry
        reg_mod.agent_registry = fresh
        setup_mod.agent_registry = fresh

        try:
            register_all_agents()
            assert fresh.is_registered("automation_generator")
            assert fresh.is_registered("browser_execution")
            assert fresh.is_registered("api_validation")
        finally:
            reg_mod.agent_registry = orig_registry
            setup_mod.agent_registry = orig_registry
