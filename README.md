<div align="center">

# AIQE
### AI Quality Engineering Operating System

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://python.org)
[![Status](https://img.shields.io/badge/status-pre--alpha-orange.svg)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Code of Conduct](https://img.shields.io/badge/code%20of%20conduct-enforced-brightgreen.svg)](CODE_OF_CONDUCT.md)

**AIQE understands software. It understands requirements. It understands business features.**
**It decides what should be tested, generates tests, executes them, analyzes failures,**
**finds root causes, and continuously improves software quality.**

[Documentation](#documentation) •
[Quick Start](#quick-start) •
[Architecture](#architecture) •
[Contributing](CONTRIBUTING.md) •
[Roadmap](#roadmap)

</div>

---

## What is AIQE?

AIQE is an open-source **AI Quality Engineering Operating System**.

Most QA automation tools execute tests you write.
AIQE is a **Release Intelligence Engine** — it tells your engineering team:

- What changed in this Pull Request?
- Which features and components are affected?
- Which tests should run, and which can safely be skipped?
- What is the release risk?
- What is the root cause of each failure?
- Is this Pull Request safe to merge?

Every conclusion comes with **reasoning, evidence, related files, a dependency
chain, and a confidence score**. AIQE never gives you a black-box answer.

> AIQE does **not** replace QA engineers.
> It removes repetitive test-design and triage work so QA engineers can focus
> on business logic, exploratory testing, and the release decisions that
> actually need human judgment.

---

## Core Principles

| Principle | What it means |
|---|---|
| **Deterministic before AI** | Framework detection, file parsing, browser execution, and HTTP validation are plain software. AI is reserved for root-cause analysis, requirement understanding, test strategy, and explanation. |
| **Explainability first** | Every AI conclusion ships with reasoning, evidence, related files/features, dependency chain, and a confidence score. No black boxes. |
| **Human review gate** | AIQE never modifies production code and never merges anything automatically. Every workflow ends with a human decision. |
| **Workflow isolation** | Every PR, branch, or run gets its own fully isolated execution context. Workflows never interfere with each other. |
| **Least privilege plugins** | Plugins declare a capability manifest. They run with the minimum permissions required — nothing more. |
| **Auditability** | Every agent execution, AI call, tool call, browser action, and retry attempt is logged. Any workflow can be fully reconstructed. |

---

## Deployment Modes

| Mode | Description | Command |
|---|---|---|
| **Local CLI** | Run against a local project, zero infrastructure required | `aiqe scan .` |
| **GitHub Action** | Automatic Pull Request testing in CI | See [docs/github-action.md](docs/github-action.md) |
| **Enterprise** | Docker / Kubernetes, private infrastructure, private AI models | See [docs/enterprise.md](docs/enterprise.md) |

---

## Architecture

AIQE is built on **Clean Architecture** with a custom **Workflow Engine** and
**Agent Registry** (the product's competitive advantage), running on proven
async infrastructure underneath.
┌─────────────────────────────────────────────┐
│               CLI / FastAPI / GitHub Action  │
├─────────────────────────────────────────────┤
│              Orchestrator Agent              │
├──────────────┬──────────────────────────────┤
│  Workflow    │  Agent Registry              │
│  Engine      │  (15 Agents)                │
├──────────────┴──────────────────────────────┤
│         AI Gateway (multi-provider)          │
├─────────────────────────────────────────────┤
│   Plugin System │ Shared Memory │ Event Bus  │
├─────────────────────────────────────────────┤
│     Persistence Layer (SQLite / Postgres)    │
└─────────────────────────────────────────────┘

### The 15 Agents

AIQE ships 15 specialized agents built and deployed incrementally:

**Tier 1 — Core**
- Orchestrator Agent — controls all agents, plans execution, coordinates workflows
- Project Analysis Agent — detects language, framework, dependencies, routes, APIs
- Test Strategy Agent — risk analysis, coverage planning, regression priority
- Test Case Generator — positive, negative, boundary, edge, exploratory cases

**Tier 2 — Execution**
- Automation Generator Agent — generates Playwright, API, and database tests
- Browser Execution Agent — runs browsers, captures video/screenshots/logs
- API Validation Agent — REST, GraphQL, authentication, rate limits

**Tier 3 — Quality**
- Security Testing Agent — SQLi, XSS, auth, secrets detection, dependency scan
- Performance Agent — CPU, memory, API latency, Core Web Vitals
- Database Validation Agent — inserts, updates, migrations, constraints

**Tier 4 — Intelligence**
- Bug Analysis Agent — root cause, severity, confidence score, suggested fix
- Memory & Learning Agent — failure history, regression memory, improvement
- Report Agent — HTML, PDF, Markdown, GitHub comments, Slack notifications
- Feature Discovery Agent — business feature understanding, feature graph
- Requirement Intelligence Agent — auto-generated requirements, business logic

---

## Quick Start

> AIQE is in pre-alpha. The CLI is not yet released.
> Star and Watch this repo to be notified when it is ready.

```bash
# Coming soon
pip install aiqe
aiqe scan .
```

---

## AI Provider Support

AIQE supports multiple AI providers through its AI Gateway.
You bring your own API keys — AIQE never creates accounts on your behalf.

| Provider | Status |
|---|---|
| OpenAI | Planned |
| Anthropic | Planned |
| Google Gemini | Planned |
| Groq | Planned |
| OpenRouter | Planned |
| Azure OpenAI | Planned |
| Ollama (local) | Planned |

---

## Documentation

| Document | Description |
|---|---|
| [Architecture Decision Records](docs/adr/README.md) | Every major architectural decision with full reasoning |
| [Contributing Guide](CONTRIBUTING.md) | How to contribute to AIQE |
| [Security Policy](SECURITY.md) | How to report vulnerabilities responsibly |
| [Code of Conduct](CODE_OF_CONDUCT.md) | Community standards |

Full documentation site coming during development.

---

## Roadmap

| Phase | Description | Status |
|---|---|---|
| Phase 0 | ADRs and Architecture | ✅ Complete |
| Phase 1 | Repository and Governance | 🔄 In Progress |
| Phase 2 | Dev Environment and Core Infrastructure | ⏳ Planned |
| Phase 3 | Workflow Engine and Agent Framework | ⏳ Planned |
| Phase 4 | AI Gateway and Plugin System | ⏳ Planned |
| Phase 5 | CLI and FastAPI | ⏳ Planned |
| Phase 6 | Agents Tier 1 | ⏳ Planned |
| Phase 7 | Agents Tier 2 and 3 | ⏳ Planned |
| Phase 8 | Release Intelligence Engine | ⏳ Planned |

---

## Contributing

AIQE welcomes contributions from developers, QA engineers, AI researchers,
and DevOps engineers. Please read [CONTRIBUTING.md](CONTRIBUTING.md) before
opening a Pull Request.

---

## Security

If you discover a security vulnerability, please read
[SECURITY.md](SECURITY.md) and report it responsibly.
Do **not** open a public GitHub issue for security vulnerabilities.

---

## License

AIQE is licensed under the [Apache License 2.0](LICENSE).

Apache 2.0 was chosen over MIT because it includes an explicit patent grant,
which matters for enterprise adoption and protects contributors.

---

<div align="center">
Built with care by the AIQE open-source community.
</div>
