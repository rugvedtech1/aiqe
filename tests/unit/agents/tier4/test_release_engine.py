"""Unit tests for Release Intelligence Engine."""
import pytest
from aiqe.intelligence.release_engine import (
    ReleaseIntelligenceEngine,
    ReleaseAssessment,
)


@pytest.fixture
def engine():
    return ReleaseIntelligenceEngine()


@pytest.fixture
def critical_bug():
    return {
        "id": "bug_001",
        "title": "SQL Injection",
        "severity": "Critical",
        "confidence": 0.97,
        "affected_feature": "auth",
        "suggested_fix": "Use parameterised queries",
        "is_downstream": False,
    }


@pytest.fixture
def high_bug():
    return {
        "id": "bug_002",
        "title": "XSS in output",
        "severity": "High",
        "confidence": 0.85,
        "affected_feature": "ui",
        "suggested_fix": "Escape HTML output",
        "is_downstream": False,
    }


@pytest.fixture
def workflow_summary():
    return {
        "agents_completed": 8,
        "agents_skipped": 0,
    }


@pytest.fixture
def project_analysis():
    return {
        "language": "python",
        "framework": "fastapi",
    }


class TestReleaseIntelligenceEngine:
    def test_no_bugs_is_safe(self, engine, workflow_summary, project_analysis):
        assessment = engine.assess(
            bugs=[],
            memory_learning={},
            project_analysis=project_analysis,
            workflow_summary=workflow_summary,
            changed_files=["src/main.py"],
            test_strategy={},
        )
        assert assessment.is_safe_to_merge is True
        assert assessment.release_risk == "Safe"

    def test_critical_bug_blocks_merge(
        self, engine, critical_bug, workflow_summary, project_analysis
    ):
        assessment = engine.assess(
            bugs=[critical_bug],
            memory_learning={},
            project_analysis=project_analysis,
            workflow_summary=workflow_summary,
            changed_files=["src/auth.py"],
            test_strategy={},
        )
        assert assessment.is_safe_to_merge is False
        assert assessment.release_risk == "Critical"

    def test_high_bug_blocks_merge(
        self, engine, high_bug, workflow_summary, project_analysis
    ):
        assessment = engine.assess(
            bugs=[high_bug],
            memory_learning={},
            project_analysis=project_analysis,
            workflow_summary=workflow_summary,
            changed_files=["src/ui.py"],
            test_strategy={},
        )
        assert assessment.is_safe_to_merge is False
        assert assessment.release_risk == "High"

    def test_medium_bug_does_not_block(
        self, engine, workflow_summary, project_analysis
    ):
        medium_bug = {
            "id": "bug_003", "title": "Minor issue",
            "severity": "Medium", "confidence": 0.6,
            "affected_feature": "ui", "suggested_fix": "Fix it",
        }
        assessment = engine.assess(
            bugs=[medium_bug],
            memory_learning={},
            project_analysis=project_analysis,
            workflow_summary=workflow_summary,
            changed_files=["src/ui.py"],
            test_strategy={},
        )
        assert assessment.is_safe_to_merge is True
        assert assessment.release_risk == "Medium"

    def test_regression_blocks_merge(
        self, engine, workflow_summary, project_analysis
    ):
        assessment = engine.assess(
            bugs=[],
            memory_learning={
                "regressions_detected": [
                    {"title": "Login broken again", "severity": "High"}
                ]
            },
            project_analysis=project_analysis,
            workflow_summary=workflow_summary,
            changed_files=["src/auth.py"],
            test_strategy={},
        )
        assert assessment.is_safe_to_merge is False
        assert assessment.regression_detected is True

    def test_fix_priority_is_ordered_by_severity(
        self, engine, critical_bug, high_bug, workflow_summary, project_analysis
    ):
        assessment = engine.assess(
            bugs=[high_bug, critical_bug],
            memory_learning={},
            project_analysis=project_analysis,
            workflow_summary=workflow_summary,
            changed_files=[],
            test_strategy={},
        )
        if len(assessment.fix_priority) >= 2:
            assert assessment.fix_priority[0]["severity"] == "Critical"

    def test_always_has_human_review_gate_note(
        self, engine, workflow_summary, project_analysis
    ):
        assessment = engine.assess(
            bugs=[],
            memory_learning={},
            project_analysis=project_analysis,
            workflow_summary=workflow_summary,
            changed_files=[],
            test_strategy={},
        )
        gate_notes = [
            note for note in assessment.human_review_notes
            if "AIQE" in note or "human" in note.lower()
        ]
        assert len(gate_notes) > 0

    def test_blocking_and_non_blocking_classified(
        self, engine, critical_bug, workflow_summary, project_analysis
    ):
        medium = {
            "id": "m1", "title": "Medium issue",
            "severity": "Medium", "confidence": 0.6,
            "affected_feature": "ui", "suggested_fix": "Fix",
        }
        assessment = engine.assess(
            bugs=[critical_bug, medium],
            memory_learning={},
            project_analysis=project_analysis,
            workflow_summary=workflow_summary,
            changed_files=[],
            test_strategy={},
        )
        assert len(assessment.blocking_issues) == 1
        assert len(assessment.non_blocking_issues) == 1

    def test_to_dict(self, engine, workflow_summary, project_analysis):
        assessment = engine.assess(
            bugs=[], memory_learning={},
            project_analysis=project_analysis,
            workflow_summary=workflow_summary,
            changed_files=[], test_strategy={},
        )
        d = assessment.to_dict()
        assert "is_safe_to_merge" in d
        assert "release_risk" in d
        assert "risk_reasoning" in d
        assert "fix_priority" in d
        assert "human_review_notes" in d
        assert "blocking_issues" in d
        assert "non_blocking_issues" in d
