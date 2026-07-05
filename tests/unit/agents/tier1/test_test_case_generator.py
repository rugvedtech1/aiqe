"""Unit tests for Test Case Generator Agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiqe.agents.test_case_generator.agent import (
    TestCaseGeneratorAgent,
    TestCase,
    TestCaseGeneratorOutput,
)
from aiqe.agents.types import TestCaseGeneratorInput


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.set = AsyncMock()
    memory.get = AsyncMock(return_value=None)
    return memory


@pytest.fixture
def test_strategy_data():
    return {
        "test_plan": [
            {
                "area": "Authentication",
                "priority": "Critical",
                "risk_score": 0.95,
                "test_types": ["positive", "negative", "boundary"],
                "estimated_cases": 10,
                "reason": "Auth files changed",
            },
            {
                "area": "User Management",
                "priority": "High",
                "risk_score": 0.7,
                "test_types": ["positive", "negative"],
                "estimated_cases": 8,
                "reason": "User endpoints affected",
            },
        ],
        "risk_assessment": "High",
        "regression_risk": True,
    }


class TestTestCaseGeneratorClassVars:
    def test_name(self):
        assert TestCaseGeneratorAgent.NAME == "test_case_generator"

    def test_tier(self):
        assert TestCaseGeneratorAgent.TIER == 1

    def test_dependencies(self):
        assert "test_strategy" in TestCaseGeneratorAgent.DEPENDENCIES
        assert "project_analysis" in TestCaseGeneratorAgent.DEPENDENCIES


class TestTestCaseGeneratorExecution:
    @pytest.mark.asyncio
    async def test_generates_test_cases(
        self, mock_memory, test_strategy_data
    ):
        agent = TestCaseGeneratorAgent(memory_store=mock_memory)
        input_data = TestCaseGeneratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            test_strategy=test_strategy_data,
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert output.total_generated > 0

    @pytest.mark.asyncio
    async def test_generates_multiple_test_types(
        self, mock_memory, test_strategy_data
    ):
        agent = TestCaseGeneratorAgent(memory_store=mock_memory)
        input_data = TestCaseGeneratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            test_strategy=test_strategy_data,
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert len(output.by_type) > 0

    @pytest.mark.asyncio
    async def test_respects_max_cases_per_feature(self, mock_memory):
        agent = TestCaseGeneratorAgent(memory_store=mock_memory)
        input_data = TestCaseGeneratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            test_strategy={
                "test_plan": [{
                    "area": "Core",
                    "priority": "High",
                    "risk_score": 0.5,
                    "test_types": ["positive", "negative", "boundary"],
                    "estimated_cases": 20,
                    "reason": "Core changed",
                }]
            },
            max_cases_per_feature=5,
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.total_generated <= 5

    @pytest.mark.asyncio
    async def test_computes_automation_coverage(
        self, mock_memory, test_strategy_data
    ):
        agent = TestCaseGeneratorAgent(memory_store=mock_memory)
        input_data = TestCaseGeneratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            test_strategy=test_strategy_data,
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert 0.0 <= output.automation_coverage <= 1.0

    @pytest.mark.asyncio
    async def test_writes_to_memory(
        self, mock_memory, test_strategy_data
    ):
        agent = TestCaseGeneratorAgent(memory_store=mock_memory)
        input_data = TestCaseGeneratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            test_strategy=test_strategy_data,
            dry_run=True,
        )
        await agent.run(input_data)
        assert mock_memory.set.call_count >= 1

    @pytest.mark.asyncio
    async def test_empty_plan_uses_defaults(self, mock_memory):
        agent = TestCaseGeneratorAgent(memory_store=mock_memory)
        input_data = TestCaseGeneratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            test_strategy={},
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert output.total_generated > 0

    @pytest.mark.asyncio
    async def test_ai_generation_called_when_gateway_present(
        self, mock_memory, test_strategy_data
    ):
        import json
        mock_gateway = MagicMock()
        from aiqe.gateway.types import AIResponse
        mock_gateway.complete = AsyncMock(return_value=AIResponse(
            content=json.dumps([
                {
                    "title": "Verify login with valid credentials",
                    "test_type": "positive",
                    "priority": "Critical",
                    "preconditions": ["User exists in system"],
                    "steps": [
                        "Navigate to login page",
                        "Enter valid username and password",
                        "Click login button",
                    ],
                    "expected_result": "User is logged in, JWT token received",
                    "automation_hint": "Playwright form fill + API assertion",
                    "is_automatable": True,
                },
                {
                    "title": "Verify login fails with wrong password",
                    "test_type": "negative",
                    "priority": "Critical",
                    "preconditions": ["User exists in system"],
                    "steps": [
                        "Navigate to login page",
                        "Enter valid username and wrong password",
                        "Click login button",
                    ],
                    "expected_result": "Error message shown, no token issued",
                    "automation_hint": "Playwright negative test",
                    "is_automatable": True,
                },
            ]),
            provider="openai",
            model="gpt-4o",
            total_tokens=500,
        ))

        agent = TestCaseGeneratorAgent(
            memory_store=mock_memory,
            gateway=mock_gateway,
        )
        input_data = TestCaseGeneratorInput(
            workflow_id="wf_001",
            project_path="/tmp/project",
            test_strategy=test_strategy_data,
            dry_run=False,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert output.total_generated >= 2
        assert mock_gateway.complete.call_count >= 1


class TestTestCase:
    def test_auto_generates_id(self):
        tc = TestCase(title="Test something")
        assert tc.id.startswith("tc_")

    def test_to_dict(self):
        tc = TestCase(
            title="Verify login",
            test_type="positive",
            feature="authentication",
            priority="Critical",
            steps=["Go to login", "Enter credentials"],
            expected_result="Login successful",
        )
        d = tc.to_dict()
        assert d["title"] == "Verify login"
        assert d["test_type"] == "positive"
        assert d["priority"] == "Critical"
        assert len(d["steps"]) == 2
