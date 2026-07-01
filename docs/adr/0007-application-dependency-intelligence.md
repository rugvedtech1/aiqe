# ADR-0007: Application Dependency Intelligence

**Status:** Accepted

---

## Decision

AIQE builds an Application Dependency Intelligence Model before executing
any tests. This model consists of five dependency graphs:

- **Feature Graph** — business features and their relationships
- **Code Dependency Graph** — modules, classes, and functions and their import relationships
- **API Dependency Graph** — API endpoints and their consumers/dependencies
- **Database Dependency Graph** — tables, views, migrations, and their relationships
- **UI Navigation Graph** — screens, routes, and navigation flows

These five graphs together form the Application Dependency Intelligence Model.

This model is used by:
- Test Strategy Agent — to determine test scope and risk
- Test Case Generator — to generate targeted test cases per feature/component
- Browser Execution Agent — to navigate UI flows correctly
- Bug Analysis Agent — to trace failures through dependency chains
- Release Intelligence Engine — to assess release risk

The model continuously improves during execution as new information is
discovered (e.g. a previously unknown API dependency surfaces during browser
execution).

---

## Why

Testing without understanding dependencies leads to:
- Redundant tests (testing the same path multiple times unknowingly)
- Missing tests (unaware that feature A depends on feature B)
- Cascading false positives (one root failure reported as many failures)
- Inability to answer "what is the release risk of this PR?"

With the dependency model, AIQE can isolate a root failure, understand
which downstream tests failed only because of that root failure (not
independent failures), and report them accurately.

---

## Alternatives Considered

**Single flat feature list without dependency mapping.**
Rejected. Without dependency relationships, AIQE cannot perform partial
failure isolation (stop only the affected dependency chain, not the whole
workflow), cannot group downstream failures under root causes, and cannot
accurately assess release risk.
