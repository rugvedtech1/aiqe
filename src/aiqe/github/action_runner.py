"""
AIQE GitHub Action Runner.

The main entry point for the GitHub Action execution.
Called by the composite action step:
    python -m aiqe.github.action_runner --project-path .

Responsibilities:
    1. Parse the GitHub event context.
    2. Configure AIQE from Action inputs (env vars).
    3. Create and run a workflow context.
    4. Write GitHub Action outputs.
    5. Post PR comment if configured.
    6. Save report artifact.
    7. Exit with correct status code.

Exit codes:
    0 — scan completed, no blocking issues
    1 — unexpected error
    2 — blocking issues found (severity >= fail-on-severity)
    3 — AIQE configuration error
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import typer

from aiqe.shared.logging import configure_logging, get_logger

logger = get_logger(__name__)

action_app = typer.Typer(
    name="aiqe-action",
    help="AIQE GitHub Action runner.",
    add_completion=False,
)


@action_app.command()
def run(
    project_path: str = typer.Option(
        ".",
        "--project-path",
        help="Path to the project to scan.",
    ),
) -> None:
    """Run AIQE quality scan as a GitHub Action."""
    log_level = os.environ.get("AIQE_LOG_LEVEL", "INFO")
    configure_logging(log_level=log_level, json_output=True)

    try:
        exit_code = asyncio.run(_run_action(project_path))
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.warning("action_interrupted")
        sys.exit(1)
    except Exception as e:
        logger.error(
            "action_runner_error",
            error_type=type(e).__name__,
            error=str(e),
        )
        _set_output("status", "failed")
        _set_output("bugs-found", "0")
        _set_output("is-safe-to-merge", "false")
        sys.exit(1)


async def _run_action(project_path: str) -> int:
    """Execute the full action run. Returns exit code."""
    from aiqe.github.event_parser import GitHubEventParser
    from aiqe.agents.registry_setup import register_all_agents
    from aiqe.workflow.engine import get_engine
    from aiqe.persistence.factory import get_repository_bundle

    # Step 1: Parse GitHub event context
    parser = GitHubEventParser()
    event = parser.parse()

    logger.info(
        "action_started",
        event_name=event.event_name,
        repository=event.repository,
        pr_number=event.pr_number,
        branch=event.head_branch,
        changed_files=len(event.changed_files),
    )

    # Step 2: Resolve project path
    resolved_path = Path(project_path).resolve()
    if not resolved_path.exists():
        logger.error(
            "project_path_not_found",
            path=str(resolved_path),
        )
        _set_output("status", "failed")
        return 3

    # Step 3: Set up AIQE
    register_all_agents()
    engine = get_engine()
    bundle = await get_repository_bundle()

    # Step 4: Create workflow context
    trigger = "pr" if event.pr_number else "branch"
    context = await engine.create_context(
        trigger=trigger,
        repository=event.repository,
        branch=event.head_branch,
        pr_number=event.pr_number,
    )

    # Store changed files in workflow metadata
    await context.memory_set(
        "system.workflow_metadata",
        {
            **event.to_dict(),
            "project_path": str(resolved_path),
        },
    )

    # Step 5: Run the workflow
    logger.info(
        "workflow_starting",
        workflow_id=context.id,
    )

    completed_context = await engine.run(context=context)

    # Step 6: Persist results
    await bundle.workflows.save(completed_context.to_dict())
    for bug in completed_context.bugs:
        await bundle.bugs.save({
            **bug,
            "workflow_id": completed_context.id,
            "repository": event.repository,
        })
    if completed_context.audit_log:
        await bundle.audit.append_batch(
            completed_context.id,
            completed_context.audit_log,
        )

    # Step 7: Analyse results
    bugs_raw = await bundle.bugs.find_by_workflow(completed_context.id)
    severity_counts = await bundle.bugs.count_by_workflow(
        completed_context.id
    )

    critical_count = severity_counts.get("Critical", 0)
    high_count = severity_counts.get("High", 0)
    total_bugs = len(bugs_raw)

    # Determine release risk
    release_risk = _calculate_release_risk(severity_counts)
    is_safe_to_merge = _is_safe_to_merge(severity_counts)

    # Step 8: Write GitHub Action outputs
    _set_output("workflow-id", completed_context.id)
    _set_output("status", completed_context.status.value)
    _set_output("bugs-found", str(total_bugs))
    _set_output("critical-bugs", str(critical_count))
    _set_output("high-bugs", str(high_count))
    _set_output("release-risk", release_risk)
    _set_output("is-safe-to-merge", str(is_safe_to_merge).lower())

    # Step 9: Generate and save report
    report_path = await _save_report(
        context=completed_context,
        bugs=bugs_raw,
        project_path=resolved_path,
    )
    _set_output("report-path", str(report_path))

    # Step 10: Post PR comment if configured
    post_comment = os.environ.get(
        "AIQE_POST_PR_COMMENT", "true"
    ).lower() == "true"
    github_token = os.environ.get("GITHUB_TOKEN", "")

    if post_comment and event.pr_number and github_token:
        await _post_pr_comment(
            workflow_summary=completed_context.to_dict(),
            bugs=bugs_raw,
            event=event,
            is_safe_to_merge=is_safe_to_merge,
            release_risk=release_risk,
            github_token=github_token,
        )

    # Step 11: Log summary
    logger.info(
        "action_complete",
        workflow_id=completed_context.id,
        status=completed_context.status.value,
        total_bugs=total_bugs,
        critical_bugs=critical_count,
        high_bugs=high_count,
        release_risk=release_risk,
        is_safe_to_merge=is_safe_to_merge,
    )

    # Step 12: Determine exit code
    fail_on = os.environ.get("AIQE_FAIL_ON_SEVERITY", "High")
    return _get_exit_code(severity_counts, fail_on)


def _calculate_release_risk(
    severity_counts: dict[str, int]
) -> str:
    """Determine overall release risk from bug severity counts."""
    if severity_counts.get("Critical", 0) > 0:
        return "Critical"
    if severity_counts.get("High", 0) > 0:
        return "High"
    if severity_counts.get("Medium", 0) > 2:
        return "Medium"
    if severity_counts.get("Low", 0) > 0:
        return "Low"
    return "Safe"


def _is_safe_to_merge(severity_counts: dict[str, int]) -> bool:
    """Return True if AIQE recommends this PR is safe to merge."""
    return (
        severity_counts.get("Critical", 0) == 0 and
        severity_counts.get("High", 0) == 0
    )


def _get_exit_code(
    severity_counts: dict[str, int],
    fail_on: str,
) -> int:
    """Determine exit code based on fail-on-severity setting."""
    severity_levels = ["Critical", "High", "Medium", "Low", "Informational"]

    if fail_on == "never":
        return 0

    if fail_on not in severity_levels:
        return 0

    fail_index = severity_levels.index(fail_on)

    for i, severity in enumerate(severity_levels):
        if i <= fail_index and severity_counts.get(severity, 0) > 0:
            logger.warning(
                "action_failing_due_to_severity",
                severity=severity,
                count=severity_counts[severity],
                fail_on=fail_on,
            )
            return 2

    return 0


def _set_output(name: str, value: str) -> None:
    """
    Write a GitHub Action output variable.

    Uses the GITHUB_OUTPUT file (modern approach) with fallback
    to the deprecated ::set-output:: command.
    """
    github_output = os.environ.get("GITHUB_OUTPUT", "")
    if github_output:
        try:
            with open(github_output, "a", encoding="utf-8") as f:
                f.write(f"{name}={value}\n")
        except OSError:
            print(f"::set-output name={name}::{value}")
    else:
        print(f"::set-output name={name}::{value}")


async def _save_report(
    context: object,
    bugs: list[dict],
    project_path: Path,
) -> Path:
    """Save the quality report as a workflow artifact."""
    report_format = os.environ.get("AIQE_REPORT_FORMAT", "markdown")

    report_dir = Path(".aiqe/reports")
    report_dir.mkdir(parents=True, exist_ok=True)

    summary = context.to_dict()
    workflow_id = summary.get("id", "unknown")

    if report_format == "json":
        report_path = report_dir / f"aiqe_report_{workflow_id[:8]}.json"
        report_content = json.dumps(
            {"workflow": summary, "bugs": bugs},
            indent=2,
            default=str,
        )
    else:
        report_path = report_dir / f"aiqe_report_{workflow_id[:8]}.md"
        report_content = _build_markdown_report(summary, bugs)

    report_path.write_text(report_content, encoding="utf-8")

    logger.info(
        "report_saved",
        path=str(report_path),
        format=report_format,
    )

    return report_path


def _build_markdown_report(
    summary: dict,
    bugs: list[dict],
) -> str:
    """Build a Markdown quality report."""
    lines = [
        "# AIQE Quality Report",
        "",
        f"**Status:** {summary.get('status', 'unknown').upper()}",
        f"**Workflow ID:** `{summary.get('id', 'N/A')}`",
        f"**Repository:** {summary.get('repository', 'N/A')}",
        f"**Branch:** {summary.get('branch', 'N/A')}",
        "",
        f"## Summary",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Bugs | {len(bugs)} |",
        f"| Agents Completed | {summary.get('agents_completed', 0)} |",
        f"| Agents Skipped | {summary.get('agents_skipped', 0)} |",
        "",
    ]

    if bugs:
        lines += ["## Issues", ""]
        severity_order = {
            "Critical": 0, "High": 1, "Medium": 2,
            "Low": 3, "Informational": 4,
        }
        for bug in sorted(
            bugs,
            key=lambda b: severity_order.get(b.get("severity", ""), 99),
        ):
            lines += [
                f"### [{bug.get('severity')}] {bug.get('title', 'N/A')}",
                f"- **Confidence:** {bug.get('confidence', 0)*100:.0f}%",
                f"- **Root Cause:** {bug.get('root_cause', 'N/A')}",
                f"- **Suggested Fix:** {bug.get('suggested_fix', 'N/A')}",
                "",
            ]
    else:
        lines += ["## ✅ No Issues Found", ""]

    lines += [
        "---",
        "_Generated by AIQE — AI Quality Engineering Operating System_",
    ]
    return "\n".join(lines)


async def _post_pr_comment(
    workflow_summary: dict,
    bugs: list[dict],
    event: object,
    is_safe_to_merge: bool,
    release_risk: str,
    github_token: str,
) -> None:
    """Build and post the PR quality comment."""
    from aiqe.github.pr_comment import PRCommentBuilder, GitHubPRCommenter

    builder = PRCommentBuilder(
        workflow_summary=workflow_summary,
        bugs=bugs,
        event_context=event,
        is_safe_to_merge=is_safe_to_merge,
        release_risk=release_risk,
    )
    comment_body = builder.build()

    commenter = GitHubPRCommenter(
        github_token=github_token,
        repository=event.repository,
        pr_number=event.pr_number,
    )
    success = await commenter.post_or_update(comment_body)

    if success:
        logger.info("pr_comment_posted")
    else:
        logger.warning("pr_comment_failed_non_blocking")


if __name__ == "__main__":
    action_app()
