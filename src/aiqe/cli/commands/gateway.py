"""
AIQE CLI — gateway command group.

Usage:
    aiqe gateway status
    aiqe gateway test
    aiqe gateway providers
"""

from __future__ import annotations

import typer

from aiqe.cli.console import (
    console,
    print_error,
    print_gateway_status,
    print_info,
    print_success,
    print_warning,
)

gateway_app = typer.Typer(help="Manage and test the AI Gateway.")


@gateway_app.command("status")
def gateway_status() -> None:
    """Show AI Gateway status and usage statistics."""
    try:
        from aiqe.gateway.gateway import get_gateway
        gateway = get_gateway()
        stats_obj = gateway.stats

        stats = {
            "total_requests": stats_obj.total_requests,
            "total_tokens": stats_obj.total_tokens,
            "total_errors": stats_obj.total_errors,
            "requests_by_provider": stats_obj.requests_by_provider,
            "tokens_by_provider": stats_obj.tokens_by_provider,
            "errors_by_provider": stats_obj.errors_by_provider,
        }

        providers = gateway.available_providers()

        if providers:
            print_success(
                f"AI Gateway ready. "
                f"Available providers: {', '.join(providers)}"
            )
        else:
            print_warning(
                "No AI providers available. "
                "Check API keys in your .env file."
            )

        print_gateway_status(stats)

    except Exception as e:
        print_error(f"Gateway status check failed: {e}")
        print_info(
            "Ensure at least one API key is configured in .env. "
            "See .env.example for required keys."
        )
        raise typer.Exit(code=1)


@gateway_app.command("test")
def gateway_test(
    provider: str = typer.Option(
        "default",
        "--provider", "-p",
        help="Provider to test (default uses configured default).",
    ),
    message: str = typer.Option(
        "Say 'AIQE gateway test successful' and nothing else.",
        "--message", "-m",
        help="Test message to send to the AI provider.",
    ),
) -> None:
    """
    Send a test message to verify AI provider connectivity.

    Examples:
    \b
      aiqe gateway test
      aiqe gateway test --provider anthropic
      aiqe gateway test --provider openai --message "Hello"
    """
    import asyncio

    try:
        asyncio.run(_run_gateway_test(provider, message))
    except Exception as e:
        print_error(f"Gateway test failed: {e}")
        raise typer.Exit(code=1)


async def _run_gateway_test(provider: str, message: str) -> None:
    """Run a test completion request against the gateway."""
    from aiqe.gateway.gateway import get_gateway
    from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage

    gateway = get_gateway()

    preferred = None if provider == "default" else provider

    print_info(
        f"Sending test request to "
        f"{'default provider' if not preferred else preferred}..."
    )

    request = AIRequest(
        messages=[PromptMessage.user(message)],
        task_type=AITaskType.QUICK,
        max_tokens=50,
        preferred_provider=preferred,
        workflow_id="cli-test",
        agent_name="cli-gateway-test",
        prompt_version="1.0",
    )

    response = await gateway.complete(request)

    print_success("Gateway test successful!")
    console.print(f"\n  [bold]Provider:[/bold] {response.provider}")
    console.print(f"  [bold]Model:[/bold]    {response.model}")
    console.print(f"  [bold]Tokens:[/bold]   {response.total_tokens}")
    console.print(f"  [bold]Latency:[/bold]  {response.latency_seconds:.2f}s")
    console.print(f"\n  [bold]Response:[/bold]")
    console.print(f"  [green]{response.content.strip()}[/green]")


@gateway_app.command("providers")
def gateway_providers() -> None:
    """List all configured AI providers and their key availability."""
    try:
        from aiqe.gateway.gateway import get_gateway
        from rich.table import Table
        from rich import box

        gateway = get_gateway()
        available = gateway.available_providers()
        key_stats = gateway._key_manager.stats()

        table = Table(
            title="AI Provider Configuration",
            box=box.ROUNDED,
            border_style="blue",
        )
        table.add_column("Provider", width=15)
        table.add_column("Status", width=12)
        table.add_column("Keys", width=8)
        table.add_column("Available", width=10)

        for provider, stats in key_stats.items():
            is_available = provider in available
            status_str = (
                "[green]✓ Ready[/green]"
                if is_available
                else "[red]✗ Unavailable[/red]"
            )
            table.add_row(
                provider,
                status_str,
                str(stats.get("total_keys", 0)),
                str(stats.get("available_keys", 0)),
            )

        console.print(table)

        if not available:
            print_warning(
                "No providers available. "
                "Add API keys to your .env file."
            )

    except Exception as e:
        print_error(f"Failed to list providers: {e}")
        raise typer.Exit(code=1)
