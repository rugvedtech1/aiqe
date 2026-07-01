# ADR-0003: Plugin Security — Capability-Based Permission Model (Principle of Least Privilege)

**Status:** Accepted

---

## Decision

Every plugin must declare a manifest describing the exact capabilities it
requires before it can be loaded. AIQE never grants full system access to
plugins by default. Every plugin receives only the minimum permissions
required to perform its job.

### Capability Groups

**Filesystem**
- Read Project Files
- Read Configuration Files
- Read Logs
- Read Temporary Files
- Write Project Files
- Write Temporary Files
- Delete Temporary Files
- Delete Project Files (Restricted — requires explicit user approval)

**Browser**
- Navigate
- Click
- Fill Forms
- Upload Files
- Download Files
- Capture Screenshots
- Record Videos
- Execute JavaScript

**Git**
- Read Repository
- Clone Repository
- Create Branch
- Commit Changes
- Create Pull Request
- Comment on Pull Request

**Network**
- HTTP Requests
- HTTPS Requests
- GitHub API
- GitLab API
- Jira API
- Slack API
- Internal Company APIs

**Secrets**
- Read OpenAI API Key
- Read Gemini API Key
- Read Database Credentials
- Read GitHub Token

**System**
- Execute Shell Commands
- Start Docker Containers
- Access Environment Variables
- Spawn Processes

**Database**
- Read Data
- Insert Data
- Update Data
- Delete Data
- Run Migrations

### Plugin Examples

Playwright Plugin:
- Allowed: Browser Navigation, Browser Screenshots, Browser Videos, Read Project Files
- Denied: Read API Keys, Delete Files, Execute Shell Commands

GitHub Plugin:
- Allowed: Read Repository, Comment on Pull Requests
- Denied: Database Access, Read Secrets, Delete Local Files

Slack Plugin:
- Allowed: Slack API
- Denied: Browser Access, File Deletion, Database Access

### Plugin Loader Responsibilities

Before loading any plugin:
1. Read the plugin manifest.
2. Validate requested capabilities against the known capability registry.
3. Reject unknown or dangerous capabilities.
4. Display requested capabilities to the user (optional in Local Mode, configurable in Enterprise Mode).
5. Load the plugin only with the approved capabilities, injecting only the permitted interfaces.

---

## Why

Plugins are one of the highest-risk attack surfaces in AIQE. They can
interact with browsers, APIs, databases, generated code, and user projects.
A compromised or malicious plugin with unrestricted access could exfiltrate
secrets, modify project files, or execute arbitrary shell commands.

Designing the capability model from day one means:
- The Plugin interface is shaped correctly from the start.
- Plugin authors know what permissions they need to declare.
- No breaking changes are needed when tightening security later.
- Enterprise adoption is possible because security auditors can review
  plugin manifests before approval.

---

## Implementation

**Version 1:** Enforce permissions in-process using Python wrappers and
capability checks. Restrict filesystem, network, secrets, browser, and
process access through controlled interfaces injected by the Plugin Loader.

**Enterprise Version:** Add OS-level sandboxing using containers or similar
isolation technologies. Support organization-level permission policies and
plugin approval workflows.

---

## Alternatives Considered

**Trust all plugins by default, add permissions later.**
Rejected. Retrofitting security after plugins already depend on unrestricted
access requires breaking changes across the entire plugin ecosystem and
violates AIQE's Security First architecture principle. This would also make
enterprise adoption impossible — security teams cannot approve plugins without
a declared permission model.
