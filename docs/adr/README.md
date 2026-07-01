# Architecture Decision Records

ADRs capture *why* AIQE is built the way it is, not just what was built.
Every major architectural decision is recorded here with full reasoning and
alternatives considered. New contributors must read all ADRs before proposing
structural changes to the codebase.

| ADR | Title | Status |
|---|---|---|
| [0001](0001-async-workflow-engine.md) | Workflow Engine built on asyncio | Accepted |
| [0002](0002-repository-pattern-persistence.md) | Repository Pattern for persistence | Accepted |
| [0003](0003-plugin-security-capability-model.md) | Plugin Security — Capability-Based Permission Model | Accepted |
| [0004](0004-tiered-agent-build-order.md) | 15-agent vision, tiered build order | Accepted |
| [0005](0005-ai-gateway-phased-scope.md) | AI Gateway — phased scope | Accepted |
| [0006](0006-workflow-context-isolation.md) | Workflow Context Isolation | Accepted |
| [0007](0007-application-dependency-intelligence.md) | Application Dependency Intelligence | Accepted |
| [0008](0008-bug-severity-and-confidence.md) | Bug Severity System with Confidence Scores | Accepted |
| [0009](0009-no-auto-production-modification.md) | No Automatic Production Code Modification | Accepted |
| [0010](0010-release-intelligence-engine.md) | Release Intelligence Engine | Accepted |
| [0011](0011-explainability-first.md) | Explainability First | Accepted |
| [0012](0012-auditability-and-traceability.md) | Auditability and Traceability | Accepted |

## Format

Each ADR contains:
- **Decision** — what was decided
- **Why** — the reasoning
- **Alternatives Considered** — what was rejected and why
- **Status** — Proposed / Accepted / Superseded
