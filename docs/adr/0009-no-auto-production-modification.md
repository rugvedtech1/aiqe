# ADR-0009: No Automatic Production Code Modification

**Status:** Accepted

---

## Decision

AIQE must never automatically modify production code in any version.

**Version 1 output for every bug or failure:**
- Root Cause — what caused the failure
- Evidence — logs, screenshots, traces, test output supporting the conclusion
- Suggested Fix — what should be changed and why
- Confidence Score — how certain AIQE is about the suggested fix

**Future versions may optionally:**
- Generate a Pull Request containing the suggested fix for human review

**Even in future versions, AIQE must never:**
- Merge code automatically
- Bypass CI checks
- Merge without explicit developer approval
- Take any action that modifies main/production branches without human confirmation

Human approval is always required. This is a permanent architectural principle,
not a temporary limitation.

---

## Why

Automated code modification without human review introduces unacceptable risk:
- AI-generated fixes may resolve the symptom but introduce a new bug
- Auto-merge bypasses code review, a critical quality gate
- Enterprise environments have compliance requirements that mandate human approval
- Trust in AIQE's output is built incrementally — auto-modification before that
  trust is established would damage the project's credibility and adoption

AIQE's value is quality intelligence, not automated code writing. Engineers
who trust AIQE's diagnosis will apply the suggested fix. Engineers who don't
trust it yet should not have code applied automatically to their codebase.

---

## Alternatives Considered

**Auto-apply fixes for "safe" changes (e.g. typos, formatting).**
Rejected. Defining "safe" reliably is harder than it appears. A formatting
change in a config file can break behavior. The risk of even one unintended
auto-modification outweighs the convenience of automating trivial fixes.
The principle must be consistent to be trustworthy.
