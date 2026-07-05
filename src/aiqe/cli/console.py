"""
AIQE CLI Console Output.

All terminal output goes through this module.
Uses Rich for professional, readable CLI output.

Why Rich?
    Rich provides consistent, professional terminal output:
    colored tables, progress bars, panels, syntax highlighting.
    Using it centrally means every command has the same look
    and feel without each command importing Rich individually.

Design rule:
    Commands never print() directly.
    They call console functions from this module.
    This makes testing clean — mock the console, not stdout.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.syntax import Syntax
from rich.table import Table
from rich import box

# Single console instance used everywhere
console = Console()
error_console = Console(stderr=True)


def print_banner() -> None:
    """Print the AIQE ASCII banner."""
    banner = """
[bold blue]
    ╔═══╗ ╔══╗  ╔══╗ ╔═══╗
    ║ ╔═╝ ║  ║  ║  ║ ║ ╔═╝
    ║ ╚═╗ ║  ║  ║  ║ ║ ╚═╗
    ╚═══╝ ╚══╝  ╚══╝ ╚═══╝
[/bold blue]
[dim]AI Quality Engineering Operating System[/dim]
"""
    console.print(banner)


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[bold green]✓[/bold green] {message}")


def print_error(message: str) -> None:
    """Print an error message to stderr."""
    error_console.print(f"[bold red]✗[/bold red] {message}")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[bold yellow]⚠[/bold yellow] {message}")


def print_info(message: str) -> None:
    """Print an informational message."""
    console.print(f"[bold blue]ℹ[/bold blue] {message}")


def print_panel(
    content: str,
    title: str = "",
    border_style: str = "blue",
) -> None:
    """Print content in a Rich panel."""
    console.print(Panel(content, title=title, border_style=border_style))


def print_workflow_summary(summary: dict[str, Any]) -> None:
    """Print a formatted workflow execution summary."""
    status = summary.get("status", "unknown")
    status_color = {
        "completed": "green",
        "failed": "red",
        "running": "blue",
        "checkpointed": "yellow",
        "pending": "dim",
    }.get(status, "white")

    table = Table(
        title="Workflow Summary",
        box=box.ROUNDED,
        border_style="blue",
        show_header=True,
    )
    table.add_column("Field", style="bold", width=25)
    table.add_column("Value")

    table.add_row(
        "Workflow ID",
        f"[dim]{summary.get('id', 'N/A')}[/dim]",
    )
    table.add_row(
        "Status",
        f"[{status_color}]{status.upper()}[/{status_color}]",
    )
    table.add_row("Repository", summary.get("repository", "N/A"))
    table.add_row("Branch", summary.get("branch", "N/A"))
    table.add_row("Trigger", summary.get("trigger", "N/A"))

    if summary.get("pr_number"):
        table.add_row("PR Number", f"#{summary['pr_number']}")

    if summary.get("duration_seconds"):
        from aiqe.shared.utils import format_duration
        table.add_row(
            "Duration",
            format_duration(summary["duration_seconds"]),
        )

    table.add_row(
        "Bugs Found",
        f"[red]{summary.get('bugs_count', 0)}[/red]",
    )
    table.add_row(
        "Agents Completed",
        str(summary.get("agents_completed", 0)),
    )
    table.add_row(
        "Agents Skipped",
        f"[yellow]{summary.get('agents_skipped', 0)}[/yellow]",
    )

    console.print(table)


def print_bug_table(bugs: list[dict[str, Any]]) -> None:
    """Print a formatted bug summary table."""
    if not bugs:
        print_success("No bugs found.")
        return

    table = Table(
        title=f"Bugs Found ({len(bugs)} total)",
        box=box.ROUNDED,
        border_style="red",
        show_header=True,
    )
    table.add_column("Severity", width=12)
    table.add_column("Confidence", width=11)
    table.add_column("Title", width=40)
    table.add_column("Feature", width=20)

    severity_colors = {
        "Critical": "bold red",
        "High": "red",
        "Medium": "yellow",
        "Low": "blue",
        "Informational": "dim",
    }

    for bug in bugs:
        severity = bug.get("severity", "Unknown")
        color = severity_colors.get(severity, "white")
        confidence = bug.get("confidence", 0)

        table.add_row(
            f"[{color}]{severity}[/{color}]",
            f"{confidence * 100:.0f}%",
            bug.get("title", "N/A"),
            bug.get("affected_feature", "N/A"),
        )

    console.print(table)


def print_agent_table(agent_records: dict[str, Any]) -> None:
    """Print a formatted agent execution table."""
    if not agent_records:
        print_info("No agent records found.")
        return

    table = Table(
        title="Agent Execution",
        box=box.ROUNDED,
        border_style="blue",
        show_header=True,
    )
    table.add_column("Agent", width=30)
    table.add_column("Status", width=12)
    table.add_column("Duration", width=10)
    table.add_column("Tokens", width=10)

    status_colors = {
        "completed": "green",
        "failed": "red",
        "skipped": "yellow",
        "running": "blue",
        "pending": "dim",
        "timeout": "red",
    }

    for agent_name, record in agent_records.items():
        status = record.get("status", "unknown")
        color = status_colors.get(status, "white")
        duration = record.get("duration_seconds", 0)

        from aiqe.shared.utils import format_duration
        duration_str = (
            format_duration(duration) if duration > 0 else "-"
        )

        table.add_row(
            agent_name,
            f"[{color}]{status.upper()}[/{color}]",
            duration_str,
            str(record.get("ai_tokens_used", 0)),
        )

        if status == "skipped" and record.get("skip_reason"):
            table.add_row(
                f"  [dim]↳ {record['skip_reason'][:60]}[/dim]",
                "", "", "",
            )

    console.print(table)


def print_plugin_table(plugins: list[dict[str, Any]]) -> None:
    """Print a formatted plugin list table."""
    if not plugins:
        print_info("No plugins loaded.")
        return

    table = Table(
        title=f"Loaded Plugins ({len(plugins)})",
        box=box.ROUNDED,
        border_style="blue",
    )
    table.add_column("Name", width=25)
    table.add_column("Version", width=8)
    table.add_column("Type", width=14)
    table.add_column("Author", width=20)
    table.add_column("Health", width=8)
    table.add_column("Capabilities", width=10)

    for plugin in plugins:
        health = plugin.get("is_healthy", False)
        health_str = (
            "[green]✓ OK[/green]" if health
            else "[red]✗ FAIL[/red]"
        )
        table.add_row(
            plugin.get("name", ""),
            plugin.get("version", ""),
            plugin.get("type", ""),
            plugin.get("author", ""),
            health_str,
            str(len(plugin.get("capabilities", []))),
        )

    console.print(table)


def print_gateway_status(stats: dict[str, Any]) -> None:
    """Print AI Gateway status and statistics."""
    table = Table(
        title="AI Gateway Status",
        box=box.ROUNDED,
        border_style="blue",
    )
    table.add_column("Provider", width=15)
    table.add_column("Requests", width=10)
    table.add_column("Tokens", width=12)
    table.add_column("Errors", width=8)

    requests_by = stats.get("requests_by_provider", {})
    tokens_by = stats.get("tokens_by_provider", {})
    errors_by = stats.get("errors_by_provider", {})

    if not requests_by:
        print_info("No AI requests made yet.")
        return

    for provider in requests_by:
        table.add_row(
            provider,
            str(requests_by.get(provider, 0)),
            str(tokens_by.get(provider, 0)),
            str(errors_by.get(provider, 0)),
        )

    console.print(table)
    console.print(
        f"[dim]Total requests: {stats.get('total_requests', 0)} | "
        f"Total tokens: {stats.get('total_tokens', 0)} | "
        f"Total errors: {stats.get('total_errors', 0)}[/dim]"
    )


def make_progress() -> Progress:
    """Create a Rich progress bar for workflow execution."""
    return Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )
