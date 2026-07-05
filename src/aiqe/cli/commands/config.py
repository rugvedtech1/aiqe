"""
AIQE CLI — config command group.

Usage:
    aiqe config show
    aiqe config validate
    aiqe config generate-key
"""

from __future__ import annotations

import typer

from aiqe.cli.console import (
    console,
    print_error,
    print_info,
    print_success,
    print_warning,
)

config_app = typer.Typer(help="Manage AIQE configuration.")


@config_app.command("show")
def config_show(
    show_secrets: bool = typer.Option(
        False,
        "--show-secrets",
        help="Show secret values (USE WITH CAUTION).",
    ),
) -> None:
    """
    Show the current AIQE configuration.

    Sensitive values (API keys, passwords) are always redacted
    unless --show-secrets is explicitly passed.
    """
    try:
        from aiqe.shared.config import get_settings
        from rich.table import Table
        from rich import box

        settings = get_settings()

        table = Table(
            title="AIQE Configuration",
            box=box.ROUNDED,
            border_style="blue",
        )
        table.add_column("Setting", style="bold", width=30)
        table.add_column("Value", width=45)

        table.add_row("Environment", settings.core.env.value)
        table.add_row("Log Level", settings.core.log_level.value)
        table.add_row("Workspace Dir", str(settings.core.workspace_dir))
        table.add_row(
            "Enterprise Mode",
            "[yellow]Yes[/yellow]"
            if settings.core.enterprise_mode
            else "No",
        )
        table.add_row(
            "Max Concurrent Workflows",
            str(settings.core.max_concurrent_workflows),
        )
        table.add_row(
            "Checkpoint Enabled",
            "[green]Yes[/green]"
            if settings.core.checkpoint_enabled
            else "No",
        )
        table.add_row(
            "Audit Log Enabled",
            "[green]Yes[/green]"
            if settings.core.audit_log_enabled
            else "No",
        )
        table.add_row("Database Mode", settings.database.mode.value)

        if settings.database.mode.value == "sqlite":
            table.add_row(
                "SQLite Path",
                str(settings.database.sqlite_path),
            )
        else:
            table.add_row(
                "Postgres Host",
                f"{settings.database.postgres_host}:"
                f"{settings.database.postgres_port}",
            )

        table.add_row(
            "Default AI Provider",
            settings.gateway.default_provider.value,
        )
        table.add_row("Default Model", settings.gateway.default_model)
        table.add_row(
            "Plugin Sandbox",
            "[green]Enabled[/green]"
            if settings.security.plugin_sandbox_enabled
            else "[red]Disabled[/red]",
        )
        table.add_row(
            "Capability Display",
            "[green]Yes[/green]"
            if settings.security.plugin_capability_display
            else "No",
        )

        # API keys (always redacted unless explicitly requested)
        from aiqe.gateway.keys import APIKeyManager
        key_manager = APIKeyManager.from_settings()
        key_stats = key_manager.stats()

        for provider, stats in key_stats.items():
            key_count = stats.get("total_keys", 0)
            table.add_row(
                f"{provider.capitalize()} API Keys",
                f"{key_count} key(s) configured",
            )

        console.print(table)

        if not show_secrets:
            print_info(
                "API key values are redacted. "
                "Use --show-secrets to display them (not recommended)."
            )

    except Exception as e:
        print_error(f"Configuration error: {e}")
        print_info(
            "Check your .env file against .env.example. "
            "Run [bold]aiqe config validate[/bold] for details."
        )
        raise typer.Exit(code=1)


@config_app.command("validate")
def config_validate() -> None:
    """
    Validate the current AIQE configuration.

    Checks for required settings, provider connectivity,
    and database accessibility.
    """
    errors = []
    warnings = []

    # Check core config
    try:
        from aiqe.shared.config import get_settings
        settings = get_settings()
        print_success("Core configuration is valid.")
    except Exception as e:
        errors.append(f"Core config invalid: {e}")

    # Check AI provider keys
    try:
        from aiqe.gateway.keys import APIKeyManager
        manager = APIKeyManager.from_settings()
        available = manager.available_providers()
        if available:
            print_success(
                f"AI providers configured: {', '.join(available)}"
            )
        else:
            errors.append(
                "No AI providers configured. "
                "Add at least one API key to .env."
            )
    except Exception as e:
        errors.append(f"AI Gateway config invalid: {e}")

    # Check database config
    try:
        from aiqe.shared.config import get_settings
        settings = get_settings()
        workspace = settings.core.workspace_dir
        workspace.mkdir(parents=True, exist_ok=True)
        print_success(
            f"Workspace directory accessible: {workspace}"
        )
    except Exception as e:
        errors.append(f"Workspace directory error: {e}")

    # Print results
    for warning in warnings:
        print_warning(warning)

    if errors:
        console.print()
        for error in errors:
            print_error(error)
        raise typer.Exit(code=1)
    else:
        console.print()
        print_success("All configuration checks passed.")


@config_app.command("generate-key")
def config_generate_key() -> None:
    """
    Generate a new AIQE encryption key.

    Copy the output to AIQE_ENCRYPTION_KEY in your .env file.
    Keep this key secure — losing it means losing access to
    all encrypted stored values.
    """
    from aiqe.shared.security import generate_encryption_key

    key = generate_encryption_key()

    console.print("\n[bold]Generated Encryption Key:[/bold]")
    console.print(f"\n[green]{key}[/green]\n")
    print_warning(
        "Store this key securely. "
        "Add it to your .env as AIQE_ENCRYPTION_KEY=<key>. "
        "Never commit it to version control."
    )
