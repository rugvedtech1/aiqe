"""Unit tests for EventBus."""
import pytest
from aiqe.events.bus import EventBus, WorkflowEventBus
from aiqe.shared.domain import DomainEvent
from dataclasses import dataclass


@dataclass(frozen=True)
class TestEvent(DomainEvent):
    message: str = ""

    @property
    def event_type(self) -> str:
        return "test_event"


@dataclass(frozen=True)
class AnotherEvent(DomainEvent):
    value: int = 0

    @property
    def event_type(self) -> str:
        return "another_event"


@pytest.fixture
def bus():
    return EventBus(scope="test")


class TestEventBus:
    @pytest.mark.asyncio
    async def test_publish_calls_subscribed_handler(self, bus):
        received = []

        async def handler(event: DomainEvent) -> None:
            received.append(event)

        bus.subscribe("test_event", handler)
        event = TestEvent(workflow_id="wf_1", message="hello")
        count = await bus.publish(event)

        assert count == 1
        assert len(received) == 1
        assert received[0].message == "hello"

    @pytest.mark.asyncio
    async def test_wildcard_receives_all_events(self, bus):
        received = []

        async def catch_all(event: DomainEvent) -> None:
            received.append(event.event_type)

        bus.subscribe(EventBus.WILDCARD, catch_all)

        await bus.publish(TestEvent(workflow_id="wf_1"))
        await bus.publish(AnotherEvent(workflow_id="wf_1"))

        assert "test_event" in received
        assert "another_event" in received

    @pytest.mark.asyncio
    async def test_no_handlers_returns_zero(self, bus):
        event = TestEvent(workflow_id="wf_1")
        count = await bus.publish(event)
        assert count == 0

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_propagate(self, bus):
        async def bad_handler(event: DomainEvent) -> None:
            raise RuntimeError("handler error")

        bus.subscribe("test_event", bad_handler)
        # Should not raise
        await bus.publish(TestEvent(workflow_id="wf_1"))
        assert bus.stats["error_count"] == 1

    @pytest.mark.asyncio
    async def test_multiple_handlers_all_called(self, bus):
        calls = []

        async def h1(event: DomainEvent) -> None:
            calls.append("h1")

        async def h2(event: DomainEvent) -> None:
            calls.append("h2")

        bus.subscribe("test_event", h1)
        bus.subscribe("test_event", h2)
        await bus.publish(TestEvent(workflow_id="wf_1"))

        assert "h1" in calls
        assert "h2" in calls

    def test_unsubscribe(self, bus):
        async def handler(e): pass
        bus.subscribe("test_event", handler)
        removed = bus.unsubscribe("test_event", handler)
        assert removed is True

    def test_unsubscribe_nonexistent(self, bus):
        async def handler(e): pass
        removed = bus.unsubscribe("test_event", handler)
        assert removed is False

    def test_clear_handlers(self, bus):
        async def handler(e): pass
        bus.subscribe("test_event", handler)
        bus.clear_handlers()
        assert bus.stats["handler_counts"] == {}


class TestWorkflowEventBus:
    def test_scope_includes_workflow_id(self):
        wf_bus = WorkflowEventBus(workflow_id="wf_abc123")
        assert "wf_abc123" in wf_bus.stats["scope"]
        assert wf_bus.workflow_id == "wf_abc123"
