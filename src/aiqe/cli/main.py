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


@app.command("serve")
def serve(
    host: str = typer.Option(
        "0.0.0.0",
        "--host",
        help="Host to bind the API server to.",
    ),
    port: int = typer.Option(
        8000,
        "--port", "-p",
        help="Port to listen on.",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Enable auto-reload for development.",
    ),
    workers: int = typer.Option(
        1,
        "--workers",
        help="Number of worker processes (enterprise mode).",
    ),
    log_level: str = typer.Option(
        "info",
        "--log-level",
        help="Log level for the server.",
    ),
) -> None:
    """
    Start the AIQE REST API server.

    Examples:
    \b
      aiqe serve
      aiqe serve --port 9000
      aiqe serve --host 127.0.0.1 --port 8080 --reload
      aiqe serve --workers 4  # enterprise multi-process mode
    """
    from aiqe.cli.console import print_banner, print_info, console

    print_banner()
    print_info(f"Starting AIQE API server on [bold]http://{host}:{port}[/bold]")
    console.print(f"  API Docs:  [link]http://{host}:{port}/docs[/link]")
    console.print(f"  ReDoc:     [link]http://{host}:{port}/redoc[/link]")
    console.print(f"  Health:    [link]http://{host}:{port}/health[/link]")
    console.print(f"  Ready:     [link]http://{host}:{port}/ready[/link]")
    console.print("")

    from aiqe.api.server import run as run_server
    run_server(
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
        workers=workers,
    )
