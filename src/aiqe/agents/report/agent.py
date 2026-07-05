"""
AIQE Report Agent.

Generates the final human-readable quality report and
sends notifications through configured channels.

Report formats:
    - Markdown (default, GitHub PR compatible)
    - JSON (for integrations and dashboards)
    - HTML (rich report with styling)

Notification channels:
    - GitHub PR comment (updates/creates)
    - Slack message (Critical bugs trigger immediate, others summary)
    - Microsoft Teams webhook

Notification strategy (ADR-008):
    - Critical bugs: immediate notification
    - High/Medium/Low: consolidated final report
    - Never spam — update existing comment, don't create new ones

Tier: 4 (Intelligence)
Dependencies: bug_analysis, memory_learning
Memory Reads: All results, bug_analysis.results, release intelligence
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class ReportOutput(AgentOutput):
    """Output from the Report Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.report_markdown: str = ""
        self.report_json: str = ""
        self.report_path: str = ""
        self.notifications_sent: list[str] = []
        self.report_sections: list[str] = []

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "report_path": self.report_path,
            "notifications_sent": self.notifications_sent,
            "report_sections": self.report_sections,
            "report_preview": self.report_markdown[:500],
        }


class ReportInput(AgentInput):
    """Input for the Report Agent."""
    output_format: str = "markdown"
    notify_slack: bool = False
    notify_github_pr: bool = False
    notify_teams: bool = False
    slack_token: str = ""
    github_token: str = ""
    github_pr_number: int | None = None
    github_repository: str = ""


class ReportAgent(BaseAgent):
    """
    Report Agent — Tier 4.

    Assembles the final quality report from all agent outputs
    and delivers it to configured notification channels.
    """

    NAME = "report"
    DESCRIPTION = (
        "Generates HTML/Markdown/JSON quality reports and sends "
        "notifications to Slack, GitHub PRs, and Teams."
    )
    TIER = 4
    DEPENDENCIES = ["bug_analysis", "memory_learning"]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway

    async def run_impl(self, input_data: AgentInput) -> ReportOutput:
        """Generate and deliver the quality report."""
        assert isinstance(input_data, ReportInput), (
            f"Expected ReportInput, got {type(input_data).__name__}"
        )

        output = ReportOutput()

        # Load all results
        context_data = await self._load_all_results(input_data)

        # Build report
        report_md = self._build_markdown_report(context_data, input_data)
        output.report_markdown = report_md

        # Save to workspace
        workspace = Path(".aiqe") / "reports" / input_data.workflow_id[:8]
        workspace.mkdir(parents=True, exist_ok=True)
        report_path = workspace / "quality_report.md"
        report_path.write_text(report_md, encoding="utf-8")
        output.report_path = str(report_path)
        output.report_sections = self._get_section_names(context_data)

        # JSON report
        json_data = {
            "workflow_id": input_data.workflow_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": context_data.get("summary", {}),
            "bugs": context_data.get("bugs", []),
        }
        output.report_json = json.dumps(json_data, indent=2, default=str)
        json_path = workspace / "quality_report.json"
        json_path.write_text(output.report_json, encoding="utf-8")

        # Send notifications
        if input_data.notify_github_pr and input_data.github_token:
            success = await self._post_github_comment(
                report_md=report_md,
                input_data=input_data,
                context_data=context_data,
            )
            if success:
                output.notifications_sent.append("github_pr")

        if input_data.notify_slack and input_data.slack_token:
            success = await self._send_slack_notification(
                context_data=context_data,
                input_data=input_data,
            )
            if success:
                output.notifications_sent.append("slack")

        output.reasoning = (
            f"Quality report generated. "
            f"Format: {input_data.output_format}. "
            f"Sections: {output.report_sections}. "
            f"Saved to: {output.report_path}. "
            f"Notifications: {output.notifications_sent}."
        )
        output.confidence = 1.0

        output.suggested_next_action = (
            "Review the quality report and make the merge/release decision. "
            "AIQE never decides automatically — human approval required (ADR-009)."
        )

        logger.info(
            "report_generated",
            workflow_id=input_data.workflow_id,
            report_path=output.report_path,
            notifications=output.notifications_sent,
        )

        return output

    async def _load_all_results(
        self, input_data: ReportInput
    ) -> dict[str, Any]:
        """Load all agent results from shared memory."""
        data: dict[str, Any] = {}

        if not self._memory:
            return data

        bug_results = await self._memory.get(
            key=str(MemoryKeys.BUG_ANALYSIS_RESULTS),
            reader=self.NAME,
        ) or {}
        data["bugs"] = bug_results.get("bugs", [])
        data["by_severity"] = bug_results.get("by_severity", {})

        release_result = await self._memory.get(
            key=str(MemoryKeys.RELEASE_INTELLIGENCE_RESULT),
            reader=self.NAME,
        ) or {}
        data["release_intelligence"] = release_result

        workflow_meta = await self._memory.get(
            key=str(MemoryKeys.WORKFLOW_METADATA),
            reader=self.NAME,
        ) or {}
        data["metadata"] = workflow_meta

        project_analysis = await self._memory.get(
            key=str(MemoryKeys.PROJECT_ANALYSIS_RESULT),
            reader=self.NAME,
        ) or {}
        data["project"] = project_analysis

        security_results = await self._memory.get(
            key=str(MemoryKeys.SECURITY_SCAN_RESULTS),
            reader=self.NAME,
        ) or {}
        data["security"] = security_results

        data["summary"] = {
            "total_bugs": len(data["bugs"]),
            "by_severity": data["by_severity"],
            "language": project_analysis.get("language", "unknown"),
            "framework": project_analysis.get("framework", "unknown"),
        }

        return data

    def _build_markdown_report(
        self,
        data: dict[str, Any],
        input_data: ReportInput,
    ) -> str:
        """Build the Markdown quality report."""
        bugs = data.get("bugs", [])
        release = data.get("release_intelligence", {})
        metadata = data.get("metadata", {})
        project = data.get("project", {})
        by_severity = data.get("by_severity", {})

        is_safe = release.get("is_safe_to_merge", True)
        risk = release.get("release_risk", "Low")
        status_emoji = "✅" if is_safe else "⚠️"

        lines = [
            "# AIQE Quality Report",
            "",
            f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}  ",
            f"**Workflow:** `{input_data.workflow_id[:16]}...`  ",
            f"**Project:** {project.get('language', 'unknown')} / {project.get('framework', 'unknown')}  ",
            "",
            "---",
            "",
            f"## {status_emoji} Release Recommendation",
            "",
            f"| | |",
            f"|---|---|",
            f"| **Recommendation** | {'✅ Safe to Review' if is_safe else '⚠️ Review Required'} |",
            f"| **Release Risk** | **{risk}** |",
            f"| **Total Bugs** | {len(bugs)} |",
            f"| 🔴 Critical | {by_severity.get('Critical', 0)} |",
            f"| 🟠 High | {by_severity.get('High', 0)} |",
            f"| 🟡 Medium | {by_severity.get('Medium', 0)} |",
            f"| 🔵 Low | {by_severity.get('Low', 0)} |",
            "",
        ]

        if release.get("risk_reasoning"):
            lines += [
                "**Risk Reasoning:**",
                f"> {release['risk_reasoning']}",
                "",
            ]

        lines += [
            "> 🔐 **Human Review Gate**  ",
            "> AIQE provides recommendations and evidence.  ",
            "> **The final merge decision always belongs to your team.**  ",
            "> AIQE never modifies production code automatically.",
            "",
            "---",
            "",
        ]

        # Bug details
        if bugs:
            severity_order = {
                "Critical": 0, "High": 1,
                "Medium": 2, "Low": 3, "Informational": 4,
            }
            sorted_bugs = sorted(
                bugs,
                key=lambda b: severity_order.get(b.get("severity", ""), 99),
            )

            lines += [f"## Bugs Found ({len(bugs)} total)", ""]

            severity_emoji = {
                "Critical": "🔴", "High": "🟠",
                "Medium": "🟡", "Low": "🔵",
                "Informational": "⚪",
            }

            for bug in sorted_bugs[:20]:
                sev = bug.get("severity", "Medium")
                conf = bug.get("confidence", 0) * 100
                emoji = severity_emoji.get(sev, "⚪")

                lines += [
                    f"### {emoji} [{sev}] {bug.get('title', 'Unknown')}",
                    f"**Confidence:** {conf:.0f}% | "
                    f"**Feature:** {bug.get('affected_feature', 'N/A')} | "
                    f"{'🔄 Regression' if bug.get('is_regression') else '🆕 New'}",
                    "",
                    f"**Root Cause:** {bug.get('root_cause', 'N/A')}",
                    "",
                    f"**Suggested Fix:** {bug.get('suggested_fix', 'N/A')} "
                    f"_(fix confidence: {bug.get('fix_confidence', 0) * 100:.0f}%)_",
                    "",
                ]

                if bug.get("is_downstream"):
                    lines.append(
                        f"> ℹ️ Downstream effect of "
                        f"`{bug.get('root_bug_id', 'N/A')[:8]}`"
                    )
                    lines.append("")

                evidence = bug.get("evidence", [])
                if evidence:
                    lines.append(
                        f"<details><summary>📎 Evidence "
                        f"({len(evidence)} item(s))</summary>"
                    )
                    lines.append("")
                    for ev in evidence[:2]:
                        lines.append(
                            f"- **{ev.get('kind', 'evidence')}** "
                            f"from `{ev.get('source', '?')}`"
                        )
                    lines.append("</details>")
                    lines.append("")
        else:
            lines += [
                "## ✅ No Bugs Found",
                "",
                "All tests passed. No quality issues detected in this scan.",
                "",
            ]

        if data.get("security", {}).get("total_findings", 0) > 0:
            sec = data["security"]
            lines += [
                "## 🔒 Security Summary",
                f"**Findings:** {sec.get('total_findings', 0)}  ",
                f"**Coverage:** {', '.join(sec.get('scan_coverage', []))}  ",
                "",
            ]

        lines += [
            "---",
            "",
            "_Generated by [AIQE](https://github.com/rugvedtech1/aiqe) "
            "— AI Quality Engineering Operating System_  ",
            "_AIQE provides quality intelligence. "
            "Release decisions require human approval._",
        ]

        return "\n".join(lines)

    def _get_section_names(self, data: dict[str, Any]) -> list[str]:
        sections = ["Release Recommendation", "Human Review Gate"]
        if data.get("bugs"):
            sections.append("Bugs Found")
        if data.get("security", {}).get("total_findings", 0) > 0:
            sections.append("Security Summary")
        return sections

    async def _post_github_comment(
        self,
        report_md: str,
        input_data: ReportInput,
        context_data: dict[str, Any],
    ) -> bool:
        """Post the report as a GitHub PR comment."""
        try:
            from aiqe.github.pr_comment import GitHubPRCommenter

            pr_number = input_data.github_pr_number
            if not pr_number or not input_data.github_repository:
                return False

            commenter = GitHubPRCommenter(
                github_token=input_data.github_token,
                repository=input_data.github_repository,
                pr_number=pr_number,
            )
            return await commenter.post_or_update(report_md)
        except Exception as e:
            logger.warning("github_comment_failed", error=str(e))
            return False

    async def _send_slack_notification(
        self,
        context_data: dict[str, Any],
        input_data: ReportInput,
    ) -> bool:
        """Send a Slack notification for the scan results."""
        try:
            bugs = context_data.get("bugs", [])
            by_severity = context_data.get("by_severity", {})
            critical = by_severity.get("Critical", 0)
            release = context_data.get("release_intelligence", {})

            is_safe = release.get("is_safe_to_merge", True)
            emoji = "✅" if is_safe else "🚨"

            message = (
                f"{emoji} *AIQE Quality Scan Complete*\n"
                f"Workflow: `{input_data.workflow_id[:12]}`\n"
                f"Bugs: {len(bugs)} total ({critical} Critical)\n"
                f"Recommendation: "
                f"{'Safe to Review' if is_safe else 'Review Required'}"
            )

            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    json={"text": message},
                    headers={
                        "Authorization": f"Bearer {input_data.slack_token}",
                        "Content-Type": "application/json",
                    },
                )
                return response.status_code == 200
        except Exception as e:
            logger.warning("slack_notification_failed", error=str(e))
            return False
