"""
AIQE Agent Input and Output Type Contracts.

Every agent in AIQE has a strictly typed input and output.
Agents never pass raw dicts to each other — they pass typed
dataclasses defined here.

Why typed contracts?
    With 15 agents passing data to each other, untyped dicts
    become unmaintainable fast. A typo in a key name silently
    produces None instead of failing loudly. Typed dataclasses
    fail at construction time with a clear error, not at runtime
    when an agent tries to use a missing field.

    Typed contracts also serve as living documentation — any
    engineer can read AgentOutput and know exactly what every
    agent is expected to produce.

Design rules:
    - All input/output types are frozen dataclasses (immutable).
    - All fields have defaults so partial construction is possible
      during testing.
    - Sensitive fields (API keys, credentials) must never appear
      in agent inputs or outputs — those go through the AI Gateway.
    - Every output includes: success flag, error, duration,
      confidence score, and an evidence list (ADR-011).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


# ==================================================
# SEVERITY AND CONFIDENCE
# Defined here so all agents use identical types.
# See ADR-008.
# ==================================================


class BugSeverity(str, Enum):
    """Bug severity levels. See ADR-008."""
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFORMATIONAL = "Informational"


class ReleaseRisk(str, Enum):
    """
    Overall release risk level produced by the Release
    Intelligence Engine. See ADR-010.
    """
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    SAFE = "Safe"


# ==================================================
# EVIDENCE
# Every AI conclusion must carry evidence. ADR-011.
# ==================================================


@dataclass(frozen=True)
class Evidence:
    """
    A single piece of evidence supporting an AI conclusion.

    Every recommendation, bug report, and release assessment
    must include at least one Evidence item. This is the
    core of ADR-011 (Explainability First).

    Attributes:
        kind: What type of evidence this is.
              Options: log, screenshot, http_response, code_snippet,
              test_output, stack_trace, network_trace, db_query_result
        content: The actual evidence content (truncated if necessary).
        source: Where this evidence came from (file path, URL, agent name).
        relevance: Why this evidence supports the conclusion (one sentence).
    """
    kind: str
    content: str
    source: str
    relevance: str = ""


# ==================================================
# BASE AGENT INPUT
# ==================================================


@dataclass(frozen=True)
class AgentInput:
    """
    Base input type for all AIQE agents.

    Every agent receives at minimum the workflow_id and the
    project path being analysed. Agent-specific inputs are
    defined in subclasses.

    Attributes:
        workflow_id: The ID of the current WorkflowContext.
                     Used for logging and audit trail correlation.
        project_path: Absolute path to the project being analysed.
        dry_run: If True, the agent should describe what it would
                 do without actually doing it. Used for testing
                 and previewing agent behaviour.
        extra: Escape hatch for agent-specific config that does
               not yet have a typed field. Avoid using this in
               production code — add a typed field instead.
    """
    workflow_id: str = ""
    project_path: str = ""
    dry_run: bool = False
    extra: dict[str, Any] = field(default_factory=dict)


# ==================================================
# BASE AGENT OUTPUT
# ==================================================


@dataclass
class AgentOutput:
    """
    Base output type for all AIQE agents.

    Every agent returns at minimum: success/failure status,
    duration, confidence, reasoning, and evidence. Agent-specific
    outputs are defined in subclasses.

    This structure directly implements ADR-011 (Explainability):
    - reasoning: why the agent reached its conclusion
    - evidence: what data supports the conclusion
    - confidence: how certain the agent is (0.0 - 1.0)
    - suggested_next_action: what the engineer should do next

    Attributes:
        success: Whether the agent completed without errors.
        error: Error message if success is False.
        duration_seconds: How long the agent took to run.
        ai_tokens_used: Total tokens consumed by AI calls.
        confidence: Agent's confidence in its output (0.0-1.0).
        reasoning: Step-by-step explanation of how the agent
                   reached its conclusions (ADR-011).
        evidence: List of Evidence items supporting the output.
        suggested_next_action: What the engineer should do with
                               this output (ADR-011).
        warnings: Non-fatal issues the agent noticed.
        metadata: Additional structured data specific to the agent.
    """
    success: bool = True
    error: str | None = None
    duration_seconds: float = 0.0
    ai_tokens_used: int = 0
    confidence: float = 1.0
    reasoning: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    suggested_next_action: str = ""
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_evidence(
        self,
        kind: str,
        content: str,
        source: str,
        relevance: str = "",
    ) -> None:
        """
        Add a piece of evidence to this output.

        Convenience method so agent code doesn't need to
        import and construct Evidence directly.

        Args:
            kind: Evidence type (log, screenshot, code_snippet, etc.)
            content: The evidence content.
            source: Where this came from.
            relevance: Why this evidence supports the conclusion.
        """
        self.evidence.append(Evidence(
            kind=kind,
            content=content,
            source=source,
            relevance=relevance,
        ))

    def add_warning(self, warning: str) -> None:
        """Add a non-fatal warning to this output."""
        self.warnings.append(warning)

    def to_dict(self) -> dict[str, Any]:
        """Serialize this output for persistence and reporting."""
        return {
            "success": self.success,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
            "ai_tokens_used": self.ai_tokens_used,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "evidence": [
                {
                    "kind": e.kind,
                    "content": e.content,
                    "source": e.source,
                    "relevance": e.relevance,
                }
                for e in self.evidence
            ],
            "suggested_next_action": self.suggested_next_action,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


# ==================================================
# AGENT-SPECIFIC INPUT TYPES
# One per agent. Defined here so they are all in one place
# and agents import from aiqe.agents.types.
# ==================================================


@dataclass(frozen=True)
class ProjectAnalysisInput(AgentInput):
    """
    Input for the Project Analysis Agent.

    Attributes:
        include_hidden_files: Whether to scan hidden directories.
        max_file_size_kb: Skip files larger than this (in KB).
        scan_depth: Maximum directory depth to scan.
    """
    include_hidden_files: bool = False
    max_file_size_kb: int = 500
    scan_depth: int = 10


@dataclass(frozen=True)
class TestStrategyInput(AgentInput):
    """
    Input for the Test Strategy Agent.

    Attributes:
        project_analysis: Output from the Project Analysis Agent.
        changed_files: List of files changed in this PR/branch.
        risk_threshold: Minimum risk score to include in strategy.
    """
    project_analysis: dict[str, Any] = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)
    risk_threshold: float = 0.3


@dataclass(frozen=True)
class TestCaseGeneratorInput(AgentInput):
    """
    Input for the Test Case Generator Agent.

    Attributes:
        test_strategy: Output from the Test Strategy Agent.
        project_analysis: Output from the Project Analysis Agent.
        max_cases_per_feature: Cap test case generation per feature.
        include_negative_cases: Generate negative test cases.
        include_boundary_cases: Generate boundary value test cases.
        include_exploratory_cases: Generate exploratory test cases.
    """
    test_strategy: dict[str, Any] = field(default_factory=dict)
    project_analysis: dict[str, Any] = field(default_factory=dict)
    max_cases_per_feature: int = 20
    include_negative_cases: bool = True
    include_boundary_cases: bool = True
    include_exploratory_cases: bool = True


@dataclass(frozen=True)
class BrowserExecutionInput(AgentInput):
    """
    Input for the Browser Execution Agent.

    Attributes:
        test_cases: Generated test cases to execute in the browser.
        base_url: The base URL of the application under test.
        browser_type: Which browser to use (chromium/firefox/webkit).
        capture_screenshots: Whether to capture screenshots on failure.
        capture_video: Whether to record video of test execution.
        headless: Run browser in headless mode.
        timeout_seconds: Maximum time per test case.
    """
    test_cases: list[dict[str, Any]] = field(default_factory=list)
    base_url: str = ""
    browser_type: str = "chromium"
    capture_screenshots: bool = True
    capture_video: bool = False
    headless: bool = True
    timeout_seconds: int = 30


@dataclass(frozen=True)
class APIValidationInput(AgentInput):
    """
    Input for the API Validation Agent.

    Attributes:
        api_spec: OpenAPI/GraphQL spec or discovered endpoints.
        base_url: Base URL for API calls.
        auth_config: Authentication configuration (no secrets —
                     agent retrieves these from the Gateway).
        validate_response_schemas: Validate all responses against spec.
        test_rate_limits: Test rate limiting behaviour.
    """
    api_spec: dict[str, Any] = field(default_factory=dict)
    base_url: str = ""
    auth_config: dict[str, str] = field(default_factory=dict)
    validate_response_schemas: bool = True
    test_rate_limits: bool = False


@dataclass(frozen=True)
class SecurityTestingInput(AgentInput):
    """
    Input for the Security Testing Agent.

    Attributes:
        project_analysis: Project analysis output.
        scan_sql_injection: Test for SQL injection vulnerabilities.
        scan_xss: Test for cross-site scripting vulnerabilities.
        scan_auth: Test authentication and authorisation flows.
        scan_secrets: Scan codebase for accidentally committed secrets.
        scan_dependencies: Check dependencies for known CVEs.
        scan_headers: Validate HTTP security headers.
    """
    project_analysis: dict[str, Any] = field(default_factory=dict)
    scan_sql_injection: bool = True
    scan_xss: bool = True
    scan_auth: bool = True
    scan_secrets: bool = True
    scan_dependencies: bool = True
    scan_headers: bool = True


@dataclass(frozen=True)
class BugAnalysisInput(AgentInput):
    """
    Input for the Bug Analysis Agent.

    Attributes:
        failed_tests: List of failed test results.
        browser_logs: Console and network logs from browser execution.
        screenshots: Paths to failure screenshots.
        dependency_graph: The application dependency graph.
        workflow_audit_log: The workflow's audit trail for context.
    """
    failed_tests: list[dict[str, Any]] = field(default_factory=list)
    browser_logs: list[str] = field(default_factory=list)
    screenshots: list[str] = field(default_factory=list)
    dependency_graph: dict[str, Any] = field(default_factory=dict)
    workflow_audit_log: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ReportInput(AgentInput):
    """
    Input for the Report Agent.

    Attributes:
        workflow_summary: Complete workflow execution summary.
        bugs: All bugs found during the workflow.
        release_recommendation: Release Intelligence Engine output.
        output_formats: Which report formats to generate.
        notify_slack: Whether to send Slack notification.
        notify_github_pr: Whether to comment on the PR.
    """
    workflow_summary: dict[str, Any] = field(default_factory=dict)
    bugs: list[dict[str, Any]] = field(default_factory=list)
    release_recommendation: dict[str, Any] = field(default_factory=dict)
    output_formats: list[str] = field(default_factory=lambda: ["html", "markdown"])
    notify_slack: bool = False
    notify_github_pr: bool = False


# ==================================================
# AGENT-SPECIFIC OUTPUT TYPES
# ==================================================


@dataclass
class ProjectAnalysisOutput(AgentOutput):
    """
    Output from the Project Analysis Agent.

    This is the foundational output that most other agents
    depend on. It tells AIQE what kind of project it is looking
    at so agents can make informed decisions.

    Attributes:
        language: Primary programming language detected.
        framework: Primary framework detected (e.g. fastapi, django).
        test_framework: Testing framework in use (e.g. pytest, jest).
        package_manager: Package manager (e.g. pip, npm, cargo).
        dependencies: List of detected dependencies.
        routes: Detected API routes / URL patterns.
        auth_method: Authentication method detected (jwt, session, oauth).
        database: Database type detected (postgres, sqlite, mongodb).
        has_docker: Whether a Dockerfile or docker-compose exists.
        has_ci: Whether CI configuration exists.
        entry_points: Main entry point files.
        test_files: Detected test files.
        config_files: Detected configuration files.
        source_files_count: Total number of source files scanned.
        lines_of_code: Approximate lines of code.
    """
    language: str = ""
    framework: str = ""
    test_framework: str = ""
    package_manager: str = ""
    dependencies: list[str] = field(default_factory=list)
    routes: list[dict[str, str]] = field(default_factory=list)
    auth_method: str = ""
    database: str = ""
    has_docker: bool = False
    has_ci: bool = False
    entry_points: list[str] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    config_files: list[str] = field(default_factory=list)
    source_files_count: int = 0
    lines_of_code: int = 0


@dataclass
class TestStrategyOutput(AgentOutput):
    """
    Output from the Test Strategy Agent.

    Attributes:
        test_plan: Ordered list of test areas with priority and risk.
        skipped_areas: Areas excluded from testing and why.
        estimated_test_count: How many tests will be generated.
        risk_assessment: Overall risk rating for this changeset.
        changed_features: Which business features are affected.
        regression_risk: Whether this change risks regressions.
    """
    test_plan: list[dict[str, Any]] = field(default_factory=list)
    skipped_areas: list[dict[str, str]] = field(default_factory=list)
    estimated_test_count: int = 0
    risk_assessment: str = ""
    changed_features: list[str] = field(default_factory=list)
    regression_risk: bool = False


@dataclass
class BugReport:
    """
    A single bug found during workflow execution.

    Implements ADR-008 (severity + confidence) and
    ADR-011 (full explainability).

    Attributes:
        id: Unique bug identifier.
        title: One-line description of the bug.
        severity: Bug severity level (ADR-008).
        confidence: AI confidence in this bug (0.0-1.0, ADR-008).
        root_cause: Detailed root cause analysis.
        evidence: Supporting evidence list (ADR-011).
        affected_feature: Which business feature is impacted.
        affected_files: Which source files are involved.
        dependency_chain: How this failure propagates (ADR-011).
        suggested_fix: What the engineer should do to fix it.
        fix_confidence: Confidence in the suggested fix (0.0-1.0).
        is_downstream: Whether this is a downstream effect.
        root_bug_id: If downstream, which bug caused this.
        related_tests: Test IDs that revealed this bug.
    """
    id: str = ""
    title: str = ""
    severity: BugSeverity = BugSeverity.MEDIUM
    confidence: float = 0.5
    root_cause: str = ""
    evidence: list[Evidence] = field(default_factory=list)
    affected_feature: str = ""
    affected_files: list[str] = field(default_factory=list)
    dependency_chain: list[str] = field(default_factory=list)
    suggested_fix: str = ""
    fix_confidence: float = 0.5
    is_downstream: bool = False
    root_bug_id: str | None = None
    related_tests: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity.value,
            "confidence": self.confidence,
            "root_cause": self.root_cause,
            "evidence": [
                {"kind": e.kind, "content": e.content,
                 "source": e.source, "relevance": e.relevance}
                for e in self.evidence
            ],
            "affected_feature": self.affected_feature,
            "affected_files": self.affected_files,
            "dependency_chain": self.dependency_chain,
            "suggested_fix": self.suggested_fix,
            "fix_confidence": self.fix_confidence,
            "is_downstream": self.is_downstream,
            "root_bug_id": self.root_bug_id,
            "related_tests": self.related_tests,
        }


@dataclass
class ReleaseIntelligenceOutput(AgentOutput):
    """
    Output from the Release Intelligence Engine.

    This is the final output of every AIQE workflow.
    It answers the human review gate questions. See ADR-010.

    Attributes:
        is_safe_to_merge: AIQE's recommendation (not a decision).
        release_risk: Overall risk level.
        risk_reasoning: Why AIQE assigned this risk level.
        what_changed: Summary of what changed in this PR.
        affected_components: Components affected by the changes.
        tests_executed: Count of tests that ran.
        tests_skipped: Count of tests that were skipped.
        skip_reasons: Why tests were skipped.
        critical_bugs: All Critical severity bugs found.
        high_bugs: All High severity bugs found.
        total_bugs_by_severity: Count per severity level.
        fix_priority: Ordered list of what to fix first and why.
        human_review_notes: Specific things engineers should look at.
    """
    is_safe_to_merge: bool = False
    release_risk: ReleaseRisk = ReleaseRisk.HIGH
    risk_reasoning: str = ""
    what_changed: str = ""
    affected_components: list[str] = field(default_factory=list)
    tests_executed: int = 0
    tests_skipped: int = 0
    skip_reasons: list[str] = field(default_factory=list)
    critical_bugs: list[BugReport] = field(default_factory=list)
    high_bugs: list[BugReport] = field(default_factory=list)
    total_bugs_by_severity: dict[str, int] = field(default_factory=dict)
    fix_priority: list[dict[str, str]] = field(default_factory=list)
    human_review_notes: list[str] = field(default_factory=list)
