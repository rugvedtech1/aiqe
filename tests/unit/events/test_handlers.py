"""Unit tests for built-in event handlers."""
import pytest
from aiqe.events.handlers import AuditHandler, NotificationHandler
from aiqe.workflow.events import BugFound, WorkflowCompleted
from dataclasses import dataclass
from aiqe.shared.domain import DomainEvent


class TestAuditHandler:
    @pytest.mark.asyncio
    async def test_appends_to_audit_log(self):
        audit_log = []
        handler = AuditHandler(audit_log=audit_log)

        event = BugFound(
            workflow_id="wf_1",
            bug_id="bug_001",
            severity="Critical",
            confidence=0.97,
            title="SQL Injection",
        )
        await handler.handle(event)

        assert len(audit_log) == 1
        assert audit_log[0]["event_type"] == "bug_found"

    @pytest.mark.asyncio
    async def test_handles_multiple_events(self):
        audit_log = []
        handler = AuditHandler(audit_log=audit_log)

        await handler.handle(BugFound(workflow_id="wf_1", bug_id="b1",
                                       severity="High", confidence=0.8, title="t"))
        await handler.handle(WorkflowCompleted(workflow_id="wf_1"))

        assert len(audit_log) == 2


class TestNotificationHandler:
    @pytest.mark.asyncio
    async def test_critical_bug_triggers_callback(self):
        triggered = []

        async def mock_notify(event):
            triggered.append(event.bug_id)

        handler = NotificationHandler(notify_callbacks=[mock_notify])

        await handler.handle(BugFound(
            workflow_id="wf_1",
            bug_id="bug_001",
            severity="Critical",
            confidence=0.97,
            title="SQL Injection",
        ))

        assert "bug_001" in triggered

    @pytest.mark.asyncio
    async def test_non_critical_does_not_trigger(self):
        triggered = []

        async def mock_notify(event):
            triggered.append(event)

        handler = NotificationHandler(notify_callbacks=[mock_notify])

        await handler.handle(BugFound(
            workflow_id="wf_1",
            bug_id="bug_002",
            severity="Medium",
            confidence=0.6,
            title="Minor issue",
        ))

        assert len(triggered) == 0

    @pytest.mark.asyncio
    async def test_non_bug_event_ignored(self):
        triggered = []

        async def mock_notify(event):
            triggered.append(event)

        handler = NotificationHandler(notify_callbacks=[mock_notify])
        await handler.handle(WorkflowCompleted(workflow_id="wf_1"))

        assert len(triggered) == 0
