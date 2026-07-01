# ADR-0010: Release Intelligence Engine

**Status:** Accepted

---

## Decision

The final output of every AIQE workflow is not a test report. It is a
Release Intelligence Report produced by the Release Intelligence Engine.

The Release Intelligence Engine answers:
- What changed in this PR/branch?
- Which components and features are affected?
- Which tests were executed?
- Which tests were skipped, and why?
- What is the release risk? (Low / Medium / High / Critical)
- What is the root cause of each failure?
- Is this Pull Request safe to merge?
- What should engineers fix first, and in what order?

Every recommendation includes:
- Reasoning — why AIQE reached this conclusion
- Supporting evidence — test results, logs, traces, screenshots
- Confidence score — how certain AIQE is

Every workflow ends at a **Human Review Gate**. AIQE provides its
recommendation. The engineering team makes the final merge/release decision.
AIQE never decides this autonomously.

---

## Why

Test reports tell you what failed. Release Intelligence tells you what the
failures mean for the release decision. These are different questions that
require different outputs.

Engineering managers and QA leads who receive a raw test report still have
to answer "is this safe to merge?" themselves. The Release Intelligence
Engine answers that question directly, with evidence, so they can make a
faster and better-informed decision.

The Human Review Gate is non-negotiable. See ADR-009. AIQE is a quality
intelligence system, not an autonomous release system.

---

## Alternatives Considered

**Standard test report as final output.**
Rejected. A test report is an input to a release decision, not a release
decision support system. AIQE's competitive advantage is answering "is this
safe to merge?" with evidence — not producing another HTML test report that
an engineer must still interpret manually.
