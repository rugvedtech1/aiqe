"""Unit tests for Automation Generator Agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiqe.agents.automation_generator.agent import (
    AutomationGeneratorAgent,
    AutomationGeneratorInput,
    AutomationGeneratorOutput,
    GeneratedScript,
)


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.set = AsyncMock()
    memory.get = AsyncMock(return_value=None)
    return memory


@pytest.fixture
def sample_test_cases():
    return [
        {
            "id": "tc_001",
            "title": "Verify login with valid credentials",
            "test_type": "positive",
            "feature": "authentication",
            "area": "authentication",
            "priority": "Critical",
            "steps": ["Navigate to login", "Enter credentials", "Click login"],
            "expected_result": "User logged in",
            "automation_hint": "Playwright form fill test",
            "is_automatable": True,
            "tags": ["authentication", "positive"],
        },
        {
            "id": "tc_002",
            "title": "Verify GET /users returns 200",
            "test_type": "positive",
            "feature": "user management",
            "area": "user_management",
            "priority": "High",
            "steps": ["Send GET /users request", "Verify 200 response"],
            "expected_result": "200 OK with user list",
            "automation_hint": "API GET request validation",
            "is_automatable": True,
            "tags": ["api", "positive"],
        },
    ]


class TestAutomationGeneratorClassVars:
    def test_name(self):
        assert AutomationGeneratorAgent.NAME == "automation_generator"

    def test_tier(self):
        assert AutomationGeneratorAgent.TIER == 2

    def test_dependencies(self):
        assert "test_case_generator" in AutomationGeneratorAgent.DEPENDENCIES
        assert "project_analysis" in AutomationGeneratorAgent.DEPENDENCIES


class TestAutomationGeneratorExecution:
    @pytest.mark.asyncio
    async def test_generates_scripts_from_memory(
        self, mock_memory, sample_test_cases, tmp_path
    ):
        mock_memory.get = AsyncMock(side_effect=[
            sample_test_cases,   # GENERATED_TEST_CASES
            {"framework": "fastapi"},  # PROJECT_ANALYSIS_RESULT
        ])

        agent = AutomationGeneratorAgent(memory_store=mock_memory)
        input_data = AutomationGeneratorInput(
            workflow_id="wf_001",
            project_path=str(tmp_path),
            base_url="http://localhost:8000",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True

    @pytest.mark.asyncio
    async def test_no_test_cases_returns_warning(
        self, mock_memory, tmp_path
    ):
        mock_memory.get = AsyncMock(return_value=None)
        agent = AutomationGeneratorAgent(memory_store=mock_memory)
        input_data = AutomationGeneratorInput(
            workflow_id="wf_001",
            project_path=str(tmp_path),
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert len(output.warnings) > 0

    @pytest.mark.asyncio
    async def test_writes_to_memory(
        self, mock_memory, sample_test_cases, tmp_path
    ):
        mock_memory.get = AsyncMock(side_effect=[
            sample_test_cases,
            {"framework": "fastapi"},
        ])
        agent = AutomationGeneratorAgent(memory_store=mock_memory)
        input_data = AutomationGeneratorInput(
            workflow_id="wf_001",
            project_path=str(tmp_path),
            dry_run=True,
        )
        await agent.run(input_data)
        assert mock_memory.set.call_count >= 2

    def test_to_function_name(self):
        agent = AutomationGeneratorAgent()
        assert agent._to_function_name("Verify login works") == "test_verify_login_works"
        assert agent._to_function_name("test_something") == "test_something"
        assert agent._to_function_name("") == "test_case"


class TestGeneratedScript:
    def test_to_dict(self):
        script = GeneratedScript(
            filename="test_auth.py",
            content="import pytest\ndef test_login(): pass",
            script_type="playwright",
            test_count=1,
            feature="authentication",
        )
        d = script.to_dict()
        assert d["filename"] == "test_auth.py"
        assert d["script_type"] == "playwright"
        assert d["test_count"] == 1
        assert "content" not in d
        assert "content_length" in d
