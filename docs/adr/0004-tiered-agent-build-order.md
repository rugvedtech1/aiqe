# ADR-0004: 15-Agent Vision Preserved, Tiered Build Order

**Status:** Accepted

---

## Decision

All 15 agents remain part of the AIQE architecture. The Agent Registry is
designed to support all 15 agent contracts. Implementation follows a tiered
order based on dependency and data availability:

**Tier 1 — Core (build first)**
- Orchestrator Agent
- Project Analysis Agent
- Test Strategy Agent
- Test Case Generator Agent

**Tier 2 — Execution**
- Automation Generator Agent
- Browser Execution Agent
- API Validation Agent

**Tier 3 — Quality**
- Security Testing Agent
- Performance Agent
- Database Validation Agent

**Tier 4 — Intelligence (build last)**
- Bug Analysis Agent
- Memory & Learning Agent
- Report Agent
- Feature Discovery Agent
- Requirement Intelligence Agent

---

## Why

Tier 4 agents — especially Bug Analysis and Memory & Learning — require real
execution data to be designed well. Building them before Tier 1 and Tier 2
agents are running means designing their inputs, learning models, and memory
schemas against guesses rather than real failure patterns.

Tier 1 agents unblock everything else. The Orchestrator must exist before any
other agent can run. Project Analysis must run before Test Strategy can
generate a meaningful plan. Test Strategy must run before Test Case Generator
has context.

The tiered approach delivers value incrementally without architectural
shortcuts that would require redesigning interfaces when later tiers are built.

---

## Alternatives Considered

**Build all 15 agents simultaneously.**
Rejected. No engineering team can design 15 distinct interfaces, prompt
contracts, input/output schemas, and failure modes in parallel without
introducing inconsistencies. Tier 4 agent designs made without real data
will need to be redesigned after Tier 1 and 2 run in production.
