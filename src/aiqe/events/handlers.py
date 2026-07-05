"""
AIQE Built-in Event Handlers.

These handlers are automatically subscribed to every WorkflowEventBus.

AuditHandler     — writes every event to the workflow audit log (ADR-012).
NotificationHandler — sends immediate alerts for Critical bugs (ADR-008).

Why built-in handlers instead of external subscribers?
    These two handlers implement core architectural requirements
    (ADR-008, ADR-012) that must always be active. They are not
    optional features. Making them built-in guarantees they are
    always subscribed before the first event is published.

    Optional notification channels (Slack, Teams, GitHub) are
    implemented as separate notification plugins that subscribe
    to the same events.
"""

from __future__ import annotations

from typing import Any

from aiqe.shared.domain import DomainEvent
from aiqe.shared.logging import get_logger
from aiqe.workflow.events import BugFound, WorkflowCompleted, WorkflowFailed

logger = get_logger(__name__)


class AuditHandler:
    """
    Writes every workflow event to the audit trail.

    Implements ADR-012 (Auditability & Traceability).
    Subscribed to EventBus.WILDCARD so it receives all events.

    The audit trail is append-only — entries are never modified
    or deleted. This makes it suitable for compliance purposes.

    Args:
        audit_log: The list to append audit entries to.
                   Typically WorkflowContext.audit_log.
    """

    def __init__(self, audit_log: list[dict[str, Any]]) -> None:
        self._audit_log = audit_log

    async def handle(self, event: DomainEvent) -> None:
        """
        Append an event to the audit log.

        Args:
            event: Any domain event from the workflow event bus.
        """
        entry = event.to_dict()
        self._audit_log.append(entry)

        logger.debug(
            "audit_entry_written",
            event_type=event.event_type,
            event_id=event.event_id,
            workflow_id=event.workflow_id,
        )


class NotificationHandler:
    """
    Handles immediate notifications for Critical severity bugs.

    Implements the Hybrid Notification Strategy from ADR-008:
    - Critical bugs → notify immediately
    - High/Medium/Low/Informational → include in final report only

    Notification channels (Slack, GitHub PR comment, Teams) are
    injected as callables so this handler is testable without
    real notification infrastructure.

    Args:
        notify_callbacks: List of async callables to call for
                          Critical notifications. Each receives
                          the bug event dict.
    """

    def __init__(
        self,
        notify_callbacks: list[Any] | None = None,
    ) -> None:
        self._callbacks = notify_callbacks or []

    async def handle(self, event: DomainEvent) -> None:
        """
        Check if this is a Critical bug event and notify immediately.

        Only reacts to BugFound events with severity=Critical.
        All other events are ignored by this handler.

        Args:
            event: Any domain event.
        """
        if not isinstance(event, BugFound):
            return

        if event.severity != "Critical":
            logger.debug(
                "notification_skipped_non_critical",
                event_type=event.event_type,
                severity=event.severity,
                workflow_id=event.workflow_id,
            )
            return

        logger.info(
            "critical_bug_notification_triggered",
            workflow_id=event.workflow_id,
            bug_id=event.bug_id,
            severity=event.severity,
            confidence=event.confidence,
            title=event.title,
        )

        # Call all registered notification channels
        import asyncio
        if self._callbacks:
            results = await asyncio.gather(
                *[cb(event) for cb in self._callbacks],
                return_exceptions=True,
            )
            errors = [r for r in results if isinstance(r, Exception)]
            for error in errors:
                logger.error(
                    "notification_callback_failed",
                    workflow_id=event.workflow_id,
                    bug_id=event.bug_id,
                    error=str(error),
                )


class WorkflowSummaryHandler:
    """
    Collects workflow lifecycle events for the final summary.

    Subscribes to WorkflowCompleted and WorkflowFailed events
    and builds a summary dict that the Report Agent can use.

    Args:
        summaries: Dict to write workflow summaries into,
                   keyed by workflow_id.
    """

    def __init__(self, summaries: dict[str, Any]) -> None:
        self._summaries = summaries

    async def handle(self, event: DomainEvent) -> None:
        """Record workflow completion or failure in the summary."""
        if isinstance(event, WorkflowCompleted):
            self._summaries[event.workflow_id] = {
                "status": "completed",
                "duration_seconds": event.duration_seconds,
                "agents_completed": event.agents_completed,
                "agents_skipped": event.agents_skipped,
                "bugs_found": event.bugs_found,
            }
        elif isinstance(event, WorkflowFailed):
            self._summaries[event.workflow_id] = {
                "status": "failed",
                "error": event.error_message,
                "failed_stage": event.failed_stage,
                "is_checkpointed": event.is_checkpointed,
            }
