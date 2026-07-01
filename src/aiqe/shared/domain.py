"""
AIQE Domain Primitives.

Base classes for all domain objects in AIQE, following
Domain-Driven Design (DDD) principles.

Why DDD?
    AIQE's domain is complex: workflows contain agents that produce
    test cases that are executed to find bugs that have severity and
    confidence scores that feed into release recommendations. Without
    clear domain modeling, this complexity collapses into a tangle of
    dicts and strings that no one can maintain.

    DDD gives us:
    - Entities: objects with unique identity that change over time
      (WorkflowContext, TestRun, Agent)
    - Value Objects: immutable objects defined by their content, not
      their identity (BugSeverity, ConfidenceScore, Capability)
    - Aggregate Roots: entities that own and protect a cluster of
      related domain objects (WorkflowContext owns its checkpoints)
    - Domain Events: things that happened in the domain that other
      parts of the system may care about (TestFailed, AgentCompleted)

Three rules enforced here:
    1. Entities are equal if and only if their IDs are equal.
    2. Value Objects are equal if and only if all their fields are equal.
    3. Domain Events are immutable once created.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utcnow() -> datetime:
    """Return the current UTC time as a timezone-aware datetime."""
    return datetime.now(tz=timezone.utc)


def _new_id() -> str:
    """Generate a new unique identifier."""
    return str(uuid.uuid4())


# ==================================================
# ENTITY BASE CLASS
# ==================================================


@dataclass
class Entity(ABC):
    """
    Base class for all AIQE domain entities.

    An Entity is a domain object that has a unique identity that
    persists over time, even as its attributes change.

    Example entities in AIQE:
        WorkflowContext — has an ID, its state changes as agents run
        TestRun — has an ID, its results accumulate over time
        Agent — has an ID and a registration record

    Identity rules:
        Two Entity instances are equal if and only if their id fields
        are equal, regardless of any other attribute values. This
        matches real-world semantics: the same workflow at two different
        points in time is still the same workflow.

    Attributes:
        id: Unique identifier for this entity. Auto-generated if not provided.
        created_at: When this entity was first created.
        updated_at: When this entity was last modified.
    """

    id: str = field(default_factory=_new_id)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self.id == other.id

    def __hash__(self) -> int:
        return hash(self.id)

    def touch(self) -> None:
        """Update the updated_at timestamp to now."""
        self.updated_at = _utcnow()

    def to_dict(self) -> dict[str, Any]:
        """
        Convert entity to a dictionary for persistence.

        Subclasses should override this to include all domain attributes.
        Always call super().to_dict() and merge with the subclass dict.
        """
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


# ==================================================
# VALUE OBJECT BASE CLASS
# ==================================================


@dataclass(frozen=True)
class ValueObject(ABC):
    """
    Base class for all AIQE value objects.

    A Value Object is a domain object that has no identity of its own.
    It is defined entirely by its attribute values. Two Value Objects
    with identical attributes are interchangeable.

    frozen=True enforces immutability at the Python level.
    Value Objects must never be modified after creation.

    Example value objects in AIQE:
        BugSeverity — Critical/High/Medium/Low/Informational
        ConfidenceScore — a percentage 0-100
        Capability — a named plugin permission
        WorkflowStatus — Pending/Running/Completed/Failed

    Identity rules:
        Two Value Objects are equal if all their fields are equal.
        This is enforced automatically by dataclass(frozen=True, eq=True).
    """

    def __post_init__(self) -> None:
        """Validate value object invariants after construction."""
        self._validate()

    @abstractmethod
    def _validate(self) -> None:
        """
        Validate that this value object is in a valid state.

        Raise ValueError if any invariant is violated. Value objects
        must always be in a valid state — invalid ones should never exist.
        """


# ==================================================
# AGGREGATE ROOT BASE CLASS
# ==================================================


@dataclass
class AggregateRoot(Entity, ABC):
    """
    Base class for AIQE aggregate roots.

    An Aggregate Root is an Entity that is the single point of
    access for a cluster of related domain objects. External code
    interacts only with the root; never directly with the objects
    it contains.

    Why aggregates?
        They enforce consistency boundaries. A WorkflowContext owns
        its checkpoints and test results. Code outside the context
        cannot directly modify a checkpoint — it must go through the
        context, which enforces isolation rules (ADR-006).

    Domain events:
        Aggregate Roots collect domain events as side effects of
        business operations. Events are collected internally and
        dispatched by the infrastructure layer after persistence.
        This separates what happened from what should happen next.

    Example aggregate roots in AIQE:
        WorkflowContext — owns checkpoints, agent states, test results
    """

    _domain_events: list[DomainEvent] = field(
        default_factory=list,
        init=False,
        repr=False,
        compare=False,
    )

    def record_event(self, event: DomainEvent) -> None:
        """
        Record a domain event that occurred within this aggregate.

        Events are collected here and dispatched after the aggregate
        is persisted. This ensures events are only published for
        changes that were actually saved.

        Args:
            event: The domain event that occurred.
        """
        self._domain_events.append(event)

    def collect_events(self) -> list[DomainEvent]:
        """
        Collect and clear all pending domain events.

        Called by the infrastructure layer after the aggregate is
        persisted. Events are cleared after collection so they are
        only dispatched once.

        Returns:
            List of domain events accumulated since last collection.
        """
        events = list(self._domain_events)
        self._domain_events.clear()
        return events


# ==================================================
# DOMAIN EVENT BASE CLASS
# ==================================================


@dataclass(frozen=True)
class DomainEvent(ABC):
    """
    Base class for all AIQE domain events.

    A Domain Event represents something that happened in the domain
    that other parts of the system may need to react to. Events are
    facts — they describe what happened, not what should happen next.

    Events are immutable. They represent the past and cannot be changed.

    Example events in AIQE:
        WorkflowStarted(workflow_id, pr_number, timestamp)
        AgentCompleted(workflow_id, agent_name, duration, timestamp)
        TestFailed(workflow_id, test_id, severity, confidence, timestamp)
        CheckpointSaved(workflow_id, stage, timestamp)
        CriticalBugFound(workflow_id, bug_id, severity, confidence, timestamp)

    Attributes:
        event_id: Unique identifier for this event occurrence.
        occurred_at: When this event occurred (UTC).
        workflow_id: The workflow context this event belongs to.
    """

    event_id: str = field(default_factory=_new_id)
    occurred_at: datetime = field(default_factory=_utcnow)
    workflow_id: str | None = None

    @property
    @abstractmethod
    def event_type(self) -> str:
        """
        The event type name used in the event bus and audit trail.

        Use snake_case. Example: "workflow_started", "test_failed".
        """

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dict for audit trail persistence."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "workflow_id": self.workflow_id,
        }
