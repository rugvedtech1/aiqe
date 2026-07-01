# ADR-0008: Bug Severity System with Confidence Scores

**Status:** Accepted

---

## Decision

Every issue discovered by AIQE includes both a Severity level and a
Confidence Score.

**Severity Levels:**
- Critical
- High
- Medium
- Low
- Informational

**Confidence Score:**
A percentage (0–100%) indicating how certain AIQE is about the classification.

Example:
Severity:   Critical
Confidence: 97%

**Notification strategy based on severity:**
- Critical: notify immediately (GitHub PR comment, Slack/Teams if configured)
- High / Medium / Low / Informational: include in final consolidated report

This avoids notification spam while ensuring critical issues are never missed.

**Confidence influences Release Intelligence:**
The Release Intelligence Engine uses confidence scores in its merge
recommendation. A Critical issue at 60% confidence produces a different
recommendation than a Critical issue at 99% confidence.

---

## Why

Severity without confidence is incomplete information. An engineer seeing
"Critical" needs to know whether AIQE is 95% sure or 55% sure before
deciding how urgently to act. Confidence also protects against notification
fatigue — a Critical at low confidence should trigger investigation, not
an immediate production halt.

The hybrid notification strategy prevents alert fatigue while ensuring that
genuine critical issues surface immediately, not only in an end-of-run report
that might be read hours later.

---

## Alternatives Considered

**Severity only, no confidence score.**
Rejected. Engineers would receive binary "Critical" labels with no indication
of AI certainty, leading to either over-reaction (treating every Critical as
definite) or under-reaction (discounting all AI verdicts). Confidence makes
AIQE's output actionable.
