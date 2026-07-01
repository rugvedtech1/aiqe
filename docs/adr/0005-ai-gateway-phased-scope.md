# ADR-0005: AI Gateway — Core Routing First, Optimization Fast-Follow

**Status:** Accepted

---

## Decision

The AI Gateway is built in two phases:

**Phase 1 (ship with core system):**
- Provider Manager — manages multiple AI provider configurations
- API Key Manager — multi-key rotation, key validation
- Retry Manager — exponential backoff, provider failover

**Phase 2 (fast-follow after real usage telemetry exists):**
- Cost Optimizer
- Prompt Cache
- Token Budget Manager
- Privacy Routing
- Health Monitor

The Gateway's public interface (`AIGateway.complete()`,
`AIGateway.embed()`) is designed now to accommodate Phase 2 features
without breaking changes. Phase 2 features are added behind the same
interface without touching agent code.

---

## Why

Optimizing cost, caching prompts, and routing by privacy requirements
requires real request data to optimize against. Building these before
the system has production traffic means optimizing against assumptions.

Phase 1 unblocks every agent immediately. Phase 2 can be added incrementally
as usage patterns become clear.

---

## Alternatives Considered

**Build all Gateway features simultaneously.**
Rejected. Cost Optimizer without real token usage data is guesswork.
Prompt Cache without knowing which prompts are repeated is premature.
Token Budget Manager without knowing typical workflow token consumption
produces arbitrary budgets. Building these correctly requires data that
does not exist until Phase 1 has been running.
