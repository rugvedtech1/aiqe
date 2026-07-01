"""
AIQE Structured Logging.

Uses structlog to produce structured (JSON) log output that is:
- Machine-readable for log aggregators (Datadog, Splunk, CloudWatch)
- Human-readable in development (colored console output)
- Audit-ready (every log entry carries workflow_id, agent_name, timestamp)
- Secret-safe (sensitive fields are automatically redacted)

Why structlog over Python's built-in logging?
    Python's logging module produces unstructured text. Structured logs
    carry key-value context (workflow_id, agent_name, provider, etc.)
    that makes filtering, alerting, and auditing vastly easier. structlog
    integrates with Python's logging module so third-party libraries that
    use standard logging still work correctly.

Usage:
    from aiqe.shared.logging import get_logger

    logger = get_logger(__name__)
    logger.info("agent_started", agent="ProjectAnalysisAgent", workflow_id="abc123")
    logger.error("provider_failed", provider="openai", status_code=429)
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

# Fields that must never appear in log output under any circumstances.
# If any log record contains these keys, their values are replaced.
_REDACTED_FIELDS = frozenset({
    "api_key",
    "secret",
    "password",
    "token",
    "credential",
    "private_key",
    "encryption_key",
    "database_url",
    "postgres_password",
    "openai_api_key",
    "anthropic_api_key",
    "gemini_api_key",
    "groq_api_key",
    "github_token",
    "slack_bot_token",
})

_REDACTED_MARKER = "[REDACTED]"


def _redact_secrets(
    logger: WrappedLogger,
    method: str,
    event_dict: EventDict,
) -> EventDict:
    """
    structlog processor that redacts sensitive fields from log output.

    This processor runs on every log record before it is emitted.
    It checks every key in the event dict against the redacted fields
    list and replaces any matches with [REDACTED].

    Why a processor instead of filtering at the call site?
        Relying on engineers to remember never to log secrets is
        unreliable. A processor enforces the rule automatically and
        consistently, even for secrets that accidentally enter the
        event dict through context binding.
    """
    for key in list(event_dict.keys()):
        if key.lower() in _REDACTED_FIELDS:
            event_dict[key] = _REDACTED_MARKER
    return event_dict


def _add_aiqe_context(
    logger: WrappedLogger,
    method: str,
    event_dict: EventDict,
) -> EventDict:
    """
    structlog processor that adds AIQE-specific fields to every log record.

    Ensures every log record carries:
    - service: always "aiqe" (useful when logs from multiple services
      are aggregated into one log stream)
    - log_level: normalized level name
    """
    event_dict.setdefault("service", "aiqe")
    event_dict["log_level"] = method.upper()
    return event_dict


def configure_logging(
    log_level: str = "INFO",
    json_output: bool = False,
) -> None:
    """
    Configure AIQE's logging system.

    Must be called once at application startup before any logging occurs.
    Called by the CLI entrypoint and the FastAPI startup event.

    Args:
        log_level: Minimum log level to emit. One of:
                   DEBUG, INFO, WARNING, ERROR, CRITICAL.
        json_output: If True, emit JSON (for production/CI).
                     If False, emit colored console output (for development).

    Why call this explicitly instead of auto-configuring?
        Different entry points (CLI, FastAPI, GitHub Action, tests) have
        different output requirements. The CLI wants colored output.
        CI/CD wants JSON for log aggregators. Tests want minimal output.
        Explicit configuration lets each entry point choose correctly.
    """
    # Configure Python's standard logging to route through structlog.
    # This captures logs from third-party libraries automatically.
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    # Processors run in order on every log record.
    # The order matters — redaction must happen before rendering.
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,   # merge bound context vars
        structlog.stdlib.add_logger_name,          # add module name
        structlog.stdlib.add_log_level,            # add level name
        structlog.processors.TimeStamper(fmt="iso"),  # ISO 8601 timestamp
        _add_aiqe_context,                         # add service="aiqe"
        _redact_secrets,                           # MUST run before rendering
        structlog.processors.StackInfoRenderer(),  # render stack traces
        structlog.processors.format_exc_info,      # render exception info
    ]

    if json_output:
        # Production / CI: machine-readable JSON
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        # Development: human-readable colored console output
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger for the given module name.

    This is the single function every AIQE module uses to get a logger.
    Always pass __name__ as the argument.

    Args:
        name: The module name. Always pass __name__.

    Returns:
        A structlog BoundLogger that supports key-value context binding.

    Example:
        logger = get_logger(__name__)
        logger.info("workflow_started", workflow_id="abc123", pr_number=42)
        logger.error("agent_failed", agent="BrowserExecutionAgent", error=str(e))

        # Bind context that appears on all subsequent log calls
        bound = logger.bind(workflow_id="abc123", agent="OrchestratorAgent")
        bound.info("starting")
        bound.info("checkpoint_saved", stage="project_analysis")
    """
    return structlog.get_logger(name)


def bind_workflow_context(workflow_id: str, **kwargs: Any) -> None:
    """
    Bind workflow context variables so they appear on every log record
    within the current async task or thread without passing them explicitly.

    Call this at the start of every workflow execution. All log records
    produced within that execution context will automatically carry
    workflow_id without needing to pass it to every logger call.

    Args:
        workflow_id: The unique ID of the current workflow context.
        **kwargs: Additional context to bind (e.g. agent_name, pr_number).

    Example:
        bind_workflow_context(
            workflow_id="wf_abc123",
            pr_number=42,
            repository="rugvedtech1/aiqe",
        )
        # All subsequent logger calls in this context carry these fields
        logger.info("test_started")
        # Output: {"event": "test_started", "workflow_id": "wf_abc123", "pr_number": 42}
    """
    structlog.contextvars.bind_contextvars(
        workflow_id=workflow_id,
        **kwargs,
    )


def clear_workflow_context() -> None:
    """
    Clear all bound workflow context variables.

    Call this when a workflow context ends to prevent context bleeding
    into the next workflow. Critical for ADR-006 (Workflow Isolation).
    """
    structlog.contextvars.clear_contextvars()
