"""Unit tests for PR comment builder."""
import pytest
from aiqe.github.pr_comment import PRCommentBuilder
from aiqe.github.event_parser import GitHubEventContext


@pytest.fixture
def event_context():
    return GitHubEventContext(
        event_name="pull_request",
        repository="owner/repo",
        pr_number=42,
        head_branch="feature/auth",
        head_sha="abc1234567890",
        changed_files=["src/auth.py", "tests/test_auth.py"],
    )


@pytest.fixture
def workflow_summary():
    return {
        "id": "wf-abc123-def456-789",
        "status": "completed",
        "repository": "owner/repo",
        "branch": "feature/auth",
        "agents_completed": 4,
        "agents_skipped": 0,
        "duration_seconds": 45.2,
        "agent_records": {
            "orchestrator": {"status": "completed"},
            "project_analysis": {"status": "completed"},
        },
    }


@pytest.fixture
def sample_bugs():
    return [
        {
            "id": "bug_001",
            "severity": "Critical",
            "confidence": 0.97,
            "title": "SQL Injection in login endpoint",
            "root_cause": "Unsanitised user input in SQL query",
            "affected_feature": "authentication",
            "suggested_fix": "Use parameterised queries",
            "fix_confidence": 0.95,
            "is_downstream": False,
            "evidence": [
                {
                    "kind": "code_snippet",
                    "content": "query = f'SELECT * FROM users WHERE id={user_id}'",
                    "source": "src/auth.py:42",
                    "relevance": "Direct string interpolation in SQL query",
                }
            ],
        },
        {
            "id": "bug_002",
            "severity": "Medium",
            "confidence": 0.72,
            "title": "Missing input validation on email field",
            "root_cause": "No regex validation before database insert",
            "affected_feature": "user-registration",
            "suggested_fix": "Add email format validation",
            "fix_confidence": 0.88,
            "is_downstream": False,
            "evidence": [],
        },
    ]


class TestPRCommentBuilder:
    def test_build_returns_string(
        self, workflow_summary, event_context
    ):
        builder = PRCommentBuilder(
            workflow_summary=workflow_summary,
            bugs=[],
            event_context=event_context,
        )
        comment = builder.build()
        assert isinstance(comment, str)
        assert len(comment) > 0

    def test_comment_contains_workflow_id(
        self, workflow_summary, event_context
    ):
        builder = PRCommentBuilder(
            workflow_summary=workflow_summary,
            bugs=[],
            event_context=event_context,
        )
        comment = builder.build()
        assert "wf-abc123" in comment

    def test_safe_to_merge_shows_success(
        self, workflow_summary, event_context
    ):
        builder = PRCommentBuilder(
            workflow_summary=workflow_summary,
            bugs=[],
            event_context=event_context,
            is_safe_to_merge=True,
            release_risk="Safe",
        )
        comment = builder.build()
        assert "Safe to Review" in comment or "✅" in comment

    def test_unsafe_to_merge_shows_warning(
        self, workflow_summary, event_context, sample_bugs
    ):
        builder = PRCommentBuilder(
            workflow_summary=workflow_summary,
            bugs=sample_bugs,
            event_context=event_context,
            is_safe_to_merge=False,
            release_risk="Critical",
        )
        comment = builder.build()
        assert "Review Required" in comment or "⚠️" in comment

    def test_comment_contains_human_review_gate(
        self, workflow_summary, event_context
    ):
        builder = PRCommentBuilder(
            workflow_summary=workflow_summary,
            bugs=[],
            event_context=event_context,
        )
        comment = builder.build()
        assert "Human Review Gate" in comment

    def test_comment_contains_bugs(
        self, workflow_summary, event_context, sample_bugs
    ):
        builder = PRCommentBuilder(
            workflow_summary=workflow_summary,
            bugs=sample_bugs,
            event_context=event_context,
            is_safe_to_merge=False,
        )
        comment = builder.build()
        assert "SQL Injection" in comment
        assert "Critical" in comment
        assert "97%" in comment

    def test_comment_contains_evidence(
        self, workflow_summary, event_context, sample_bugs
    ):
        builder = PRCommentBuilder(
            workflow_summary=workflow_summary,
            bugs=sample_bugs,
            event_context=event_context,
        )
        comment = builder.build()
        assert "Evidence" in comment or "evidence" in comment

    def test_no_bugs_shows_success_message(
        self, workflow_summary, event_context
    ):
        builder = PRCommentBuilder(
            workflow_summary=workflow_summary,
            bugs=[],
            event_context=event_context,
            is_safe_to_merge=True,
        )
        comment = builder.build()
        assert "No Issues Found" in comment

    def test_comment_contains_aiqe_marker_note(
        self, workflow_summary, event_context
    ):
        builder = PRCommentBuilder(
            workflow_summary=workflow_summary,
            bugs=[],
            event_context=event_context,
        )
        comment = builder.build()
        assert "AIQE" in comment

    def test_medium_low_bugs_in_collapsible(
        self, workflow_summary, event_context
    ):
        medium_bugs = [
            {
                "id": "bug_m1",
                "severity": "Medium",
                "confidence": 0.7,
                "title": "Medium severity issue",
                "root_cause": "Root cause",
                "affected_feature": "core",
                "suggested_fix": "Fix suggestion",
                "fix_confidence": 0.6,
                "is_downstream": False,
                "evidence": [],
            }
        ]
        builder = PRCommentBuilder(
            workflow_summary=workflow_summary,
            bugs=medium_bugs,
            event_context=event_context,
        )
        comment = builder.build()
        assert "<details>" in comment


class TestExitCodeCalculation:
    def test_no_bugs_exit_zero(self):
        from aiqe.github.action_runner import _get_exit_code
        assert _get_exit_code({}, "High") == 0

    def test_critical_bug_exits_two(self):
        from aiqe.github.action_runner import _get_exit_code
        assert _get_exit_code({"Critical": 1}, "High") == 2

    def test_high_bug_exits_two_when_fail_on_high(self):
        from aiqe.github.action_runner import _get_exit_code
        assert _get_exit_code({"High": 1}, "High") == 2

    def test_high_bug_exits_zero_when_fail_on_critical_only(self):
        from aiqe.github.action_runner import _get_exit_code
        assert _get_exit_code({"High": 1}, "Critical") == 0

    def test_medium_bug_exits_zero_when_fail_on_high(self):
        from aiqe.github.action_runner import _get_exit_code
        assert _get_exit_code({"Medium": 5}, "High") == 0

    def test_never_always_exits_zero(self):
        from aiqe.github.action_runner import _get_exit_code
        assert _get_exit_code({"Critical": 10}, "never") == 0


class TestReleaseRisk:
    def test_critical_bug_critical_risk(self):
        from aiqe.github.action_runner import _calculate_release_risk
        assert _calculate_release_risk({"Critical": 1}) == "Critical"

    def test_high_bug_high_risk(self):
        from aiqe.github.action_runner import _calculate_release_risk
        assert _calculate_release_risk({"High": 2}) == "High"

    def test_no_bugs_safe(self):
        from aiqe.github.action_runner import _calculate_release_risk
        assert _calculate_release_risk({}) == "Safe"

    def test_medium_bugs_medium_risk(self):
        from aiqe.github.action_runner import _calculate_release_risk
        assert _calculate_release_risk({"Medium": 3}) == "Medium"
