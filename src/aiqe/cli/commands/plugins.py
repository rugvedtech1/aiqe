"""
AIQE CLI — plugins command group.

Usage:
    aiqe plugins list
    aiqe plugins info <plugin-name>
    aiqe plugins validate <path-to-plugin-dir>
    aiqe plugins capabilities
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from aiqe.cli.console import (
    console,
    print_error,
    print_info,
    print_plugin_table,
    print_success,
    print_warning,
)

plugins_app = typer.Typer(help="Manage and inspect AIQE plugins.")


@plugins_app.command("list")
def plugins_list() -> None:
    """List all currently loaded plugins."""
    from aiqe.plugins.registry import get_plugin_registry

    registry = get_plugin_registry()
    plugins = registry.summary()

    if not plugins:
        print_info(
            "No plugins are currently loaded. "
            "Load plugins using the plugin configuration."
        )
        return

    print_plugin_table(plugins)
    print_info(f"Total: {len(plugins)} plugin(s) loaded.")


@plugins_app.command("info")
def plugins_info(
    plugin_name: str = typer.Argument(..., help="Plugin name to inspect."),
) -> None:
    """Show detailed information about a specific plugin."""
    from aiqe.plugins.registry import get_plugin_registry
    from aiqe.shared.exceptions import PluginLoadError

    registry = get_plugin_registry()

    try:
        loaded = registry.get(plugin_name)
    except PluginLoadError:
        print_error(f"Plugin '{plugin_name}' is not loaded.")
        available = [p["name"] for p in registry.summary()]
        if available:
            print_info(f"Available plugins: {', '.join(available)}")
        raise typer.Exit(code=1)

    manifest = loaded.manifest

    console.print(f"\n[bold]Plugin: {manifest.name}[/bold]")
    console.print(f"  Version:     {manifest.version}")
    console.print(f"  Type:        {manifest.plugin_type}")
    console.print(f"  Author:      {manifest.author}")
    console.print(f"  Description: {manifest.description}")
    console.print(
        f"  Health:      "
        f"{'[green]✓ Healthy[/green]' if loaded.is_healthy else '[red]✗ Unhealthy[/red]'}"
    )
    console.print(
        f"  Manifest:    "
        f"{manifest.manifest_path or 'in-memory'}"
    )

    if manifest.required_capabilities:
        console.print(f"\n  [bold]Capabilities ({len(manifest.required_capabilities)}):[/bold]")
        for cap in manifest.required_capabilities:
            risk_str = (
                "[red]⚠ RESTRICTED[/red]"
                if cap.is_restricted
                else f"[dim]risk:{cap.risk_level}[/dim]"
            )
            console.print(
                f"    • [cyan]{cap.display_name}[/cyan] "
                f"{risk_str}"
            )
            console.print(f"      [dim]{cap.description}[/dim]")
    else:
        console.print("\n  [dim]No capabilities declared.[/dim]")


@plugins_app.command("validate")
def plugins_validate(
    plugin_dir: str = typer.Argument(
        ...,
        help="Path to the plugin directory containing plugin.toml.",
    ),
) -> None:
    """
    Validate a plugin manifest without loading the plugin.

    Useful for plugin developers to check their plugin.toml
    before publishing.

    Examples:
    \b
      aiqe plugins validate ./my-plugin/
      aiqe plugins validate /path/to/plugin-directory
    """
    from aiqe.plugins.manifest import ManifestLoader
    from aiqe.shared.exceptions import PluginManifestError

    plugin_path = Path(plugin_dir).resolve()

    if not plugin_path.exists():
        print_error(f"Path '{plugin_dir}' does not exist.")
        raise typer.Exit(code=1)

    manifest_path = plugin_path / "plugin.toml"
    loader = ManifestLoader()

    try:
        manifest = loader.load_from_path(manifest_path)
    except PluginManifestError as e:
        print_error(f"Manifest validation failed:\n{e}")
        raise typer.Exit(code=1)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        raise typer.Exit(code=1)

    print_success(f"Plugin manifest is valid: {manifest.name} v{manifest.version}")
    console.print(f"\n[bold]Validation Summary:[/bold]")
    console.print(f"  Name:             {manifest.name}")
    console.print(f"  Type:             {manifest.plugin_type}")
    console.print(f"  Capabilities:     {len(manifest.required_capabilities)}")
    console.print(
        f"  Has Restricted:   "
        f"{'[yellow]Yes[/yellow]' if manifest.has_restricted_capabilities else '[green]No[/green]'}"
    )
    console.print(f"  Max Risk Level:   {manifest.max_risk_level}/4")

    if manifest.has_restricted_capabilities:
        print_warning(
            "This plugin requests restricted capabilities. "
            "Users will be prompted for approval before loading."
        )


@plugins_app.command("capabilities")
def plugins_capabilities(
    group: Optional[str] = typer.Option(
        None,
        "--group", "-g",
        help="Filter by capability group (filesystem/browser/git/network/secrets/system/database).",
    ),
    show_restricted_only: bool = typer.Option(
        False,
        "--restricted",
        help="Show only restricted (high-risk) capabilities.",
    ),
) -> None:
    """
    List all available plugin capabilities.

    Shows what capabilities plugins can request in their manifests.

    Examples:
    \b
      aiqe plugins capabilities
      aiqe plugins capabilities --group browser
      aiqe plugins capabilities --restricted
    """
    from aiqe.plugins.capabilities import Capabilities, CapabilityGroup
    from rich.table import Table
    from rich import box

    caps = Capabilities.all()

    if group:
        try:
            cap_group = CapabilityGroup(group.lower())
            caps = [c for c in caps if c.group == cap_group]
        except ValueError:
            valid = [g.value for g in CapabilityGroup]
            print_error(
                f"Unknown group '{group}'. Valid groups: {valid}"
            )
            raise typer.Exit(code=1)

    if show_restricted_only:
        caps = [c for c in caps if c.is_restricted]

    if not caps:
        print_info("No capabilities match the given filters.")
        return

    table = Table(
        title=f"Plugin Capabilities ({len(caps)} total)",
        box=box.ROUNDED,
        border_style="blue",
        show_header=True,
    )
    table.add_column("Capability ID", width=35)
    table.add_column("Group", width=12)
    table.add_column("Display Name", width=25)
    table.add_column("Risk", width=6)
    table.add_column("Restricted", width=10)

    for cap in sorted(caps, key=lambda c: (c.group.value, c.id)):
        risk_color = {
            1: "green", 2: "blue", 3: "yellow", 4: "red"
        }.get(cap.risk_level, "white")

        table.add_row(
            f"[dim]{cap.id}[/dim]",
            cap.group.value,
            cap.display_name,
            f"[{risk_color}]{cap.risk_level}[/{risk_color}]",
            "[red]YES[/red]" if cap.is_restricted else "[green]No[/green]",
        )

    console.print(table)
    console.print(
        f"\n[dim]Use these IDs in your plugin's plugin.toml "
        f"under [plugin.capabilities] required = [\"id\", ...][/dim]"
    )
