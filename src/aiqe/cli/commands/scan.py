"""
AIQE CLI — scan command.

Usage:
    aiqe scan .
    aiqe scan /path/to/project
    aiqe scan . --branch feature/auth --dry-run
    aiqe scan . --provider anthropic --output json

The scan command is AIQE's primary entry point. It:
    1. Creates an isolated WorkflowContext.
    2. Registers the Orchestrator and enabled agents.
    3. Runs the full workflow engine.
    4. Displays a summary and opens/saves the report.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from aiqe.cli.console import (
    console,
    print_banner,
    print_bug_table,
    print_error,
    print_info,
    print_success,
    print_warning,
    print_workflow_summary,
    make_progress,
)
from aiqe.cli.types import OutputFormat, resolve_project_path
from aiqe.shared.logging import configure_logging, get_logger

logger = get_logger(__name__)

scan_app = typer.Typer(help="Scan a project for quality issues.")


@scan_app.callback(invoke_without_command=True)
def scan(
    project_path: str = typer.Argument(
        ".",
        help="Path to the project to scan. Defaults to current directory.",
    ),
    branch: Optional[str] = typer.Option(
        None,
        "--branch", "-b",
        help="Branch name to associate with this scan.",
    ),
    pr_number: Optional[int] = typer.Option(
        None,
        "--pr",
        help="Pull Request number (enables PR-specific analysis).",
    ),
    repository: Optional[str] = typer.Option(
        None,
        "--repo", "-r",
        help="Repository in owner/repo format (e.g. rugvedtech1/aiqe).",
    ),
    provider: Optional[str] = typer.Option(
        None,
        "--provider",
        help="AI provider to use (openai/anthropic/gemini/groq/ollama).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Show what AIQE would do without executing tests.",
    ),
    output: OutputFormat = typer.Option(
        OutputFormat.TABLE,
        "--output", "-o",
        help="Output format: table, json, or markdown.",
    ),
    no_banner: bool = typer.Option(
        False,
        "--no-banner",
        help="Skip the AIQE banner (useful for CI).",
    ),
    log_level: str = typer.Option(
        "INFO",
        "--log-level",
        help="Log level: DEBUG, INFO, WARNING, ERROR.",
    ),
) -> None:
    """
    Scan a project for quality issues using AI-powered analysis.

    AIQE will:
    \b
      1. Analyse the project structure and detect framework/language
      2. Build a dependency intelligence model
      3. Generate a test strategy based on risk
      4. Generate and execute test cases
      5. Analyse failures and find root causes
      6. Produce a release intelligence report

    Examples:
    \b
      aiqe scan .
      aiqe scan /path/to/project --branch feature/auth
      aiqe scan . --pr 42 --repo owner/project
      aiqe scan . --dry-run
      aiqe scan . --provider anthropic --output json
    """
    configure_logging(log_level=log_level.upper(), json_output=False)

    if not no_banner:
        print_banner()

    try:
        project = resolve_project_path(project_path)
    except typer.BadParameter as e:
        print_error(str(e))
        raise typer.Exit(code=1)

    print_info(f"Scanning project: [bold]{project}[/bold]")

    if dry_run:
        print_warning("DRY RUN MODE — no tests will be executed.")

    if pr_number:
        print_info(f"PR Mode: #{pr_number}")

    # Show what will happen in dry-run mode
    if dry_run:
        _show_dry_run_plan(
            project=project,
            branch=branch,
            pr_number=pr_number,
            repository=repository,
            provider=provider,
        )
        return

    # Run the actual scan
    import asyncio
    try:
        result = asyncio.run(
            _execute_scan(
                project=project,
                branch=branch or "",
                pr_number=pr_number,
                repository=repository or "",
                provider=provider,
                output_format=output,
            )
        )
    except KeyboardInterrupt:
        print_warning("\nScan interrupted by user.")
        raise typer.Exit(code=130)
    except Exception as e:
        print_error(f"Scan failed: {e}")
        logger.exception("scan_command_failed", error=str(e))
        raise typer.Exit(code=1)


async def _execute_scan(
    project: Path,
    branch: str,
    pr_number: int | None,
    repository: str,
    provider: str | None,
    output_format: OutputFormat,
) -> dict:
    """Execute the full scan workflow."""
    from aiqe.agents.registry_setup import register_all_agents
    from aiqe.workflow.engine import get_engine

    register_all_agents()
    engine = get_engine()

    trigger = "pr" if pr_number else "manual"

    with make_progress() as progress:
        task = progress.add_task(
            "Creating workflow context...", total=None
        )

        context = await engine.create_context(
            trigger=trigger,
            repository=repository,
            branch=branch,
            pr_number=pr_number,
        )

        progress.update(task, description="Running workflow...")

        # Run the workflow engine
        # In the current state (Steps 1-11), this runs the
        # Orchestrator Agent only. Full agent execution comes in Steps 15-18.
        context = await engine.run(context=context)

        progress.update(
            task,
            description="Workflow complete.",
            completed=100,
            total=100,
        )

    # Display results
    _display_results(context, output_format)
    return context.to_dict()


def _display_results(context: any, output_format: OutputFormat) -> None:
    """Display scan results in the requested format."""
    summary = context.to_dict()

    if output_format == OutputFormat.JSON:
        import json
        console.print_json(json.dumps(summary, indent=2, default=str))
        return

    if output_format == OutputFormat.MARKDOWN:
        _print_markdown_summary(summary)
        return

    print_workflow_summary(summary)

    if context.bugs:
        print_bug_table(context.bugs)
    else:
        print_success("No bugs found in this scan.")

    if context.status.value == "completed":
        print_success("Scan completed successfully.")
    elif context.status.value == "failed":
        print_error(f"Scan failed: {context.error}")


def _print_markdown_summary(summary: dict) -> None:
    """Print scan results in Markdown format."""
    md = f"""# AIQE Scan Results

**Status:** {summary.get('status', 'unknown').upper()}
**Repository:** {summary.get('repository', 'N/A')}
**Branch:** {summary.get('branch', 'N/A')}
**Bugs Found:** {summary.get('bugs_count', 0)}
"""
    console.print(md)


def _show_dry_run_plan(
    project: Path,
    branch: str | None,
    pr_number: int | None,
    repository: str | None,
    provider: str | None,
) -> None:
    """Show what AIQE would do without executing."""
    from aiqe.agents.registry_setup import register_all_agents
    from aiqe.workflow.registry import agent_registry

    register_all_agents()

    console.print("\n[bold]Dry Run Plan[/bold]")
    console.print(f"  Project:    {project}")
    console.print(f"  Branch:     {branch or 'auto-detect'}")
    console.print(f"  Repository: {repository or 'auto-detect'}")
    console.print(f"  PR:         {f'#{pr_number}' if pr_number else 'N/A'}")
    console.print(f"  Provider:   {provider or 'default from config'}")

    console.print("\n[bold]Agents that would execute:[/bold]")
    try:
        waves = agent_registry.resolve_execution_order()
        for i, wave in enumerate(waves, 1):
            console.print(f"  Wave {i}: {', '.join(wave)}")
    except Exception:
        for reg in agent_registry.get_all_enabled():
            console.print(f"  • {reg.display_name} (Tier {reg.tier})")

    print_info("Dry run complete. Use without --dry-run to execute.")
