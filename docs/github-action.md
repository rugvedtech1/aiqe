# AIQE GitHub Action

Automatically scan your Pull Requests for quality issues using AIQE.

## Quick Start

Add this to `.github/workflows/aiqe.yml` in your repository:

```yaml
name: AIQE Quality Scan
on:
  pull_request:
    branches: [main, develop]

jobs:
  quality:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: rugvedtech1/aiqe@v0.1.0
        with:
          openai-api-key: ${{ secrets.OPENAI_API_KEY }}
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `openai-api-key` | At least one AI key | `''` | OpenAI API key |
| `anthropic-api-key` | At least one AI key | `''` | Anthropic API key |
| `gemini-api-key` | At least one AI key | `''` | Google Gemini API key |
| `groq-api-key` | At least one AI key | `''` | Groq API key |
| `ai-provider` | No | `openai` | AI provider to use |
| `github-token` | No | `${{ github.token }}` | GitHub token for PR comments |
| `project-path` | No | `.` | Path to the project to scan |
| `fail-on-severity` | No | `High` | Severity level that fails the check |
| `post-pr-comment` | No | `true` | Post quality report as PR comment |
| `enable-security-testing` | No | `true` | Run security tests |
| `enable-performance-testing` | No | `false` | Run performance tests |
| `log-level` | No | `INFO` | Log verbosity |
| `report-format` | No | `markdown` | Report format (markdown, json) |

## Outputs

| Output | Description |
|--------|-------------|
| `workflow-id` | AIQE workflow ID for this scan |
| `status` | Scan status (completed, failed) |
| `bugs-found` | Total bugs found |
| `critical-bugs` | Critical severity bug count |
| `high-bugs` | High severity bug count |
| `release-risk` | Release risk (Safe, Low, Medium, High, Critical) |
| `report-path` | Path to the generated report artifact |
| `is-safe-to-merge` | Whether AIQE recommends merging (true/false) |

## Fail on Severity

The `fail-on-severity` input controls when the action fails the PR check:

| Value | Behaviour |
|-------|-----------|
| `Critical` | Only fail on Critical bugs |
| `High` | Fail on Critical or High bugs (default) |
| `Medium` | Fail on Critical, High, or Medium bugs |
| `Low` | Fail on any bug |
| `never` | Never fail the check (report only) |

## Secrets Setup

Add your AI provider API key to your repository:

1. Go to **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Add `OPENAI_API_KEY` (or your preferred provider key)

## PR Comment Example

AIQE posts a structured quality report as a PR comment:
✅ AIQE Recommendation: Safe to Review

Release Risk: Low

MetricValueTotal Bugs2🔴 Critical0🟠 High0🟡 Medium2...
🔐 Human Review Gate
AIQE provides recommendations. The final merge decision belongs to your team.

## Human Review Gate

AIQE always ends with a Human Review Gate. It provides:
- Root cause analysis
- Evidence
- Suggested fixes with confidence scores
- Release risk assessment

**AIQE never merges code automatically.**
The engineering team always makes the final decision.

## Artifacts

AIQE uploads the quality report as a workflow artifact named
`aiqe-quality-report`. Download it from the Actions run page.

## Supported Languages and Frameworks

| Language | Frameworks |
|----------|------------|
| Python | FastAPI, Django, Flask, Starlette |
| JavaScript | React, Next.js, Express, Vue |
| TypeScript | Angular, NestJS, Next.js |
| Ruby | Rails, Sinatra |
| Go | Standard library, Gin, Echo |
| Rust | Actix-web, Axum |

## Enterprise Mode

For enterprise deployments with private infrastructure:

```yaml
- uses: rugvedtech1/aiqe@v0.1.0
  with:
    ai-provider: ollama          # Use local Ollama instance
    enable-security-testing: 'true'
    enable-performance-testing: 'true'
```

See [docs/enterprise.md](enterprise.md) for full enterprise configuration.
