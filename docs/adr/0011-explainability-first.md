# ADR-0011: Explainability First

**Status:** Accepted

---

## Decision

Every AI decision made by AIQE must be explainable.
AIQE must never provide conclusions without evidence.

Every recommendation or conclusion includes:
- **Reasoning** — the logical steps AIQE followed to reach this conclusion
- **Supporting Evidence** — test results, logs, traces, screenshots, code references
- **Related Files** — which source files are involved
- **Related Features** — which business features are affected
- **Dependency Chain** — how this failure propagates through the system
- **Confidence Score** — how certain AIQE is (0–100%)
- **Suggested Next Action** — what the engineer should do first

Explainability is a core architectural principle. It takes priority over
black-box AI decisions, even when a black-box decision would be faster or
require fewer tokens.

---

## Why

QA engineers and developers adopt AI tools only when they can verify the
AI's reasoning. A "Critical: Authentication Bypass" label with no evidence
will be ignored or treated with suspicion. The same conclusion with
supporting HTTP logs, the specific code path involved, the dependency
chain showing downstream impact, and a 94% confidence score will be acted on.

Explainability also enables enterprise adoption. Compliance teams and
security engineers need to audit AI decisions. "The AI said so" is not
auditable. "The AI reached this conclusion because of these three log
entries, this code path, and this dependency relationship" is auditable.

Explainability is also AIQE's primary defense against prompt injection and
hallucination — if AIQE must always cite evidence, it cannot fabricate a
conclusion that has no evidence trail.

---

## Alternatives Considered

**Black-box AI verdicts for speed.**
Rejected. Speed of output is worthless if the output is not trusted.
Engineers who do not understand why AIQE flagged something as Critical
will either ignore it (missing real bugs) or escalate every flag (alert
fatigue). Explainability is what makes AIQE's output actionable.
