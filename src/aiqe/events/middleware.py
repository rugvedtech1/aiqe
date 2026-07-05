"""
AIQE Event Bus Middleware.

Middleware wraps the EventBus to add cross-cutting behaviour
to every event publication, without modifying the bus itself.

Current middleware:
    LoggingMiddleware — structured log entry for every published event.

Why middleware instead of a wildcard handler?
    A wildcard handler runs AFTER the bus dispatches events to handlers.
    Middleware wraps the publish() call itself, so it can log before
    AND after dispatch, measure dispatch latency, and catch errors
    that happen inside publish() itself.
"""

from __future__ import annotations

from typing import Any

from aiqe.events.bus import EventBus
from aiqe.shared.domain import DomainEvent
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import Timer

logger = get_logger(__name__)


class LoggingMiddleware:
    """
    Wraps an EventBus to add structured logging around every publish.

    Records:
    - Event type and ID
    - Workflow context
    - Number of handlers invoked
    - Dispatch latency

    Args:
        bus: The EventBus to wrap.
    """

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    async def publish(self, event: DomainEvent) -> int:
        """
        Publish an event with timing and structured logging.

        Args:
            event: The event to publish.

        Returns:
            Number of handlers that were invoked.
        """
        with Timer() as timer:
            handler_count = await self._bus.publish(event)

        logger.info(
            "event_dispatched",
            event_type=event.event_type,
            event_id=event.event_id,
            workflow_id=event.workflow_id,
            handler_count=handler_count,
            dispatch_ms=timer.elapsed_ms,
        )

        return handler_count

    def subscribe(self, event_type: str, handler: Any) -> None:
        """Delegate subscription to the wrapped bus."""
        self._bus.subscribe(event_type, handler)

    def unsubscribe(self, event_type: str, handler: Any) -> bool:
        """Delegate unsubscription to the wrapped bus."""
        return self._bus.unsubscribe(event_type, handler)

    @property
    def stats(self) -> dict[str, Any]:
        """Delegate stats to the wrapped bus."""
        return self._bus.stats
