# ADR-0012: Auditability and Traceability

**Status:** Accepted

---

## Decision

Every workflow must produce a complete, immutable audit trail.
Every significant action during a workflow execution is recorded.

**What is traced:**
- Agent Executions — which agent ran, when, with what inputs and outputs
- AI Model Used — provider, model version, temperature, and parameters
- Prompt Version — the exact prompt template version used
- Response — the AI response (with sensitive data redacted)
- Tool Calls — every tool invoked by every agent
- Test Executions — test ID, input, output, duration, result
- Browser Actions — navigation, clicks, form fills, screenshots, videos
- API Calls — endpoint, method, status, duration (credentials redacted)
- Generated Reports — report type, location, timestamp
- Errors — full error with stack trace and context
- Retry Attempts — what was retried, how many times, and the outcome
- Checkpoints — stage name, timestamp, state snapshot

The audit trail is:
- Written to the workflow's isolated execution context (see ADR-006)
- Queryable after the workflow completes
- Never modified after it is written (append-only)
- Exportable for compliance and debugging purposes

---

## Why

**Debugging:** When a workflow produces an unexpected result, engineers need
to reconstruct exactly what happened. "The browser agent clicked X and then
the API returned 403" is only recoverable from a full audit trail.

**AI Transparency:** Which AI model produced which recommendation, with which
prompt, is essential for understanding and improving AIQE's behavior over time.

**Enterprise Compliance:** Regulated industries (finance, healthcare, government)
require proof that automated systems behaved correctly. An audit trail is not
optional for enterprise adoption — it is a hard requirement.

**Regression Analysis:** The Memory & Learning Agent (ADR-004, Tier 4) uses
historical audit trails to detect regressions, understand failure patterns,
and improve test strategy recommendations over time.

---

## Alternatives Considered

**Logs only, no structured audit trail.**
Rejected. Unstructured logs are not queryable, not exportable for compliance,
and cannot be used by the Memory & Learning Agent for regression analysis.
Structured audit records are more work upfront and deliver significantly
more value.

**Single global audit log for all workflows.**
Rejected. Violates ADR-006 (Workflow Context Isolation). Each workflow's
audit trail must live in its own isolated context. The Memory & Learning
Agent reads historical audit trails in READ-ONLY mode — it never writes to
them or merges them.
