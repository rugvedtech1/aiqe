"""
AIQE CLI Type Definitions.

Shared types, enums, and helpers used across CLI commands.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path


class OutputFormat(str, Enum):
    """Output format for CLI commands that support multiple formats."""
    TABLE = "table"
    JSON = "json"
    MARKDOWN = "markdown"


class LogLevelChoice(str, Enum):
    """Valid log levels for the CLI --log-level option."""
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


def resolve_project_path(path: str) -> Path:
    """
    Resolve and validate a project path argument.

    Args:
        path: Path string from CLI argument (e.g. "." or "/home/user/project").

    Returns:
        Resolved absolute Path.

    Raises:
        typer.BadParameter: If the path does not exist or is not a directory.
    """
    import typer
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise typer.BadParameter(
            f"Path '{path}' does not exist.",
        )
    if not resolved.is_dir():
        raise typer.BadParameter(
            f"Path '{path}' is not a directory.",
        )
    return resolved
