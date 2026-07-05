"""
AIQE GitHub Event Parser.

Reads the GitHub Actions event.json file and extracts
the information AIQE needs to run a PR quality scan.

GitHub Actions sets the GITHUB_EVENT_PATH environment variable
to the path of a JSON file containing the full webhook payload
for the event that triggered the workflow.

Why parse the event file instead of using environment variables?
    Environment variables in GitHub Actions carry basic info
    (PR number, repo name, ref). The event.json file contains
    the full PR payload — changed files, author, labels,
    base/head SHAs, PR title, and more. We need this for
    context-aware quality scanning.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GitHubEventContext:
    """
    Extracted context from a GitHub Actions event.

    Attributes:
        event_name: The GitHub event name (pull_request, push, etc.)
        action: The specific action within the event (opened, synchronize, etc.)
        repository: Repository full name (owner/repo).
        pr_number: Pull Request number (None for non-PR events).
        pr_title: Pull Request title.
        pr_body: Pull Request description.
        head_sha: SHA of the head commit being tested.
        base_sha: SHA of the base branch commit.
        head_branch: Branch name being tested.
        base_branch: Base branch name (e.g. main).
        author: PR author's GitHub username.
        labels: PR label names.
        is_draft: Whether the PR is a draft.
        is_mergeable: Whether GitHub reports the PR as mergeable.
        changed_files: List of changed file paths (from git diff).
        additions: Total lines added.
        deletions: Total lines deleted.
        raw_payload: The complete event JSON payload.
    """
    event_name: str = ""
    action: str = ""
    repository: str = ""
    pr_number: int | None = None
    pr_title: str = ""
    pr_body: str = ""
    head_sha: str = ""
    base_sha: str = ""
    head_branch: str = ""
    base_branch: str = ""
    author: str = ""
    labels: list[str] = field(default_factory=list)
    is_draft: bool = False
    is_mergeable: bool = True
    changed_files: list[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    raw_payload: dict[str, Any] = field(default_factory=dict)

    @property
    def is_pull_request(self) -> bool:
        """True if this event is for a Pull Request."""
        return self.pr_number is not None

    @property
    def short_sha(self) -> str:
        """First 8 characters of the head SHA."""
        return self.head_sha[:8] if self.head_sha else ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_name": self.event_name,
            "action": self.action,
            "repository": self.repository,
            "pr_number": self.pr_number,
            "pr_title": self.pr_title,
            "head_sha": self.head_sha,
            "base_sha": self.base_sha,
            "head_branch": self.head_branch,
            "base_branch": self.base_branch,
            "author": self.author,
            "labels": self.labels,
            "is_draft": self.is_draft,
            "changed_files": self.changed_files,
            "additions": self.additions,
            "deletions": self.deletions,
        }


class GitHubEventParser:
    """
    Parses GitHub Actions event context.

    Reads from:
        1. GITHUB_EVENT_PATH file (primary — full webhook payload)
        2. Environment variables (fallback — basic context)
    """

    def parse(self) -> GitHubEventContext:
        """
        Parse the current GitHub Actions event.

        Returns:
            GitHubEventContext with all available event data.
        """
        context = GitHubEventContext()

        # Read event name from environment
        context.event_name = os.environ.get("GITHUB_EVENT_NAME", "")
        context.repository = os.environ.get("GITHUB_REPOSITORY", "")
        context.head_sha = os.environ.get("GITHUB_SHA", "")
        context.head_branch = os.environ.get("GITHUB_HEAD_REF", "") or \
                              os.environ.get("GITHUB_REF_NAME", "")

        # Read from AIQE-specific env vars set by action.yml
        if not context.pr_number:
            pr_num_str = os.environ.get("AIQE_PR_NUMBER", "")
            if pr_num_str.isdigit():
                context.pr_number = int(pr_num_str)

        if not context.repository:
            context.repository = os.environ.get("AIQE_REPOSITORY", "")

        if not context.head_branch:
            context.head_branch = os.environ.get("AIQE_BRANCH", "")

        if not context.head_sha:
            context.head_sha = os.environ.get("AIQE_COMMIT_SHA", "")

        # Read full event payload if available
        event_path = os.environ.get("GITHUB_EVENT_PATH", "")
        if event_path and Path(event_path).exists():
            try:
                payload = json.loads(
                    Path(event_path).read_text(encoding="utf-8")
                )
                context.raw_payload = payload
                self._extract_from_payload(context, payload)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(
                    "github_event_parse_failed",
                    event_path=event_path,
                    error=str(e),
                )

        # Parse changed files from git if in a git repo
        context.changed_files = self._get_changed_files(
            context.base_sha, context.head_sha
        )

        logger.info(
            "github_event_parsed",
            event_name=context.event_name,
            repository=context.repository,
            pr_number=context.pr_number,
            head_branch=context.head_branch,
            changed_files=len(context.changed_files),
        )

        return context

    def _extract_from_payload(
        self,
        context: GitHubEventContext,
        payload: dict[str, Any],
    ) -> None:
        """Extract fields from the full GitHub event payload."""
        context.action = payload.get("action", "")

        pr = payload.get("pull_request", {})
        if pr:
            context.pr_number = payload.get("number") or pr.get("number")
            context.pr_title = pr.get("title", "")
            context.pr_body = pr.get("body", "") or ""
            context.is_draft = pr.get("draft", False)
            context.is_mergeable = pr.get("mergeable", True) or True
            context.additions = pr.get("additions", 0)
            context.deletions = pr.get("deletions", 0)

            head = pr.get("head", {})
            if head:
                context.head_sha = head.get("sha", context.head_sha)
                context.head_branch = head.get("ref", context.head_branch)

            base = pr.get("base", {})
            if base:
                context.base_sha = base.get("sha", "")
                context.base_branch = base.get("ref", "")

            user = pr.get("user", {})
            if user:
                context.author = user.get("login", "")

            labels = pr.get("labels", [])
            context.labels = [
                label.get("name", "") for label in labels
                if label.get("name")
            ]

        repo = payload.get("repository", {})
        if repo and not context.repository:
            context.repository = repo.get("full_name", "")

    def _get_changed_files(
        self,
        base_sha: str,
        head_sha: str,
    ) -> list[str]:
        """
        Get the list of files changed between two commits.

        Uses git diff to get accurate changed file list.
        Falls back to empty list if git is unavailable.

        Args:
            base_sha: Base commit SHA.
            head_sha: Head commit SHA.

        Returns:
            List of relative file paths that changed.
        """
        if not base_sha or not head_sha:
            return []

        try:
            import subprocess
            result = subprocess.run(
                ["git", "diff", "--name-only", base_sha, head_sha],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                files = [
                    f.strip()
                    for f in result.stdout.splitlines()
                    if f.strip()
                ]
                logger.info(
                    "changed_files_detected",
                    count=len(files),
                )
                return files
        except Exception as e:
            logger.warning(
                "git_diff_failed",
                error=str(e),
            )

        return []
