"""
AIQE Custom Exception Hierarchy.

Every exception raised by AIQE inherits from AIQEError.
This allows callers to catch all AIQE exceptions with a single
except clause, while still being able to catch specific ones.

Design principle:
    Never raise generic Python exceptions (ValueError, RuntimeError)
    from AIQE code. Always raise a specific AIQEError subclass so
    callers know exactly what went wrong and at which layer.

Exception hierarchy:
    AIQEError                          (base — all AIQE exceptions)
    ├── ConfigurationError             (bad config, missing env vars)
    ├── WorkflowError                  (workflow engine failures)
    │   ├── WorkflowContextError       (context isolation violations)
    │   └── CheckpointError            (checkpoint read/write failures)
    ├── AgentError                     (agent execution failures)
    │   ├── AgentNotFoundError         (agent not registered)
    │   └── AgentTimeoutError          (agent exceeded time limit)
    ├── GatewayError                   (AI gateway failures)
    │   ├── ProviderError              (AI provider API failure)
    │   ├── AllProvidersExhaustedError (all keys/providers failed)
    │   └── TokenBudgetExceededError   (token budget limit hit)
    ├── PluginError                    (plugin system failures)
    │   ├── PluginManifestError        (invalid or missing manifest)
    │   ├── CapabilityDeniedError      (plugin requested denied capability)
    │   └── PluginLoadError            (plugin failed to load)
    ├── PersistenceError               (database layer failures)
    │   ├── RecordNotFoundError        (entity not found in DB)
    │   └── MigrationError             (database migration failure)
    ├── IntelligenceError              (dependency graph failures)
    ├── SecurityError                  (security violations)
    │   ├── PromptInjectionError       (detected prompt injection attempt)
    │   └── SecretsLeakError           (detected secrets in output)
    └── ValidationError                (input validation failures)
"""


class AIQEError(Exception):
    """
    Base exception for all AIQE errors.

    All exceptions raised by AIQE code must inherit from this class.
    This allows external callers to catch all AIQE exceptions cleanly.

    Attributes:
        message: Human-readable description of what went wrong.
        context: Optional dictionary of additional context for debugging.
        workflow_id: Optional ID of the workflow context where error occurred.
    """

    def __init__(
        self,
        message: str,
        context: dict | None = None,
        workflow_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.context = context or {}
        self.workflow_id = workflow_id

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"workflow_id={self.workflow_id!r}, "
            f"context={self.context!r})"
        )


# ==================================================
# CONFIGURATION ERRORS
# ==================================================


class ConfigurationError(AIQEError):
    """
    Raised when AIQE configuration is invalid or incomplete.

    Examples:
        - Required environment variable is missing
        - Configuration value is out of valid range
        - Conflicting configuration values
        - Unknown provider specified
    """


# ==================================================
# WORKFLOW ERRORS
# ==================================================


class WorkflowError(AIQEError):
    """Raised when the Workflow Engine encounters a failure."""


class WorkflowContextError(WorkflowError):
    """
    Raised when workflow context isolation is violated.

    This is a critical error. If one workflow attempts to access
    another workflow's state, execution must stop immediately.
    See ADR-006.
    """


class CheckpointError(WorkflowError):
    """
    Raised when a checkpoint cannot be read or written.

    AIQE uses checkpoints to resume long-running workflows after
    provider failures. If checkpointing fails, the workflow cannot
    be safely resumed.
    """


# ==================================================
# AGENT ERRORS
# ==================================================


class AgentError(AIQEError):
    """Raised when an agent fails to execute."""

    def __init__(
        self,
        message: str,
        agent_name: str | None = None,
        context: dict | None = None,
        workflow_id: str | None = None,
    ) -> None:
        super().__init__(message, context, workflow_id)
        self.agent_name = agent_name


class AgentNotFoundError(AgentError):
    """
    Raised when the Agent Registry cannot find a requested agent.

    This usually means the agent was not registered before the
    Orchestrator attempted to dispatch work to it.
    """


class AgentTimeoutError(AgentError):
    """
    Raised when an agent exceeds its configured execution time limit.

    Agents that time out are treated as failures. The Orchestrator
    will record the timeout in the audit trail and apply the
    dependency graph failure isolation rules (ADR-007).
    """


# ==================================================
# AI GATEWAY ERRORS
# ==================================================


class GatewayError(AIQEError):
    """Raised when the AI Gateway encounters a failure."""


class ProviderError(GatewayError):
    """
    Raised when a specific AI provider returns an error.

    The Gateway will attempt retry with exponential backoff
    before raising this exception. See ADR-005.

    Attributes:
        provider: Name of the provider that failed (e.g. 'openai').
        status_code: HTTP status code if applicable.
    """

    def __init__(
        self,
        message: str,
        provider: str | None = None,
        status_code: int | None = None,
        context: dict | None = None,
        workflow_id: str | None = None,
    ) -> None:
        super().__init__(message, context, workflow_id)
        self.provider = provider
        self.status_code = status_code


class AllProvidersExhaustedError(GatewayError):
    """
    Raised when all configured AI providers and API keys have failed.

    This is a fatal gateway error. The workflow must checkpoint its
    current state so it can be resumed when a provider becomes
    available again.
    """


class TokenBudgetExceededError(GatewayError):
    """
    Raised when a workflow exceeds its configured token budget.

    Token budgets prevent runaway costs in enterprise deployments.
    The workflow is checkpointed before this exception propagates.
    """


# ==================================================
# PLUGIN ERRORS
# ==================================================


class PluginError(AIQEError):
    """Raised when the plugin system encounters a failure."""

    def __init__(
        self,
        message: str,
        plugin_name: str | None = None,
        context: dict | None = None,
        workflow_id: str | None = None,
    ) -> None:
        super().__init__(message, context, workflow_id)
        self.plugin_name = plugin_name


class PluginManifestError(PluginError):
    """
    Raised when a plugin manifest is missing, malformed, or declares
    unknown capabilities.

    A plugin without a valid manifest must never be loaded.
    See ADR-003.
    """


class CapabilityDeniedError(PluginError):
    """
    Raised when a plugin attempts to use a capability it did not
    declare in its manifest, or one that was denied by the user
    or organization policy.

    This is a security violation and must be logged immediately.
    See ADR-003.
    """

    def __init__(
        self,
        message: str,
        plugin_name: str | None = None,
        capability: str | None = None,
        context: dict | None = None,
        workflow_id: str | None = None,
    ) -> None:
        super().__init__(message, plugin_name, context, workflow_id)
        self.capability = capability


class PluginLoadError(PluginError):
    """
    Raised when a plugin fails to load after passing manifest
    validation.

    Could indicate import errors, missing dependencies, or
    initialization failures inside the plugin itself.
    """


# ==================================================
# PERSISTENCE ERRORS
# ==================================================


class PersistenceError(AIQEError):
    """Raised when the persistence layer encounters a failure."""


class RecordNotFoundError(PersistenceError):
    """
    Raised when a requested entity does not exist in the database.

    Always include the entity type and ID in the message so
    engineers can debug without reading source code.

    Example:
        raise RecordNotFoundError(
            "WorkflowContext not found",
            entity_type="WorkflowContext",
            entity_id=workflow_id,
        )
    """

    def __init__(
        self,
        message: str,
        entity_type: str | None = None,
        entity_id: str | None = None,
        context: dict | None = None,
        workflow_id: str | None = None,
    ) -> None:
        super().__init__(message, context, workflow_id)
        self.entity_type = entity_type
        self.entity_id = entity_id


class MigrationError(PersistenceError):
    """
    Raised when a database migration fails.

    Migration failures are treated as fatal startup errors.
    AIQE will not start with an unmigrated database.
    """


# ==================================================
# INTELLIGENCE ERRORS
# ==================================================


class IntelligenceError(AIQEError):
    """
    Raised when the Application Dependency Intelligence system
    fails to build or query a dependency graph.

    See ADR-007.
    """


# ==================================================
# SECURITY ERRORS
# ==================================================


class SecurityError(AIQEError):
    """
    Raised when a security violation is detected.

    Security errors are always logged immediately, regardless
    of the configured log level.
    """


class PromptInjectionError(SecurityError):
    """
    Raised when repository content appears to contain a prompt
    injection attempt.

    Repository content is untrusted input. AIQE must never
    interpolate it directly into AI prompts without sanitization.
    """


class SecretsLeakError(SecurityError):
    """
    Raised when a secret, API key, or credential is detected
    in a location where it should not appear (e.g. log output,
    report content, AI prompt).

    This triggers immediate workflow termination and audit logging.
    """


# ==================================================
# VALIDATION ERRORS
# ==================================================


class ValidationError(AIQEError):
    """
    Raised when input validation fails.

    Used for CLI arguments, API payloads, plugin manifests,
    configuration values, and any other external input.

    Attributes:
        field: The field or parameter that failed validation.
        invalid_value: The value that was rejected (sanitized — no secrets).
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        invalid_value: object = None,
        context: dict | None = None,
        workflow_id: str | None = None,
    ) -> None:
        super().__init__(message, context, workflow_id)
        self.field = field
        self.invalid_value = invalid_value
