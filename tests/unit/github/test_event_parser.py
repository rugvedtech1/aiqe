"""Unit tests for GitHub event parser."""
import json
import os
import pytest
from pathlib import Path
from aiqe.github.event_parser import GitHubEventParser, GitHubEventContext


class TestGitHubEventContext:
    def test_is_pull_request_true(self):
        ctx = GitHubEventContext(pr_number=42)
        assert ctx.is_pull_request is True

    def test_is_pull_request_false(self):
        ctx = GitHubEventContext(pr_number=None)
        assert ctx.is_pull_request is False

    def test_short_sha(self):
        ctx = GitHubEventContext(head_sha="abc1234567890")
        assert ctx.short_sha == "abc12345"

    def test_short_sha_empty(self):
        ctx = GitHubEventContext(head_sha="")
        assert ctx.short_sha == ""

    def test_to_dict(self):
        ctx = GitHubEventContext(
            event_name="pull_request",
            repository="owner/repo",
            pr_number=42,
            head_branch="feature/test",
        )
        d = ctx.to_dict()
        assert d["event_name"] == "pull_request"
        assert d["repository"] == "owner/repo"
        assert d["pr_number"] == 42


class TestGitHubEventParser:
    def test_parse_from_env_vars(self, monkeypatch):
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.setenv("AIQE_PR_NUMBER", "42")
        monkeypatch.setenv("AIQE_BRANCH", "feature/auth")
        monkeypatch.setenv("AIQE_COMMIT_SHA", "abc1234")

        parser = GitHubEventParser()
        ctx = parser.parse()

        assert ctx.event_name == "pull_request"
        assert ctx.repository == "owner/repo"
        assert ctx.pr_number == 42
        assert ctx.head_branch == "feature/auth"

    def test_parse_from_event_file(self, tmp_path, monkeypatch):
        payload = {
            "action": "opened",
            "number": 7,
            "pull_request": {
                "title": "Add auth feature",
                "body": "Implements JWT auth",
                "draft": False,
                "head": {
                    "sha": "def456",
                    "ref": "feature/jwt",
                },
                "base": {
                    "sha": "abc123",
                    "ref": "main",
                },
                "user": {"login": "developer"},
                "labels": [{"name": "enhancement"}],
                "additions": 150,
                "deletions": 20,
            },
            "repository": {"full_name": "myorg/myapp"},
        }
        event_file = tmp_path / "event.json"
        event_file.write_text(json.dumps(payload))

        monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_file))
        monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")

        parser = GitHubEventParser()
        ctx = parser.parse()

        assert ctx.action == "opened"
        assert ctx.pr_number == 7
        assert ctx.pr_title == "Add auth feature"
        assert ctx.head_branch == "feature/jwt"
        assert ctx.base_branch == "main"
        assert ctx.author == "developer"
        assert "enhancement" in ctx.labels
        assert ctx.additions == 150

    def test_parse_non_pr_event(self, monkeypatch):
        monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
        monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
        monkeypatch.delenv("AIQE_PR_NUMBER", raising=False)

        parser = GitHubEventParser()
        ctx = parser.parse()

        assert ctx.event_name == "push"
        assert ctx.pr_number is None
        assert not ctx.is_pull_request
