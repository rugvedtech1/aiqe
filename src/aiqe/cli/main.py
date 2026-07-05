"""
AIQE CLI Main Entrypoint.

This is the root Typer application. All command groups
are registered here and wired to the entry point defined
in pyproject.toml:

    [project.scripts]
    aiqe = "aiqe.cli.main:app"

Commands:
    aiqe scan      — scan a project
    aiqe status    — check workflow status
    aiqe report    — generate reports
    aiqe plugins   — manage plugins
    aiqe gateway   — AI gateway management
    aiqe config    — configuration management
    aiqe version   — show version
"""

from __future__ import annotations

import typer
from typing import Optional

from aiqe.cli.commands.config import config_app
from aiqe.cli.commands.gateway import gateway_app
from aiqe.cli.commands.plugins import plugins_app
from aiqe.cli.commands.report import report_app
from aiqe.cli.commands.scan import scan_app
from aiqe.cli.commands.status import status_app

# Root application
app = typer.Typer(
    name="aiqe",
    help=(
        "AIQE — AI Quality Engineering Operating System.\n\n"
        "Understands software, generates tests, analyzes failures,\n"
        "finds root causes, and provides release intelligence."
    ),
    rich_markup_mode="rich",
    no_args_is_help=True,
    add_completion=True,
)

# Register command groups
app.add_typer(scan_app, name="scan")
app.add_typer(status_app, name="status")
app.add_typer(report_app, name="report")
app.add_typer(plugins_app, name="plugins")
app.add_typer(gateway_app, name="gateway")
app.add_typer(config_app, name="config")


@app.command("version")
def version() -> None:
    """Show the AIQE version."""
    from aiqe.cli.console import console
    console.print("[bold blue]AIQE[/bold blue] version [green]0.1.0-alpha[/green]")
    console.print("[dim]AI Quality Engineering Operating System[/dim]")


@app.callback()
def main(
    ctx: typer.Context,
    version_flag: Optional[bool] = typer.Option(
        None,
        "--version", "-v",
        is_eager=True,
        help="Show version and exit.",
    ),
) -> None:
    """
    AIQE — AI Quality Engineering Operating System.

    Run [bold]aiqe --help[/bold] to see available commands.
    Run [bold]aiqe scan .[/bold] to start scanning a project.
    """
    if version_flag:
        from aiqe.cli.console import console
        console.print(
            "[bold blue]AIQE[/bold blue] version [green]0.1.0-alpha[/green]"
        )
        raise typer.Exit()


if __name__ == "__main__":
    app()
