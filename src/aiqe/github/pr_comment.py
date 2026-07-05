"""
AIQE GitHub PR Comment Builder and Poster.

Builds a structured Markdown comment summarising the AIQE
quality scan results and posts it to the GitHub Pull Request.

Comment design principles:
    - Start with a clear pass/fail status the reviewer sees first.
    - Show the Human Review Gate statement explicitly (ADR-009/ADR-010).
    - Group bugs by severity, Critical first.
    - Show evidence for every bug (ADR-011 explainability).
    - Keep the comment concise — link to the full report artifact.
    - Use GitHub Markdown features: collapsible sections, tables, emojis.
    - Never mention specific AI provider names in public comments.

Security:
    - Never include API keys, credentials, or secrets in comments.
    - Never include internal file paths that reveal infrastructure.
    - PR descriptions are public — treat all content as public.
"""

from __future__ import annotations

import os
from typing import Any

from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

# Severity emoji map
_SEVERITY_EMOJI = {
    "Critical": "🔴",
    "High": "🟠",
    "Medium": "🟡",
    "Low": "🔵",
    "Informational": "⚪",
}

# Status emoji
_STATUS_EMOJI = {
    "completed": "✅",
    "failed": "❌",
    "running": "🔄",
}


class PRCommentBuilder:
    """
    Builds the AIQE quality report Markdown comment for a PR.

    Args:
        workflow_summary: WorkflowContext.to_dict() output.
        bugs: List of bug report dicts.
        event_context: GitHub event context.
        is_safe_to_merge: AIQE's recommendation.
        release_risk: Overall release risk level.
    """

    def __init__(
        self,
        workflow_summary: dict[str, Any],
        bugs: list[dict[str, Any]],
        event_context: Any,
        is_safe_to_merge: bool = True,
        release_risk: str = "Low",
    ) -> None:
        self._summary = workflow_summary
        self._bugs = bugs
        self._event = event_context
        self._is_safe = is_safe_to_merge
        self._risk = release_risk

    def build(self) -> str:
        """Build the complete PR comment Markdown."""
        sections = [
            self._build_header(),
            self._build_status_badge(),
            self._build_human_review_gate(),
            self._build_summary_table(),
        ]

        if self._bugs:
            sections.append(self._build_bugs_section())
        else:
            sections.append(self._build_no_bugs_section())

        sections.append(self._build_agent_summary())
        sections.append(self._build_footer())

        return "\n\n".join(sections)

    def _build_header(self) -> str:
        status = self._summary.get("status", "unknown")
        status_emoji = _STATUS_EMOJI.get(status, "❓")
        return (
            f"## {status_emoji} AIQE Quality Report\n"
            f"**Workflow:** `{self._summary.get('id', 'N/A')[:16]}...`  \n"
            f"**Branch:** `{self._event.head_branch}`  \n"
            f"**Commit:** `{self._event.short_sha}`  \n"
            f"**Changed Files:** {len(self._event.changed_files)}"
        )

    def _build_status_badge(self) -> str:
        if self._is_safe:
            return (
                "### ✅ AIQE Recommendation: Safe to Review\n"
                f"> Release Risk: **{self._risk}**  \n"
                "> No blocking issues were found. "
                "Human review is still required."
            )
        else:
            critical = sum(
                1 for b in self._bugs
                if b.get("severity") == "Critical"
            )
            high = sum(
                1 for b in self._bugs
                if b.get("severity") == "High"
            )
            return (
                "### ⚠️ AIQE Recommendation: Review Required\n"
                f"> Release Risk: **{self._risk}**  \n"
                f"> Found **{critical} Critical** and "
                f"**{high} High** severity issues.  \n"
                "> Address these before merging."
            )

    def _build_human_review_gate(self) -> str:
        return (
            "> 🔐 **Human Review Gate**  \n"
            "> AIQE provides recommendations and evidence. "
            "The final merge decision always belongs to your team.  \n"
            "> AIQE never modifies production code automatically."
        )

    def _build_summary_table(self) -> str:
        # Count bugs by severity
        severity_counts: dict[str, int] = {}
        for bug in self._bugs:
            sev = bug.get("severity", "Unknown")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        from aiqe.shared.utils import format_duration
        duration = self._summary.get("duration_seconds")
        duration_str = (
            format_duration(duration)
            if duration else "N/A"
        )

        rows = [
            "| Metric | Value |",
            "|--------|-------|",
            f"| Total Bugs | **{len(self._bugs)}** |",
            f"| 🔴 Critical | {severity_counts.get('Critical', 0)} |",
            f"| 🟠 High | {severity_counts.get('High', 0)} |",
            f"| 🟡 Medium | {severity_counts.get('Medium', 0)} |",
            f"| 🔵 Low | {severity_counts.get('Low', 0)} |",
            f"| Agents Completed | {self._summary.get('agents_completed', 0)} |",
            f"| Agents Skipped | {self._summary.get('agents_skipped', 0)} |",
            f"| Duration | {duration_str} |",
        ]
        return "\n".join(rows)

    def _build_bugs_section(self) -> str:
        severity_order = {
            "Critical": 0, "High": 1,
            "Medium": 2, "Low": 3, "Informational": 4,
        }
        sorted_bugs = sorted(
            self._bugs,
            key=lambda b: severity_order.get(b.get("severity", ""), 99),
        )

        # Show all Critical/High inline, collapse Medium/Low
        critical_high = [
            b for b in sorted_bugs
            if b.get("severity") in {"Critical", "High"}
        ]
        medium_low = [
            b for b in sorted_bugs
            if b.get("severity") not in {"Critical", "High"}
        ]

        lines = ["### 🐛 Issues Found"]

        for bug in critical_high:
            lines.append(self._format_bug(bug))

        if medium_low:
            lines.append(
                f"\n<details>\n"
                f"<summary>📋 {len(medium_low)} lower-severity issues "
                f"(click to expand)</summary>\n"
            )
            for bug in medium_low:
                lines.append(self._format_bug(bug))
            lines.append("</details>")

        return "\n".join(lines)

    def _format_bug(self, bug: dict[str, Any]) -> str:
        """Format a single bug report for the PR comment."""
        severity = bug.get("severity", "Unknown")
        emoji = _SEVERITY_EMOJI.get(severity, "⚪")
        confidence = bug.get("confidence", 0) * 100
        title = bug.get("title", "Unknown issue")
        root_cause = bug.get("root_cause", "")
        suggested_fix = bug.get("suggested_fix", "")
        affected_feature = bug.get("affected_feature", "")
        fix_confidence = bug.get("fix_confidence", 0) * 100

        lines = [
            f"\n#### {emoji} [{severity}] {title}",
            f"- **Feature:** {affected_feature}",
            f"- **Confidence:** {confidence:.0f}%",
        ]

        if root_cause:
            lines.append(f"- **Root Cause:** {root_cause}")

        if suggested_fix:
            lines.append(
                f"- **Suggested Fix:** {suggested_fix} "
                f"_(fix confidence: {fix_confidence:.0f}%)_"
            )

        if bug.get("is_downstream"):
            lines.append(
                f"- ℹ️ _Downstream effect of bug "
                f"`{bug.get('root_bug_id', 'N/A')[:8]}`_"
            )

        evidence = bug.get("evidence", [])
        if evidence:
            lines.append(
                f"\n<details><summary>📎 Evidence "
                f"({len(evidence)} item(s))</summary>\n"
            )
            for ev in evidence[:3]:
                lines.append(
                    f"- **{ev.get('kind', 'evidence')}** "
                    f"from `{ev.get('source', 'unknown')}`  \n"
                    f"  _{ev.get('relevance', '')}_"
                )
            lines.append("</details>")

        return "\n".join(lines)

    def _build_no_bugs_section(self) -> str:
        return (
            "### ✅ No Issues Found\n"
            "AIQE did not detect any quality issues in this PR.  \n"
            "This does not guarantee the absence of all bugs — "
            "human review and domain expertise remain important."
        )

    def _build_agent_summary(self) -> str:
        agent_records = self._summary.get("agent_records", {})
        if not agent_records:
            return ""

        completed = sum(
            1 for r in agent_records.values()
            if r.get("status") == "completed"
        )
        failed = sum(
            1 for r in agent_records.values()
            if r.get("status") == "failed"
        )
        skipped = sum(
            1 for r in agent_records.values()
            if r.get("status") == "skipped"
        )

        return (
            f"<details>\n"
            f"<summary>🤖 Agent Execution Summary "
            f"({completed} completed, {failed} failed, "
            f"{skipped} skipped)</summary>\n\n"
            f"| Agent | Status |\n"
            f"|-------|--------|\n"
            + "\n".join(
                f"| {name} | {rec.get('status', 'unknown').upper()} |"
                for name, rec in agent_records.items()
            )
            + "\n\n</details>"
        )

    def _build_footer(self) -> str:
        return (
            "---\n"
            "_Generated by [AIQE](https://github.com/rugvedtech1/aiqe) "
            f"— AI Quality Engineering Operating System  \n"
            "AIQE provides quality intelligence. "
            "Release decisions require human approval._"
        )


class GitHubPRCommenter:
    """
    Posts and updates AIQE quality report comments on GitHub PRs.

    Uses the GitHub REST API to post or update a PR comment.
    Finds an existing AIQE comment and updates it (instead of
    creating a new comment every run) to avoid cluttering the PR.

    Args:
        github_token: GitHub personal access token or GITHUB_TOKEN.
        repository: Repository full name (owner/repo).
        pr_number: Pull Request number.
    """

    COMMENT_MARKER = "<!-- AIQE-QUALITY-REPORT -->"

    def __init__(
        self,
        github_token: str,
        repository: str,
        pr_number: int,
    ) -> None:
        self._token = github_token
        self._repository = repository
        self._pr_number = pr_number

    async def post_or_update(self, comment_body: str) -> bool:
        """
        Post a new comment or update an existing AIQE comment.

        Searches for an existing comment with the AIQE marker.
        Updates it if found, creates a new one if not.

        Args:
            comment_body: The Markdown comment content.

        Returns:
            True if the comment was posted/updated successfully.
        """
        import httpx

        full_body = f"{self.COMMENT_MARKER}\n{comment_body}"
        headers = {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github.v3+json",
            "Content-Type": "application/json",
        }

        # Search for existing AIQE comment
        existing_id = await self._find_existing_comment(headers)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if existing_id:
                    # Update existing comment
                    url = (
                        f"https://api.github.com/repos/"
                        f"{self._repository}/issues/comments/{existing_id}"
                    )
                    response = await client.patch(
                        url,
                        json={"body": full_body},
                        headers=headers,
                    )
                else:
                    # Create new comment
                    url = (
                        f"https://api.github.com/repos/"
                        f"{self._repository}/issues/"
                        f"{self._pr_number}/comments"
                    )
                    response = await client.post(
                        url,
                        json={"body": full_body},
                        headers=headers,
                    )

                if response.status_code in {200, 201}:
                    action = "updated" if existing_id else "created"
                    logger.info(
                        f"pr_comment_{action}",
                        repository=self._repository,
                        pr_number=self._pr_number,
                    )
                    return True
                else:
                    logger.error(
                        "pr_comment_failed",
                        status_code=response.status_code,
                        repository=self._repository,
                        pr_number=self._pr_number,
                    )
                    return False

        except Exception as e:
            logger.error(
                "pr_comment_error",
                error=str(e),
                repository=self._repository,
                pr_number=self._pr_number,
            )
            return False

    async def _find_existing_comment(
        self, headers: dict[str, str]
    ) -> int | None:
        """Find an existing AIQE comment to update."""
        import httpx

        try:
            url = (
                f"https://api.github.com/repos/"
                f"{self._repository}/issues/"
                f"{self._pr_number}/comments"
            )
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, headers=headers)

            if response.status_code != 200:
                return None

            comments = response.json()
            for comment in comments:
                if self.COMMENT_MARKER in comment.get("body", ""):
                    return comment["id"]
        except Exception as e:
            logger.warning(
                "find_existing_comment_failed",
                error=str(e),
            )

        return None
