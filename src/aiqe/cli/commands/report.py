"""
AIQE CLI — report command.

Usage:
    aiqe report <workflow-id>
    aiqe report <workflow-id> --format html
    aiqe report <workflow-id> --format pdf --output ./reports/
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import json

import typer

from aiqe.cli.console import (
    console,
    print_bug_table,
    print_error,
    print_info,
    print_success,
    print_workflow_summary,
)

report_app = typer.Typer(help="Generate reports for workflow executions.")


@report_app.callback(invoke_without_command=True)
def report(
    workflow_id: str = typer.Argument(
        ...,
        help="Workflow ID to generate a report for.",
    ),
    format: str = typer.Option(
        "markdown",
        "--format", "-f",
        help="Report format: markdown, json, html (html/pdf coming in Step 18).",
    ),
    output_dir: Optional[Path] = typer.Option(
        None,
        "--output", "-o",
        help="Directory to save the report. Defaults to current directory.",
    ),
    show_bugs: bool = typer.Option(
        True,
        "--bugs/--no-bugs",
        help="Include bug details in the report.",
    ),
    show_audit: bool = typer.Option(
        False,
        "--audit",
        help="Include the full audit trail in the report.",
    ),
) -> None:
    """
    Generate a quality report for a completed workflow.

    Examples:
    \b
      aiqe report wf-abc123
      aiqe report wf-abc123 --format json
      aiqe report wf-abc123 --format markdown --output ./reports/
    """
    import asyncio

    try:
        asyncio.run(
            _generate_report(
                workflow_id=workflow_id,
                format=format,
                output_dir=output_dir or Path("."),
                show_bugs=show_bugs,
                show_audit=show_audit,
            )
        )
    except Exception as e:
        print_error(f"Report generation failed: {e}")
        raise typer.Exit(code=1)


async def _generate_report(
    workflow_id: str,
    format: str,
    output_dir: Path,
    show_bugs: bool,
    show_audit: bool,
) -> None:
    """Fetch workflow data and generate a report."""
    from aiqe.persistence.factory import get_repository_bundle

    bundle = await get_repository_bundle()

    context = await bundle.workflows.find_by_id(workflow_id)
    if context is None:
        print_error(f"Workflow '{workflow_id}' not found.")
        raise typer.Exit(code=1)

    bugs = await bundle.bugs.find_by_workflow(workflow_id)
    audit_entries = []
    if show_audit:
        audit_entries = await bundle.audit.find_by_workflow(workflow_id)

    if format == "json":
        report_data = {
            "workflow": context,
            "bugs": bugs,
            "audit_log": audit_entries if show_audit else [],
        }
        report_path = output_dir / f"aiqe_report_{workflow_id[:8]}.json"
        report_path.write_text(
            json.dumps(report_data, indent=2, default=str),
            encoding="utf-8",
        )
        print_success(f"JSON report saved to: {report_path}")
        return

    if format == "markdown":
        report_content = _build_markdown_report(
            context=context,
            bugs=bugs,
            audit_entries=audit_entries if show_audit else [],
        )
        report_path = output_dir / f"aiqe_report_{workflow_id[:8]}.md"
        report_path.write_text(report_content, encoding="utf-8")
        print_success(f"Markdown report saved to: {report_path}")

        # Also display in terminal
        print_workflow_summary(context)
        if show_bugs and bugs:
            print_bug_table(bugs)
        return

    if format in ("html", "pdf"):
        print_info(
            f"{format.upper()} report generation will be available "
            f"in Step 18 (Report Agent). "
            f"Using markdown for now."
        )
        await _generate_report(
            workflow_id, "markdown", output_dir, show_bugs, show_audit
        )
        return

    print_error(f"Unknown format '{format}'. Use: markdown, json, html.")
    raise typer.Exit(code=1)


def _build_markdown_report(
    context: dict,
    bugs: list[dict],
    audit_entries: list[dict],
) -> str:
    """Build a Markdown report from workflow data."""
    status = context.get("status", "unknown").upper()
    lines = [
        f"# AIQE Quality Report",
        f"",
        f"**Workflow ID:** `{context.get('id', 'N/A')}`",
        f"**Status:** {status}",
        f"**Repository:** {context.get('repository', 'N/A')}",
        f"**Branch:** {context.get('branch', 'N/A')}",
        f"**Trigger:** {context.get('trigger', 'N/A')}",
        f"",
        f"---",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Bugs Found | {context.get('bugs_count', 0)} |",
        f"| Agents Completed | {context.get('agents_completed', 0)} |",
        f"| Agents Skipped | {context.get('agents_skipped', 0)} |",
        f"",
    ]

    if bugs:
        lines += [
            f"## Bugs Found ({len(bugs)})",
            f"",
        ]
        severity_order = {
            "Critical": 0, "High": 1, "Medium": 2, "Low": 3,
            "Informational": 4
        }
        sorted_bugs = sorted(
            bugs,
            key=lambda b: severity_order.get(b.get("severity", ""), 99)
        )
        for bug in sorted_bugs:
            lines += [
                f"### [{bug.get('severity')}] {bug.get('title', 'N/A')}",
                f"",
                f"- **Confidence:** {bug.get('confidence', 0)*100:.0f}%",
                f"- **Feature:** {bug.get('affected_feature', 'N/A')}",
                f"- **Root Cause:** {bug.get('root_cause', 'N/A')}",
                f"- **Suggested Fix:** {bug.get('suggested_fix', 'N/A')}",
                f"",
            ]

    if audit_entries:
        lines += [
            f"## Audit Trail ({len(audit_entries)} events)",
            f"",
            f"| Event | Type | Time |",
            f"|-------|------|------|",
        ]
        for entry in audit_entries[:50]:  # Cap at 50 for readability
            lines.append(
                f"| {entry.get('event_id', 'N/A')[:8]} "
                f"| {entry.get('event_type', 'N/A')} "
                f"| {entry.get('occurred_at', 'N/A')} |"
            )

    lines += [
        f"",
        f"---",
        f"*Generated by AIQE — AI Quality Engineering Operating System*",
    ]

    return "\n".join(lines)
