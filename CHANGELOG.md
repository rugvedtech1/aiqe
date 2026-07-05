# AIQE Changelog

All notable changes to AIQE are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
AIQE follows [Semantic Versioning](https://semver.org/).

---

## [Unreleased] — Pre-Alpha

### Added — Core Architecture
- 12 Architecture Decision Records (ADR-001 through ADR-012)
- Clean Architecture with Domain-Driven Design principles
- Dependency Injection throughout all layers
- Plugin Architecture with capability-based security model

### Added — Infrastructure
- Async Workflow Engine built on Python asyncio (ADR-001)
- Workflow Context Isolation — each PR/branch/run is completely isolated (ADR-006)
- Checkpoint Manager — resume long-running workflows after failure
- Agent Registry with dependency resolution and execution wave planning
- Task Scheduler with dependency failure isolation (ADR-007)
- Shared Memory Store with TTL, snapshots, and read-only access
- Publish/subscribe Event Bus (workflow-scoped and system-scoped)
- Repository Pattern persistence layer (SQLite + Postgres, ADR-002)
- Structured logging with secret redaction (ADR-012)
- Pydantic Settings configuration with full validation

### Added — AI Gateway (ADR-005)
- Multi-provider support: OpenAI, Anthropic, Gemini, Groq, OpenRouter, Ollama
- Multi-key rotation with exponential backoff per provider
- Task Router — routes requests to best provider/model per task type
- Retry Manager with jitter-based exponential backoff
- Provider adapters: OpenAI, Anthropic, Ollama

### Added — Plugin System (ADR-003)
- Capability-based least-privilege plugin model
- 35+ fine-grained capabilities across 7 groups (Filesystem, Browser, Git, Network, Secrets, System, Database)
- Plugin manifest validation (TOML-based)
- Plugin Loader with 10-step ADR-003 security pipeline
- In-process capability enforcement via restricted interfaces
- Plugin Registry with type-based lookup

### Added — Agents (15 total)

**Tier 1 — Core:**
- Orchestrator Agent — controls all agents, plans execution
- Project Analysis Agent — detects language, framework, builds dependency intelligence
- Test Strategy Agent — risk-based test planning with AI
- Test Case Generator Agent — positive/negative/boundary/edge/exploratory cases

**Tier 2 — Execution:**
- Automation Generator Agent — Playwright and API test script generation
- Browser Execution Agent — Playwright browser testing with screenshots/video
- API Validation Agent — REST endpoint validation, auth boundary testing

**Tier 3 — Quality:**
- Security Testing Agent — SQLi, XSS, secrets, dependency CVEs, headers (CWE/OWASP references)
- Performance Agent — API latency percentiles, Core Web Vitals, grading
- Database Validation Agent — migrations, N+1 queries, indexes, constraints

**Tier 4 — Intelligence:**
- Bug Analysis Agent — root cause analysis, downstream effect detection, severity + confidence (ADR-008)
- Memory & Learning Agent — regression detection, failure trends (ADR-006 read-only exception)
- Report Agent — Markdown/JSON/HTML reports, GitHub PR comments, Slack notifications
- Feature Discovery Agent — AI-enriched business feature understanding
- Requirement Intelligence Agent — auto-generated business requirements

### Added — Application Dependency Intelligence (ADR-007)
- Feature Graph — business feature dependency discovery
- Code Dependency Graph — Python AST import analysis
- API Dependency Graph — FastAPI/Flask/Django/Express route detection
- Database Dependency Graph — SQLAlchemy/Django ORM model analysis
- UI Navigation Graph — React/Next.js/Vue/HTML route discovery

### Added — Release Intelligence Engine (ADR-010)
- Merge safety recommendation with reasoning and confidence
- Release risk assessment: Safe/Low/Medium/High/Critical
- Fix priority ordering
- Human Review Gate — AIQE never decides autonomously (ADR-009)
- Blocking vs non-blocking issue classification
- Regression detection integration

### Added — CLI (aiqe command)
- `aiqe scan .` — full project quality scan
- `aiqe scan . --dry-run` — preview without execution
- `aiqe status` — check workflow status
- `aiqe report <id>` — generate quality reports
- `aiqe plugins list/info/validate/capabilities`
- `aiqe gateway status/test/providers`
- `aiqe config show/validate/generate-key`
- `aiqe serve` — start REST API server

### Added — FastAPI REST API
- POST/GET/DELETE /api/v1/workflows
- GET /api/v1/workflows/{id}/bugs
- GET /api/v1/workflows/{id}/audit
- POST /api/v1/workflows/{id}/report
- GET/POST /api/v1/plugins (list, validate, capabilities)
- GET /api/v1/gateway/status, POST /api/v1/gateway/test
- POST /api/v1/webhooks/github (HMAC-SHA256 verified)
- GET /health, GET /ready (Kubernetes probes)
- CorrelationID, RequestLogging, SecurityHeaders middleware
- Full OpenAPI schema at /docs

### Added — GitHub Action
- Composite action (action.yml) with 14 inputs, 8 outputs
- GitHub event parser (reads GitHub Actions event.json)
- PR comment builder (updates existing, never creates spam)
- HMAC-SHA256 webhook signature verification
- Configurable fail-on-severity (Critical/High/Medium/Low/never)
- Example workflow for users to copy
- Full documentation in docs/github-action.md

### Added — Open Source Governance
- Professional README with architecture diagram
- CONTRIBUTING.md with branch strategy, commit format, PR process
- CODE_OF_CONDUCT.md (Contributor Covenant v2.1)
- SECURITY.md with vulnerability reporting process
- Issue templates: bug report, feature request, agent proposal
- Pull Request template with security and ADR checklists
- Dependabot configuration (Python + GitHub Actions)
- CI/CD workflow: quality, security scan, unit tests, integration tests

### Security
- Prompt injection defence: repository content sanitised before AI prompts
- Secret redaction: 20+ patterns filtered from all log output
- Plugin sandboxing: capability-based least-privilege (ADR-003)
- No auto-modification of production code (ADR-009)
- Audit trail: every agent execution, AI call, and tool invocation logged (ADR-012)
- Gitleaks + detect-secrets in pre-commit hooks
- Bandit security linter in CI

---

## [0.1.0] — Planned First Release

Pre-alpha implementation complete. First stable release will follow:
- Successful end-to-end scan of a real FastAPI project
- Complete test suite passing at ≥80% coverage
- Community feedback integration
- Documentation site deployment

---

*AIQE — AI Quality Engineering Operating System*
*Apache License 2.0*
