# ADR-0002: Repository Pattern for Persistence (SQLite/Postgres Interchangeable)

**Status:** Accepted

---

## Decision

All data access goes through repository interfaces defined as Python Protocols
in the domain layer. Example interfaces: `ProjectRepository`,
`TestRunRepository`, `CheckpointRepository`, `WorkflowContextRepository`.

SQLite and Postgres implementations live in the infrastructure layer and are
selected via configuration. No SQL dialect leaks into business logic or agent
code. The domain layer never imports a database driver directly.

The query layer uses SQLAlchemy Core (not the full ORM) for portability, with
explicit repository methods as the only access point.

---

## Why

Local CLI mode needs zero-setup SQLite (no server, no installation, just a
file). Enterprise mode needs Postgres for concurrent workflow execution and
scale.

If SQL dialect or driver-specific code leaks into agent logic now, switching
to Postgres later means rewriting agent code, not just swapping a driver.
Introducing the repository interface costs one extra abstraction layer upfront.
Not introducing it costs a full rewrite and regression risk at enterprise
readiness time.

---

## Alternatives Considered

**SQLAlchemy ORM as the abstraction.**
Considered. Rejected in favor of explicit repository interfaces over
SQLAlchemy Core because: the full ORM couples domain objects to ORM-managed
lifecycles (sessions, lazy loading, identity maps), which adds complexity that
is not necessary for AIQE's access patterns. Core gives SQL portability without
forcing the ORM model onto domain classes.

**Single database (Postgres everywhere).**
Rejected. Requiring Postgres for local/CLI mode creates significant onboarding
friction for individual developers, startups, and open-source contributors.
