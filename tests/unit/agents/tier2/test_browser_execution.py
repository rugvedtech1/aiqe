"""Unit tests for Browser Execution Agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from aiqe.agents.browser_execution.agent import (
    BrowserExecutionAgent,
    BrowserExecutionInput,
    BrowserExecutionOutput,
    BrowserTestResult,
)


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.set = AsyncMock()
    memory.get = AsyncMock(return_value=None)
    return memory


@pytest.fixture
def sample_playwright_scripts():
    return [
        {
            "filename": "test_playwright_authentication.py",
            "content": "def test_login(page): pass",
            "script_type": "playwright",
            "test_count": 2,
            "feature": "authentication",
        }
    ]


class TestBrowserExecutionClassVars:
    def test_name(self):
        assert BrowserExecutionAgent.NAME == "browser_execution"

    def test_tier(self):
        assert BrowserExecutionAgent.TIER == 2

    def test_dependencies(self):
        assert "automation_generator" in BrowserExecutionAgent.DEPENDENCIES


class TestBrowserExecutionExecution:
    @pytest.mark.asyncio
    async def test_dry_run_simulates_results(
        self, mock_memory, sample_playwright_scripts
    ):
        mock_memory.get = AsyncMock(return_value=sample_playwright_scripts)
        agent = BrowserExecutionAgent(memory_store=mock_memory)
        input_data = BrowserExecutionInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert output.total_executed > 0
        assert output.execution_mode in {"simulation", "dry_run"}

    @pytest.mark.asyncio
    async def test_no_scripts_returns_skipped(self, mock_memory):
        mock_memory.get = AsyncMock(return_value=None)
        agent = BrowserExecutionAgent(memory_store=mock_memory)
        input_data = BrowserExecutionInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert output.execution_mode == "skipped_no_scripts"

    @pytest.mark.asyncio
    async def test_pass_rate_computed(
        self, mock_memory, sample_playwright_scripts
    ):
        mock_memory.get = AsyncMock(return_value=sample_playwright_scripts)
        agent = BrowserExecutionAgent(memory_store=mock_memory)
        input_data = BrowserExecutionInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert 0.0 <= output.pass_rate <= 1.0

    @pytest.mark.asyncio
    async def test_writes_to_memory(
        self, mock_memory, sample_playwright_scripts
    ):
        mock_memory.get = AsyncMock(return_value=sample_playwright_scripts)
        agent = BrowserExecutionAgent(memory_store=mock_memory)
        input_data = BrowserExecutionInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        await agent.run(input_data)
        assert mock_memory.set.call_count >= 2

    @pytest.mark.asyncio
    async def test_unreachable_app_uses_simulation(self, mock_memory, sample_playwright_scripts):
        mock_memory.get = AsyncMock(return_value=sample_playwright_scripts)
        agent = BrowserExecutionAgent(memory_store=mock_memory)

        with patch.object(agent, "_check_application", return_value=False):
            input_data = BrowserExecutionInput(
                workflow_id="wf_001",
                project_path="/tmp",
                dry_run=False,
            )
            output = await agent.run(input_data)

        assert output.success is True
        assert output.execution_mode == "simulation"


class TestBrowserTestResult:
    def test_default_id_generated(self):
        result = BrowserTestResult()
        assert result.test_id.startswith("bt_")

    def test_to_dict(self):
        result = BrowserTestResult(
            test_name="Test login",
            feature="auth",
            passed=True,
            duration_seconds=1.5,
        )
        d = result.to_dict()
        assert d["test_name"] == "Test login"
        assert d["passed"] is True
        assert d["duration_seconds"] == 1.5
