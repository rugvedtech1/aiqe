"""
AIQE Common Utilities.

Small, stateless helper functions used across AIQE modules.
Nothing in this file should import from other AIQE modules
(it sits at the very bottom of the dependency graph).
"""

from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)


def slugify(text: str) -> str:
    """
    Convert a string to a URL/filename-safe slug.

    Example:
        slugify("My Feature: User Authentication!") -> "my-feature-user-authentication"

    Args:
        text: The string to slugify.

    Returns:
        Lowercase slug with only letters, numbers, and hyphens.
    """
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return re.sub(r"^-+|-+$", "", text)


def truncate(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate a string to a maximum length, adding a suffix if truncated.

    Args:
        text: The string to truncate.
        max_length: Maximum length including the suffix.
        suffix: String to append when truncated.

    Returns:
        Original string if within limit, otherwise truncated with suffix.
    """
    if len(text) <= max_length:
        return text
    return text[: max_length - len(suffix)] + suffix


def hash_content(content: str) -> str:
    """
    Compute a SHA-256 hash of a string.

    Used for:
    - Detecting whether file content has changed between runs
    - Deduplicating test cases
    - Cache keys in the AI Gateway prompt cache

    Args:
        content: The string to hash.

    Returns:
        Hex-encoded SHA-256 hash string.
    """
    return hashlib.sha256(content.encode()).hexdigest()


def ensure_directory(path: Path) -> Path:
    """
    Ensure a directory exists, creating it and all parents if needed.

    Args:
        path: The directory path to ensure exists.

    Returns:
        The same path, guaranteed to exist.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def format_duration(seconds: float) -> str:
    """
    Format a duration in seconds to a human-readable string.

    Examples:
        format_duration(0.5)    -> "500ms"
        format_duration(1.5)    -> "1.5s"
        format_duration(90.0)   -> "1m 30s"
        format_duration(3661.0) -> "1h 1m 1s"

    Args:
        seconds: Duration in seconds.

    Returns:
        Human-readable duration string.
    """
    if seconds < 1:
        return f"{seconds * 1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes = int(seconds // 60)
    remaining_seconds = int(seconds % 60)
    if minutes < 60:
        return f"{minutes}m {remaining_seconds}s"
    hours = int(minutes // 60)
    remaining_minutes = int(minutes % 60)
    return f"{hours}h {remaining_minutes}m {remaining_seconds}s"


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """
    Deep merge two dictionaries, with override taking precedence.

    Unlike dict.update(), this recursively merges nested dicts
    rather than replacing them entirely.

    Args:
        base: The base dictionary.
        override: Values in this dict override values in base.

    Returns:
        New merged dictionary (base and override are not modified).
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
) -> list[float]:
    """
    Generate a list of delay intervals for exponential backoff retries.

    Used by the AI Gateway Retry Manager to space out retry attempts.
    Adds jitter to prevent thundering herd when many workflows retry
    simultaneously.

    Args:
        max_attempts: Number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap in seconds.
        exponential_base: The base for exponential growth.

    Returns:
        List of delay values in seconds for each retry attempt.
    """
    import random
    delays = []
    for attempt in range(max_attempts):
        delay = min(base_delay * (exponential_base ** attempt), max_delay)
        # Add ±10% jitter to prevent thundering herd
        jitter = delay * 0.1 * (2 * random.random() - 1)
        delays.append(max(0.0, delay + jitter))
    return delays


class Timer:
    """
    Context manager for measuring execution duration.

    Usage:
        with Timer() as t:
            do_something()
        print(f"Took: {t.elapsed_seconds}s")
        print(f"Took: {format_duration(t.elapsed_seconds)}")
    """

    def __init__(self) -> None:
        self._start: float = 0.0
        self._end: float = 0.0

    def __enter__(self) -> Timer:
        self._start = time.perf_counter()
        return self

    def __exit__(self, *args: object) -> None:
        self._end = time.perf_counter()

    @property
    def elapsed_seconds(self) -> float:
        """Elapsed time in seconds."""
        if self._end == 0.0:
            return time.perf_counter() - self._start
        return self._end - self._start

    @property
    def elapsed_ms(self) -> float:
        """Elapsed time in milliseconds."""
        return self.elapsed_seconds * 1000
