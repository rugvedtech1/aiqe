# ADR-0001: Workflow Engine Built on asyncio, Not a Custom Event System

**Status:** Accepted

---

## Decision

The AIQE Workflow Engine and Agent Registry are custom-built because they
represent AIQE's core product differentiation. However, the underlying
execution and messaging primitives use Python's `asyncio` (tasks, queues,
`asyncio.Event`) for local and CLI modes, with an adapter to Redis Streams
for enterprise multi-node deployments.

The public interface (`EventBus.publish()`, `EventBus.subscribe()`,
`WorkflowEngine.submit()`) is entirely AIQE-owned. The implementation
underneath uses proven primitives, not hand-rolled delivery guarantees.

---

## Why

Event ordering, backpressure, and at-least-once delivery are solved problems.
Hand-rolling them risks subtle bugs — lost events, race conditions, starvation
— that only surface under production load.

The Workflow Engine and Agent Registry are genuinely domain-specific and worth
owning because they encode AIQE's execution model, dependency graph traversal,
agent coordination, and checkpoint recovery. These give AIQE a competitive
advantage. The event plumbing underneath does not.

asyncio is part of the Python standard library, has no external dependencies,
is battle-tested at scale (FastAPI, aiohttp, many production systems run on
it), and is familiar to any senior Python engineer.

---

## Alternatives Considered

**Full custom event sourcing system.**
Rejected. Too much engineering surface area for pre-alpha, no product value
over asyncio, can be added later behind the same interface if requirements
demand it.

**LangGraph / CrewAI / AutoGen as the workflow core.**
Rejected. These frameworks impose their own agent models, memory abstractions,
and execution graphs on AIQE's domain. AIQE's quality engineering workflow has
specific requirements (dependency graph traversal, partial failure isolation,
per-workflow memory isolation, audit trail) that these frameworks were not
designed for. They would be adapters at best, constraints at worst.
