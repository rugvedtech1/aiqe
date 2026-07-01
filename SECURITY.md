# Security Policy

## Supported Versions

AIQE is currently in pre-alpha. Security fixes will be applied to the
latest development version only until a stable release is published,
at which point a supported versions table will be maintained here.

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**
Public disclosure before a fix is available puts all users at risk.

To report a vulnerability:

1. Go to the **Security** tab of this repository on GitHub.
2. Click **Report a vulnerability** (GitHub Private Security Advisory).
3. Describe the vulnerability in detail:
   - What is the issue?
   - What is the impact?
   - What component is affected?
   - Steps to reproduce.
   - Any suggested fix if you have one.

You will receive an acknowledgment within **48 hours**.
We will work with you to understand the issue and coordinate a fix and
responsible disclosure timeline.

---

## Security Architecture Principles

AIQE is built with security as a first-class concern at every layer.
Key principles:

- **Principle of Least Privilege** — plugins and agents receive only the
  minimum permissions required (see ADR-003).
- **No secrets in code or logs** — API keys, tokens, and credentials are
  never logged, never committed, and managed through controlled interfaces only.
- **Input validation on all external inputs** — CLI arguments, API payloads,
  plugin manifests, and repository content are all validated before processing.
- **No automatic production code modification** — AIQE never writes to or
  merges into production code automatically (see ADR-009).
- **Audit trail** — every agent execution, AI call, and tool invocation is
  logged for traceability (see ADR-012).
- **Prompt injection awareness** — content from scanned repositories is
  treated as untrusted input and never interpolated directly into AI prompts.
- **Supply chain security** — Dependabot is enabled. Dependencies are
  reviewed before merging.

---

## Vulnerability Disclosure Timeline

| Step | Timeline |
|---|---|
| Acknowledgment of report | Within 48 hours |
| Confirmation of vulnerability | Within 7 days |
| Fix developed and reviewed | Within 30 days (critical: faster) |
| Fix released | Coordinated with reporter |
| Public disclosure | After fix is available |

---

## Bug Bounty

There is no formal bug bounty program at this time.
We recognize responsible disclosure in our changelog and contributors list.
