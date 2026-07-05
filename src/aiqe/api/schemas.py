"""
AIQE FastAPI Request and Response Schemas.

All HTTP request bodies and response bodies are typed
Pydantic models defined here.

Why separate schemas from domain types?
    Domain types (WorkflowContext, BugReport, etc.) are optimised
    for internal use — they carry asyncio locks, mutable state,
    and internal methods. They are not suitable for JSON serialisation.

    API schemas are optimised for HTTP — they are flat, JSON-safe,
    and designed for external consumers (CI systems, dashboards,
    third-party integrations). They include documentation strings
    that appear in the OpenAPI schema.

    Separation prevents coupling: changing the internal domain model
    does not break the public API contract, and vice versa.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ==================================================
# SHARED BASE MODELS
# ==================================================

class APIResponse(BaseModel):
    """Standard API response envelope."""
    success: bool = True
    message: str = ""
    data: Any = None


class ErrorResponse(BaseModel):
    """Standard error response."""
    success: bool = False
    error: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class PaginatedResponse(BaseModel):
    """Paginated list response."""
    items: list[Any]
    total: int
    page: int
    page_size: int
    has_next: bool


# ==================================================
# WORKFLOW SCHEMAS
# ==================================================

class WorkflowTrigger(str, Enum):
    """What triggered a workflow."""
    PR = "pr"
    BRANCH = "branch"
    MANUAL = "manual"
    SCHEDULED = "scheduled"


class CreateWorkflowRequest(BaseModel):
    """
    Request body for POST /workflows — create and start a new workflow.
    """
    project_path: str = Field(
        description="Absolute path to the project to scan.",
        examples=["/home/user/my-project"],
    )
    trigger: WorkflowTrigger = Field(
        default=WorkflowTrigger.MANUAL,
        description="What triggered this workflow.",
    )
    repository: str = Field(
        default="",
        description="Repository in owner/repo format.",
        examples=["rugvedtech1/aiqe"],
    )
    branch: str = Field(
        default="",
        description="Branch name to scan.",
        examples=["feature/auth-redesign"],
    )
    pr_number: Optional[int] = Field(
        default=None,
        description="Pull Request number (if trigger is pr).",
        examples=[42],
    )
    provider: Optional[str] = Field(
        default=None,
        description="AI provider override (uses default if not set).",
        examples=["anthropic", "openai"],
    )
    dry_run: bool = Field(
        default=False,
        description=(
            "If true, return the execution plan without running tests."
        ),
    )

    @field_validator("project_path")
    @classmethod
    def validate_project_path(cls, v: str) -> str:
        from pathlib import Path
        path = Path(v)
        if not path.exists():
            raise ValueError(f"Project path does not exist: {v}")
        if not path.is_dir():
            raise ValueError(f"Project path is not a directory: {v}")
        return str(path.resolve())


class WorkflowStatusSchema(str, Enum):
    """Workflow lifecycle status values."""
    PENDING = "pending"
    RUNNING = "running"
    CHECKPOINTED = "checkpointed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRecordSchema(BaseModel):
    """Per-agent execution record in a workflow response."""
    status: str
    duration_seconds: float = 0.0
    error: Optional[str] = None
    skip_reason: Optional[str] = None
    blocked_by: Optional[str] = None
    ai_tokens_used: int = 0


class WorkflowResponse(BaseModel):
    """
    Response schema for workflow operations.
    Returned by POST /workflows and GET /workflows/{id}.
    """
    id: str = Field(description="Unique workflow identifier.")
    status: str = Field(description="Current workflow status.")
    trigger: str = Field(description="What triggered this workflow.")
    repository: str = Field(description="Repository being scanned.")
    branch: str = Field(description="Branch being scanned.")
    pr_number: Optional[int] = Field(
        default=None,
        description="PR number if trigger is pr.",
    )
    bugs_count: int = Field(
        default=0,
        description="Total bugs found.",
    )
    agents_completed: int = Field(
        default=0,
        description="Number of agents that completed.",
    )
    agents_skipped: int = Field(
        default=0,
        description="Number of agents skipped due to failures.",
    )
    agent_records: dict[str, AgentRecordSchema] = Field(
        default_factory=dict,
        description="Per-agent execution details.",
    )
    error: Optional[str] = Field(
        default=None,
        description="Top-level error if the workflow failed.",
    )
    workspace_path: str = Field(
        default="",
        description="Path to workflow artifacts.",
    )
    started_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp when workflow started.",
    )
    completed_at: Optional[str] = Field(
        default=None,
        description="ISO 8601 timestamp when workflow completed.",
    )
    duration_seconds: Optional[float] = Field(
        default=None,
        description="Total workflow duration in seconds.",
    )
    created_at: str = Field(
        description="ISO 8601 timestamp when context was created.",
    )


class WorkflowListResponse(BaseModel):
    """Response for listing multiple workflows."""
    workflows: list[WorkflowResponse]
    total: int


# ==================================================
# BUG SCHEMAS
# ==================================================

class BugSeveritySchema(str, Enum):
    """Bug severity levels matching ADR-008."""
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"
    INFORMATIONAL = "Informational"


class EvidenceSchema(BaseModel):
    """Evidence item supporting a bug finding."""
    kind: str = Field(
        description="Evidence type: log, screenshot, code_snippet, etc."
    )
    content: str = Field(description="The evidence content.")
    source: str = Field(description="Where this evidence came from.")
    relevance: str = Field(
        default="",
        description="Why this evidence supports the finding.",
    )


class BugResponse(BaseModel):
    """
    Response schema for a bug report.
    Implements ADR-008 (severity + confidence) and
    ADR-011 (explainability).
    """
    id: str
    severity: str
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="AI confidence score 0.0-1.0 (ADR-008).",
    )
    title: str
    root_cause: str = Field(
        description="Root cause analysis (ADR-011).",
    )
    evidence: list[EvidenceSchema] = Field(
        default_factory=list,
        description="Supporting evidence (ADR-011).",
    )
    affected_feature: str
    affected_files: list[str] = Field(default_factory=list)
    dependency_chain: list[str] = Field(
        default_factory=list,
        description="How this failure propagates (ADR-011).",
    )
    suggested_fix: str = Field(
        description="Suggested fix (never auto-applied, ADR-009).",
    )
    fix_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the suggested fix.",
    )
    is_downstream: bool = Field(
        default=False,
        description="Whether this is a downstream effect of another bug.",
    )
    root_bug_id: Optional[str] = Field(
        default=None,
        description="Root cause bug ID if this is a downstream effect.",
    )
    related_tests: list[str] = Field(default_factory=list)
    workflow_id: str = ""
    repository: str = ""


class BugListResponse(BaseModel):
    """Response for listing bugs from a workflow."""
    bugs: list[BugResponse]
    total: int
    by_severity: dict[str, int] = Field(
        default_factory=dict,
        description="Count of bugs per severity level.",
    )


# ==================================================
# REPORT SCHEMAS
# ==================================================

class ReportFormat(str, Enum):
    """Available report formats."""
    MARKDOWN = "markdown"
    JSON = "json"
    HTML = "html"


class GenerateReportRequest(BaseModel):
    """Request body for POST /workflows/{id}/report."""
    format: ReportFormat = Field(
        default=ReportFormat.MARKDOWN,
        description="Output format for the report.",
    )
    include_audit: bool = Field(
        default=False,
        description="Include the full audit trail in the report.",
    )
    notify_github_pr: bool = Field(
        default=False,
        description=(
            "Post the report as a GitHub PR comment. "
            "Requires GITHUB_TOKEN in configuration."
        ),
    )
    notify_slack: bool = Field(
        default=False,
        description=(
            "Send a notification to the configured Slack channel. "
            "Requires SLACK_BOT_TOKEN in configuration."
        ),
    )


class ReportResponse(BaseModel):
    """Response containing a generated report."""
    workflow_id: str
    format: str
    content: str = Field(description="The report content.")
    report_path: Optional[str] = Field(
        default=None,
        description="Path where the report was saved (if applicable).",
    )
    generated_at: str


# ==================================================
# PLUGIN SCHEMAS
# ==================================================

class CapabilitySchema(BaseModel):
    """A plugin capability item."""
    id: str
    group: str
    display_name: str
    description: str
    is_restricted: bool
    risk_level: int


class PluginInfoResponse(BaseModel):
    """Detailed plugin information response."""
    name: str
    version: str
    plugin_type: str
    author: str
    description: str
    is_healthy: bool
    required_capabilities: list[CapabilitySchema]
    has_restricted_capabilities: bool
    max_risk_level: int


class ValidateManifestRequest(BaseModel):
    """
    Request body for POST /plugins/validate.
    Accepts the plugin manifest as a dict matching plugin.toml structure.
    """
    manifest: dict[str, Any] = Field(
        description="Plugin manifest dict matching plugin.toml structure.",
    )


class ValidateManifestResponse(BaseModel):
    """Response from plugin manifest validation."""
    is_valid: bool
    plugin_name: str = ""
    plugin_type: str = ""
    capability_count: int = 0
    has_restricted: bool = False
    max_risk_level: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ==================================================
# GATEWAY SCHEMAS
# ==================================================

class GatewayTestRequest(BaseModel):
    """Request body for POST /gateway/test."""
    message: str = Field(
        default="Respond with: AIQE gateway test successful",
        description="Test message to send to the AI provider.",
    )
    provider: Optional[str] = Field(
        default=None,
        description="Provider to test. Uses default if not specified.",
    )
    max_tokens: int = Field(
        default=50,
        description="Maximum tokens for the test response.",
        ge=1,
        le=500,
    )


class GatewayTestResponse(BaseModel):
    """Response from POST /gateway/test."""
    success: bool
    provider: str
    model: str
    response: str
    total_tokens: int
    latency_seconds: float


class GatewayStatusResponse(BaseModel):
    """Response from GET /gateway/status."""
    available_providers: list[str]
    total_requests: int
    total_tokens: int
    total_errors: int
    requests_by_provider: dict[str, int]
    tokens_by_provider: dict[str, int]


class ProviderStatusSchema(BaseModel):
    """Status of a single AI provider."""
    provider: str
    total_keys: int
    available_keys: int
    request_count: int
    error_count: int


# ==================================================
# WEBHOOK SCHEMAS
# ==================================================

class GitHubWebhookPayload(BaseModel):
    """
    Incoming GitHub webhook payload.

    AIQE listens for pull_request events to trigger automatic
    PR quality scans.
    """
    action: str = Field(
        description="GitHub webhook action: opened, synchronize, reopened, etc."
    )
    number: Optional[int] = Field(
        default=None,
        description="PR number.",
    )
    pull_request: Optional[dict[str, Any]] = Field(
        default=None,
        description="Pull request data from GitHub.",
    )
    repository: Optional[dict[str, Any]] = Field(
        default=None,
        description="Repository data from GitHub.",
    )
    sender: Optional[dict[str, Any]] = Field(
        default=None,
        description="User who triggered the webhook.",
    )


class WebhookResponse(BaseModel):
    """Response to webhook delivery."""
    received: bool = True
    workflow_id: Optional[str] = None
    message: str = ""


# ==================================================
# HEALTH SCHEMAS
# ==================================================

class HealthStatus(str, Enum):
    """Service health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class HealthCheckResponse(BaseModel):
    """Response from GET /health."""
    status: HealthStatus
    version: str
    checks: dict[str, str] = Field(
        default_factory=dict,
        description="Individual component health checks.",
    )
    uptime_seconds: float = 0.0


class ReadyResponse(BaseModel):
    """Response from GET /ready — readiness probe for Kubernetes."""
    ready: bool
    checks: dict[str, bool] = Field(default_factory=dict)
