"""Unit tests for Memory & Learning Agent."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiqe.agents.memory_learning.agent import (
    MemoryLearningAgent,
    MemoryLearningInput,
    MemoryLearningOutput,
)


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.set = AsyncMock()
    memory.get = AsyncMock(return_value=None)
    return memory


class TestMemoryLearningClassVars:
    def test_name(self):
        assert MemoryLearningAgent.NAME == "memory_learning"

    def test_tier(self):
        assert MemoryLearningAgent.TIER == 4

    def test_dependencies(self):
        assert "bug_analysis" in MemoryLearningAgent.DEPENDENCIES


class TestMemoryLearningExecution:
    @pytest.mark.asyncio
    async def test_no_bugs_returns_clean_result(self, mock_memory):
        agent = MemoryLearningAgent(memory_store=mock_memory)
        input_data = MemoryLearningInput(
            workflow_id="wf_001",
            project_path="/tmp",
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert len(output.regressions_detected) == 0

    @pytest.mark.asyncio
    async def test_detects_regression(self, mock_memory):
        current_bugs = [
            {
                "title": "SQL Injection in login",
                "severity": "Critical",
                "affected_feature": "auth",
            }
        ]
        historical_bugs = [
            {
                "title": "SQL Injection in login",
                "severity": "Critical",
                "affected_feature": "auth",
            }
        ]
        mock_memory.get = AsyncMock(return_value={
            "bugs": current_bugs
        })

        agent = MemoryLearningAgent(memory_store=mock_memory)
        input_data = MemoryLearningInput(
            workflow_id="wf_001",
            project_path="/tmp",
        )
        output = await agent.run(input_data)
        assert output.success is True

    def test_detect_regressions_logic(self):
        agent = MemoryLearningAgent()
        current = [{"title": "Bug A", "severity": "High", "affected_feature": "f1"}]
        historical = [{"title": "Bug A", "severity": "High"}]
        regressions = agent._detect_regressions(current, historical)
        assert len(regressions) == 1
        assert regressions[0].get("is_regression") is True

    def test_compute_trends_improving(self):
        agent = MemoryLearningAgent()
        current = [{"severity": "Low"}]
        historical = [{"severity": "Critical"}, {"severity": "High"}]
        trends = agent._compute_trends(current, historical)
        assert trends["trend"] == "improving"

    def test_generate_insights_with_regressions(self):
        agent = MemoryLearningAgent()
        regressions = [
            {"title": "Bug A", "affected_feature": "auth", "is_regression": True}
        ]
        insights = agent._generate_insights(
            current_bugs=regressions,
            regressions=regressions,
            recurring=[],
        )
        assert len(insights) > 0
        assert any("regression" in i.lower() for i in insights)


class TestReportAgent:
    @pytest.mark.asyncio
    async def test_generates_report(self):
        from aiqe.agents.report.agent import ReportAgent, ReportInput
        from unittest.mock import MagicMock, AsyncMock

        mock_mem = MagicMock()
        mock_mem.get = AsyncMock(return_value=None)

        agent = ReportAgent(memory_store=mock_mem)
        input_data = ReportInput(
            workflow_id="wf_test_001",
            project_path="/tmp",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert len(output.report_markdown) > 0
        assert "AIQE" in output.report_markdown
        assert "Human Review Gate" in output.report_markdown

    def test_report_contains_human_review_gate(self):
        from aiqe.agents.report.agent import ReportAgent, ReportInput
        agent = ReportAgent()
        data = {
            "bugs": [],
            "by_severity": {},
            "release_intelligence": {"is_safe_to_merge": True, "release_risk": "Safe"},
            "metadata": {},
            "project": {"language": "python", "framework": "fastapi"},
            "security": {},
            "summary": {"total_bugs": 0},
        }
        input_data = ReportInput(workflow_id="wf_001", project_path="/tmp")
        report = agent._build_markdown_report(data, input_data)
        assert "Human Review Gate" in report
        assert "AIQE" in report

    def test_report_with_critical_bug(self):
        from aiqe.agents.report.agent import ReportAgent, ReportInput
        agent = ReportAgent()
        data = {
            "bugs": [{
                "id": "bug_001",
                "title": "SQL Injection",
                "severity": "Critical",
                "confidence": 0.97,
                "affected_feature": "auth",
                "root_cause": "String interpolation",
                "suggested_fix": "Use parameterised queries",
                "fix_confidence": 0.95,
                "is_downstream": False,
                "is_regression": False,
                "evidence": [],
            }],
            "by_severity": {"Critical": 1},
            "release_intelligence": {
                "is_safe_to_merge": False,
                "release_risk": "Critical",
                "risk_reasoning": "Critical bugs block merge.",
            },
            "metadata": {},
            "project": {"language": "python", "framework": "fastapi"},
            "security": {},
            "summary": {"total_bugs": 1},
        }
        input_data = ReportInput(workflow_id="wf_001", project_path="/tmp")
        report = agent._build_markdown_report(data, input_data)
        assert "SQL Injection" in report
        assert "Critical" in report
        assert "⚠️" in report or "Review Required" in report


class TestAllFifteenAgentsRegistered:
    def test_all_15_agents_present(self):
        from aiqe.workflow.registry import AgentRegistry
        from aiqe.agents.registry_setup import register_all_agents
        import aiqe.agents.registry_setup as setup_mod
        import aiqe.workflow.registry as reg_mod

        fresh = AgentRegistry()
        orig = reg_mod.agent_registry
        reg_mod.agent_registry = fresh
        setup_mod.agent_registry = fresh

        try:
            register_all_agents()
            assert fresh.count == 15

            tier1 = fresh.get_tier(1)
            tier2 = fresh.get_tier(2)
            tier3 = fresh.get_tier(3)
            tier4 = fresh.get_tier(4)

            assert len(tier1) == 4
            assert len(tier2) == 3
            assert len(tier3) == 3
            assert len(tier4) == 5

            expected = {
                "orchestrator", "project_analysis",
                "test_strategy", "test_case_generator",
                "automation_generator", "browser_execution",
                "api_validation", "security_testing",
                "performance", "database_validation",
                "bug_analysis", "memory_learning",
                "report", "feature_discovery",
                "requirement_intelligence",
            }
            registered = {r.name for r in fresh.get_all_enabled()}
            assert registered == expected

        finally:
            reg_mod.agent_registry = orig
            setup_mod.agent_registry = orig
