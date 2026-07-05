"""
AIQE CLI — status command.

Usage:
    aiqe status
    aiqe status <workflow-id>
    aiqe status --active
"""

from __future__ import annotations

from typing import Optional
import json

import typer

from aiqe.cli.console import (
    console,
    print_agent_table,
    print_error,
    print_info,
    print_success,
    print_warning,
    print_workflow_summary,
)

status_app = typer.Typer(help="Check workflow execution status.")


@status_app.callback(invoke_without_command=True)
def status(
    workflow_id: Optional[str] = typer.Argument(
        None,
        help="Workflow ID to inspect. Shows active workflows if omitted.",
    ),
    active: bool = typer.Option(
        False,
        "--active", "-a",
        help="Show only currently active (running) workflows.",
    ),
    show_agents: bool = typer.Option(
        False,
        "--agents",
        help="Show per-agent execution details.",
    ),
    output_json: bool = typer.Option(
        False,
        "--json",
        help="Output in JSON format.",
    ),
) -> None:
    """
    Show the status of AIQE workflow executions.

    Examples:
    \b
      aiqe status
      aiqe status wf-abc123-def456
      aiqe status --active
      aiqe status wf-abc123 --agents
    """
    import asyncio

    try:
        asyncio.run(
            _show_status(
                workflow_id=workflow_id,
                active_only=active,
                show_agents=show_agents,
                output_json=output_json,
            )
        )
    except Exception as e:
        print_error(f"Status check failed: {e}")
        raise typer.Exit(code=1)


async def _show_status(
    workflow_id: str | None,
    active_only: bool,
    show_agents: bool,
    output_json: bool,
) -> None:
    """Fetch and display workflow status."""
    from aiqe.persistence.factory import get_repository_bundle

    bundle = await get_repository_bundle()

    if workflow_id:
        # Show a specific workflow
        context = await bundle.workflows.find_by_id(workflow_id)
        if context is None:
            print_error(f"Workflow '{workflow_id}' not found.")
            raise typer.Exit(code=1)

        if output_json:
            console.print_json(json.dumps(context, indent=2, default=str))
            return

        print_workflow_summary(context)

        if show_agents and context.get("agent_records"):
            print_agent_table(context["agent_records"])

    else:
        # Show all active or recent workflows
        if active_only:
            workflows = await bundle.workflows.find_active()
            title = "Active Workflows"
        else:
            # Show recent workflows — find_by_repository with empty
            # string returns all in this simple implementation
            workflows = await bundle.workflows.find_active()
            title = "Recent Workflows"

        if not workflows:
            print_info(
                "No active workflows found. "
                "Run [bold]aiqe scan .[/bold] to start one."
            )
            return

        if output_json:
            console.print_json(
                json.dumps(workflows, indent=2, default=str)
            )
            return

        from rich.table import Table
        from rich import box

        table = Table(
            title=title,
            box=box.ROUNDED,
            border_style="blue",
        )
        table.add_column("ID", width=38)
        table.add_column("Status", width=14)
        table.add_column("Repository", width=25)
        table.add_column("Branch", width=20)
        table.add_column("Bugs", width=6)

        status_colors = {
            "completed": "green",
            "failed": "red",
            "running": "blue",
            "checkpointed": "yellow",
        }

        for wf in workflows:
            status = wf.get("status", "unknown")
            color = status_colors.get(status, "white")
            table.add_row(
                f"[dim]{wf.get('id', 'N/A')}[/dim]",
                f"[{color}]{status.upper()}[/{color}]",
                wf.get("repository", "N/A"),
                wf.get("branch", "N/A"),
                str(wf.get("bugs_count", 0)),
            )

        console.print(table)
        print_info(
            f"Found {len(workflows)} workflow(s). "
            f"Use [bold]aiqe status <id>[/bold] for details."
        )
