"""Unit tests for CLI console output functions."""
import pytest
from unittest.mock import patch
from aiqe.cli.console import (
    print_success,
    print_error,
    print_warning,
    print_info,
    print_workflow_summary,
    print_bug_table,
    print_agent_table,
    print_plugin_table,
)


class TestConsoleHelpers:
    def test_print_success_does_not_raise(self):
        with patch("aiqe.cli.console.console") as mock_console:
            print_success("Operation complete")
            mock_console.print.assert_called_once()

    def test_print_error_uses_error_console(self):
        with patch("aiqe.cli.console.error_console") as mock_console:
            print_error("Something failed")
            mock_console.print.assert_called_once()

    def test_print_workflow_summary_with_full_data(self):
        summary = {
            "id": "wf-abc123",
            "status": "completed",
            "repository": "owner/repo",
            "branch": "main",
            "trigger": "pr",
            "pr_number": 42,
            "duration_seconds": 120.5,
            "bugs_count": 3,
            "agents_completed": 8,
            "agents_skipped": 2,
        }
        with patch("aiqe.cli.console.console"):
            print_workflow_summary(summary)

    def test_print_bug_table_empty(self):
        with patch("aiqe.cli.console.console") as mock_console:
            print_bug_table([])

    def test_print_bug_table_with_bugs(self):
        bugs = [
            {
                "severity": "Critical",
                "confidence": 0.97,
                "title": "SQL Injection",
                "affected_feature": "auth",
            },
            {
                "severity": "High",
                "confidence": 0.85,
                "title": "XSS Vulnerability",
                "affected_feature": "ui",
            },
        ]
        with patch("aiqe.cli.console.console"):
            print_bug_table(bugs)

    def test_print_agent_table_with_skipped(self):
        records = {
            "orchestrator": {
                "status": "completed",
                "duration_seconds": 0.5,
                "ai_tokens_used": 0,
            },
            "test_strategy": {
                "status": "skipped",
                "duration_seconds": 0,
                "ai_tokens_used": 0,
                "skip_reason": "Dependency 'project_analysis' failed",
            },
        }
        with patch("aiqe.cli.console.console"):
            print_agent_table(records)
