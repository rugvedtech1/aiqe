# ADR-0006: Workflow Context Isolation

**Status:** Accepted

---

## Decision

Every Pull Request, Branch, Local Execution, Scheduled Run, or Manual
Execution creates its own Workflow Context. Workflow Contexts are completely
isolated from each other.

A Workflow Context contains:
- Execution State
- Agent State
- Shared Memory
- Checkpoints
- Logs
- Reports
- Test Results
- Generated Artifacts

No workflow may access or modify another workflow's runtime state.

**The only exception:** The Memory & Learning Agent may access historical
workflow data in READ-ONLY mode for regression analysis, quality improvement,
and learning. This exception is explicit, controlled, and audited.

This rule must never be violated.

---

## Why

Enterprise engineering teams run multiple PRs, branches, CI runs, and manual
executions simultaneously. If workflow contexts share state, a failure in one
workflow can corrupt results in another. Debugging becomes impossible because
it is unclear which workflow produced which state.

Isolation also enables:
- Accurate per-PR quality reports
- Safe parallel execution with no race conditions
- Clear audit trails per execution context
- Reliable regression detection (comparing isolated context to historical data)

---

## Alternatives Considered

**Shared global memory for all workflows.**
Rejected. Introduces state contamination between concurrent executions, makes
debugging failures nearly impossible, and prevents accurate per-PR reporting.

**Partial isolation (share some state, isolate execution).**
Rejected. Any shared mutable state between workflows is a race condition
waiting to happen. The Memory & Learning Agent READ-ONLY exception is
designed specifically to allow learning from history without introducing
mutable shared state at runtime.
