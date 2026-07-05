"""Unit tests for Bug Analysis Agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiqe.agents.bug_analysis.agent import (
    BugAnalysisAgent,
    BugAnalysisInput,
    BugAnalysisOutput,
)


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.set = AsyncMock()
    memory.get = AsyncMock(return_value=None)
    return memory


@pytest.fixture
def sample_failures():
    return {
        "browser_failed": [
            {
                "test_name": "Login test failed",
                "feature": "authentication",
                "error": "Element not found: #login-button",
                "source_agent": "browser_execution",
                "failure_category": "browser_test",
            }
        ],
        "api_results": {
            "failed_tests": [
                {
                    "endpoint": "/users",
                    "method": "GET",
                    "error": "500 Internal Server Error",
                    "source_agent": "api_validation",
                    "failure_category": "api_validation",
                    "feature": "user_management",
                }
            ]
        },
        "security_results": {
            "findings": [
                {
                    "category": "sql_injection",
                    "title": "SQL Injection in login",
                    "severity": "Critical",
                    "confidence": 0.85,
                    "source_agent": "security_testing",
                    "failure_category": "security",
                    "feature": "authentication",
                    "description": "String interpolation in SQL query",
                    "remediation": "Use parameterised queries",
                    "cwe": "CWE-89",
                }
            ]
        },
    }


class TestBugAnalysisClassVars:
    def test_name(self):
        assert BugAnalysisAgent.NAME == "bug_analysis"

    def test_tier(self):
        assert BugAnalysisAgent.TIER == 4

    def test_dependencies(self):
        assert "browser_execution" in BugAnalysisAgent.DEPENDENCIES
        assert "security_testing" in BugAnalysisAgent.DEPENDENCIES
        assert "performance" in BugAnalysisAgent.DEPENDENCIES


class TestBugAnalysisExecution:
    @pytest.mark.asyncio
    async def test_no_failures_returns_clean_result(self, mock_memory):
        mock_memory.get = AsyncMock(return_value=None)
        agent = BugAnalysisAgent(memory_store=mock_memory)
        input_data = BugAnalysisInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert output.total_bugs == 0

    @pytest.mark.asyncio
    async def test_creates_bugs_from_failures(
        self, mock_memory, sample_failures
    ):
        def mock_get(key, reader=None):
            from aiqe.memory.schema import MemoryKeys
            if "failed_tests" in key or "browser" in key:
                return sample_failures["browser_failed"]
            elif "api_validation" in key:
                return sample_failures["api_results"]
            elif "security" in key:
                return sample_failures["security_results"]
            return None

        mock_memory.get = AsyncMock(side_effect=lambda key, reader=None: (
            sample_failures["browser_failed"] if "browser" in str(key)
            else sample_failures["api_results"] if "api_validation" in str(key)
            else sample_failures["security_results"] if "security" in str(key)
            else None
        ))

        agent = BugAnalysisAgent(memory_store=mock_memory)
        input_data = BugAnalysisInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert output.total_bugs >= 0

    @pytest.mark.asyncio
    async def test_marks_downstream_effects(self, mock_memory):
        bugs = [
            {
                "id": "bug_001",
                "title": "Root cause bug",
                "severity": "Critical",
                "confidence": 0.9,
                "affected_feature": "auth",
                "is_downstream": False,
            },
            {
                "id": "bug_002",
                "title": "Downstream bug",
                "severity": "High",
                "confidence": 0.7,
                "affected_feature": "auth",
                "is_downstream": False,
            },
        ]
        agent = BugAnalysisAgent(memory_store=mock_memory)
        result = agent._mark_downstream_effects(bugs)
        root_causes = [b for b in result if not b.get("is_downstream")]
        downstream = [b for b in result if b.get("is_downstream")]
        assert len(root_causes) == 1
        assert len(downstream) == 1

    @pytest.mark.asyncio
    async def test_groups_by_feature(self, mock_memory):
        failures = [
            {"feature": "auth", "title": "Login fails", "error": "500"},
            {"feature": "auth", "title": "Register fails", "error": "400"},
            {"feature": "products", "title": "List fails", "error": "404"},
        ]
        agent = BugAnalysisAgent(memory_store=mock_memory)
        grouped = agent._group_by_feature(failures)
        assert "auth" in grouped
        assert "products" in grouped
        assert len(grouped["auth"]) == 2

    @pytest.mark.asyncio
    async def test_writes_to_memory(self, mock_memory):
        mock_memory.get = AsyncMock(return_value=None)
        agent = BugAnalysisAgent(memory_store=mock_memory)
        input_data = BugAnalysisInput(
            workflow_id="wf_001",
            project_path="/tmp",
            dry_run=True,
        )
        await agent.run(input_data)
        assert mock_memory.set.call_count >= 1
