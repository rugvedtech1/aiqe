# Contributing to AIQE

Thank you for your interest in contributing to AIQE.
This guide explains everything you need to know before opening a Pull Request.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
- [Development Setup](#development-setup)
- [Branch Strategy](#branch-strategy)
- [Commit Message Format](#commit-message-format)
- [Pull Request Process](#pull-request-process)
- [Architecture Decision Records](#architecture-decision-records)
- [Testing Requirements](#testing-requirements)
- [Documentation Requirements](#documentation-requirements)
- [Good First Issues](#good-first-issues)

---

## Code of Conduct

All contributors must follow our [Code of Conduct](CODE_OF_CONDUCT.md).
We enforce it.

---

## How to Contribute

There are many ways to contribute beyond writing code:

- Report bugs using the bug report issue template
- Suggest features using the feature request issue template
- Improve documentation
- Write tests
- Review Pull Requests
- Propose a new agent using the agent proposal issue template
- Participate in GitHub Discussions

---

## Development Setup

Full setup instructions will be documented in [docs/dev-setup.md](docs/dev-setup.md)
once the development environment step is complete (Step 3 of the build plan).

Requirements:
- Python 3.12+
- Git

---

## Branch Strategy
main          ← stable releases only, protected, never commit directly
develop       ← integration branch, all features merge here first
feature/*     ← new features (branch from develop)
fix/*         ← bug fixes (branch from develop)
docs/*        ← documentation only changes
chore/*       ← tooling, dependencies, CI changes
adr/*         ← architecture decision record additions or updates

**Always branch from `develop`, never from `main`.**

Example:
```bash
git checkout develop
git pull origin develop
git checkout -b feature/project-analysis-agent
```

---

## Commit Message Format

AIQE uses [Conventional Commits](https://www.conventionalcommits.org/).
<type>(<scope>): <short description>
[optional body]
[optional footer]

Types:
- `feat` — new feature
- `fix` — bug fix
- `docs` — documentation only
- `test` — adding or updating tests
- `chore` — tooling, dependencies, CI
- `refactor` — code change that is neither a fix nor a feature
- `perf` — performance improvement
- `security` — security improvement
- `adr` — architecture decision record

Examples:
feat(agents): add Project Analysis Agent framework detection
fix(gateway): handle OpenAI rate limit retry correctly
docs(adr): add ADR-013 for caching strategy
test(workflow): add integration tests for checkpoint recovery
security(plugins): enforce capability manifest validation on load

---

## Pull Request Process

1. Branch from `develop`.
2. Write code, tests, and documentation together — not after.
3. Ensure all tests pass locally before opening a PR.
4. Fill in the Pull Request template completely.
5. Link any related issues.
6. If your change involves an architectural decision, reference the relevant ADR or propose a new one.
7. Request review from at least one maintainer.
8. Address all review comments before merging.
9. PRs are merged using **squash and merge** only — keep history clean.

---

## Architecture Decision Records

If your contribution involves a significant architectural decision
(new infrastructure, changing a core interface, adding a new agent,
changing the persistence layer, etc.), you must either:

- Reference an existing ADR that covers your decision, or
- Propose a new ADR by opening an issue using the ADR proposal process
  before writing the implementation.

See [docs/adr/README.md](docs/adr/README.md) for the full list of current ADRs.

---

## Testing Requirements

Every contribution must include:

- Unit tests for all new logic
- Integration tests for any cross-module interactions
- Security tests for any new input handling, plugin interaction, or API surface
- No reduction in overall code coverage

Testing setup and commands will be documented in [docs/dev-setup.md](docs/dev-setup.md).

---

## Documentation Requirements

Every feature must include documentation. This is not optional.

- Public functions and classes must have docstrings.
- New modules need a module-level docstring explaining their purpose.
- User-facing features need documentation in `docs/`.
- Architecture changes need an ADR update or new ADR.

---

## Good First Issues

Look for issues labeled `good first issue` in the GitHub Issues tab.
These are specifically selected for contributors who are new to the codebase.

If you are unsure where to start, open a Discussion and ask — the maintainers
will help you find the right issue for your skills and interests.

---

## Questions?

Open a [GitHub Discussion](../../discussions) — do not use Issues for questions.
Issues are for bugs and actionable feature requests only.
