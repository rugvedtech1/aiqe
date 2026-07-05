"""Unit tests for agent type contracts."""
import pytest
from aiqe.agents.types import (
    AgentInput,
    AgentOutput,
    BugReport,
    BugSeverity,
    Evidence,
    ProjectAnalysisOutput,
    ReleaseRisk,
    TestStrategyOutput,
)


class TestEvidence:
    def test_construction(self):
        e = Evidence(
            kind="log",
            content="Error: 500 Internal Server Error",
            source="/var/log/app.log",
            relevance="Shows the server crashed during login.",
        )
        assert e.kind == "log"
        assert e.source == "/var/log/app.log"

    def test_immutable(self):
        e = Evidence(kind="log", content="x", source="y")
        with pytest.raises((AttributeError, TypeError)):
            e.kind = "screenshot"  # type: ignore


class TestAgentOutput:
    def test_default_construction(self):
        output = AgentOutput()
        assert output.success is True
        assert output.error is None
        assert output.confidence == 1.0
        assert output.evidence == []
        assert output.warnings == []

    def test_add_evidence(self):
        output = AgentOutput()
        output.add_evidence(
            kind="code_snippet",
            content="def login(): pass",
            source="app/auth.py",
            relevance="Missing authentication check.",
        )
        assert len(output.evidence) == 1
        assert output.evidence[0].kind == "code_snippet"

    def test_add_warning(self):
        output = AgentOutput()
        output.add_warning("Test coverage below 80%")
        assert len(output.warnings) == 1

    def test_to_dict(self):
        output = AgentOutput()
        output.reasoning = "Because X implies Y."
        output.add_evidence("log", "error msg", "app.log")
        d = output.to_dict()
        assert d["success"] is True
        assert d["reasoning"] == "Because X implies Y."
        assert len(d["evidence"]) == 1


class TestBugSeverity:
    def test_all_levels_exist(self):
        assert BugSeverity.CRITICAL == "Critical"
        assert BugSeverity.HIGH == "High"
        assert BugSeverity.MEDIUM == "Medium"
        assert BugSeverity.LOW == "Low"
        assert BugSeverity.INFORMATIONAL == "Informational"


class TestBugReport:
    def test_to_dict_complete(self):
        bug = BugReport(
            id="bug_001",
            title="SQL Injection in login",
            severity=BugSeverity.CRITICAL,
            confidence=0.97,
            root_cause="Unsanitised user input passed to SQL query.",
            affected_feature="authentication",
            affected_files=["app/auth.py"],
            suggested_fix="Use parameterised queries.",
            fix_confidence=0.95,
        )
        d = bug.to_dict()
        assert d["severity"] == "Critical"
        assert d["confidence"] == 0.97
        assert d["affected_files"] == ["app/auth.py"]

    def test_downstream_bug(self):
        bug = BugReport(
            id="bug_002",
            title="User session not invalidated",
            severity=BugSeverity.HIGH,
            confidence=0.82,
            is_downstream=True,
            root_bug_id="bug_001",
        )
        d = bug.to_dict()
        assert d["is_downstream"] is True
        assert d["root_bug_id"] == "bug_001"


class TestProjectAnalysisOutput:
    def test_construction_with_defaults(self):
        output = ProjectAnalysisOutput()
        assert output.language == ""
        assert output.framework == ""
        assert output.dependencies == []
        assert output.success is True

    def test_full_construction(self):
        output = ProjectAnalysisOutput(
            language="python",
            framework="fastapi",
            test_framework="pytest",
            package_manager="pip",
            has_docker=True,
            has_ci=True,
            source_files_count=42,
        )
        assert output.language == "python"
        assert output.has_docker is True
