"""
AIQE BaseAgent — Abstract Base Class for All Agents.

Every one of the 15 AIQE agents inherits from BaseAgent.
This class enforces the contract that every agent must follow:

1. Typed input and output (from aiqe.agents.types)
2. Automatic lifecycle logging (started, completed, failed)
3. Duration tracking
4. Audit trail integration (ADR-012)
5. Explainability enforcement (ADR-011) — output must have reasoning
6. Error handling that never crashes the workflow silently
7. dry_run support for testing

Why an abstract base class instead of a protocol?
    A Protocol defines the interface but cannot enforce behaviour.
    An ABC can enforce behaviour through:
    - @abstractmethod (subclass must implement run_impl)
    - __init_subclass__ (validate subclass at class definition time)
    - Template Method pattern (run() calls run_impl() with guards)

    The Template Method pattern is the key design decision here:
    run() is the public method that handles ALL cross-cutting concerns
    (logging, timing, error handling, audit). run_impl() is where
    each agent puts its actual logic. Agent authors never have to
    remember to add logging or error handling — it is automatic.

Template Method pattern:
    ┌─────────────────────────────────────┐
    │  BaseAgent.run()  ← public method   │
    │    ├── validate_input()             │
    │    ├── log "agent_started"          │
    │    ├── start timer                  │
    │    ├── await self.run_impl()  ◄───── agent puts logic here
    │    ├── enforce explainability       │
    │    ├── log "agent_completed"        │
    │    └── return typed output          │
    └─────────────────────────────────────┘
"""

from __future__ import annotations

import abc
from typing import Any, ClassVar

from aiqe.agents.types import AgentInput, AgentOutput
from aiqe.shared.exceptions import AgentError
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import Timer

logger = get_logger(__name__)


class BaseAgent(abc.ABC):
    """
    Abstract base class for all AIQE agents.

    Subclasses must implement:
        - NAME: class variable — the agent's registered name
        - DESCRIPTION: class variable — one sentence description
        - TIER: class variable — which implementation tier (1-4)
        - run_impl(): the actual agent logic

    Subclasses may override:
        - validate_input(): add agent-specific input validation
        - get_dependencies(): return list of agent names this depends on

    Usage (from registry/orchestrator perspective):
        agent = ProjectAnalysisAgent()
        output = await agent.run(input_data)
        # output is always a typed AgentOutput subclass
        # output.success tells you if it worked
        # output.reasoning tells you why (ADR-011)
        # output.evidence tells you what data supports it (ADR-011)
    """

    # Every subclass must declare these class variables.
    NAME: ClassVar[str] = ""
    DESCRIPTION: ClassVar[str] = ""
    TIER: ClassVar[int] = 0
    DEPENDENCIES: ClassVar[list[str]] = []

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """
        Validate that every subclass declares required class variables.

        This runs at class definition time, not at runtime.
        If an agent is missing NAME or TIER, the error surfaces
        immediately when the module is imported, not when the
        agent is first executed.
        """
        super().__init_subclass__(**kwargs)

        # Skip validation for abstract intermediary classes
        if abc.ABC in cls.__bases__:
            return
        if getattr(cls, "__abstractmethods__", None):
            return

        if not cls.NAME:
            msg = (
                f"Agent class {cls.__name__} must declare a non-empty "
                f"NAME class variable."
            )
            raise TypeError(msg)

        if cls.TIER not in {1, 2, 3, 4}:
            msg = (
                f"Agent class {cls.__name__} must declare TIER as "
                f"1, 2, 3, or 4. Got: {cls.TIER!r}"
            )
            raise TypeError(msg)

    async def run(self, input_data: AgentInput) -> AgentOutput:
        """
        Execute this agent with full lifecycle management.

        This is the ONLY public method callers should use.
        It wraps run_impl() with:
            - Input validation
            - Lifecycle logging (started/completed/failed)
            - Duration tracking
            - Explainability enforcement
            - Safe error handling

        Args:
            input_data: Typed agent input. Must be an AgentInput subclass.

        Returns:
            AgentOutput subclass. Always returned — never raises.
            Check output.success to determine if the agent succeeded.
        """
        agent_logger = get_logger(self.__class__.__module__)

        agent_logger.info(
            "agent_started",
            agent_name=self.NAME,
            agent_tier=self.TIER,
            workflow_id=input_data.workflow_id,
            dry_run=input_data.dry_run,
        )

        # Validate input before doing any work
        try:
            self.validate_input(input_data)
        except Exception as e:
            agent_logger.error(
                "agent_input_validation_failed",
                agent_name=self.NAME,
                workflow_id=input_data.workflow_id,
                error=str(e),
            )
            return self._make_error_output(
                error=f"Input validation failed: {e}",
                duration_seconds=0.0,
            )

        with Timer() as timer:
            try:
                if input_data.dry_run:
                    output = await self._run_dry(input_data)
                else:
                    output = await self.run_impl(input_data)

                output.duration_seconds = timer.elapsed_seconds

                # Enforce explainability (ADR-011)
                # Every successful output must have reasoning.
                if output.success and not output.reasoning:
                    output.warnings.append(
                        f"Agent {self.NAME} produced output without "
                        f"reasoning. ADR-011 requires all AI conclusions "
                        f"to include reasoning."
                    )
                    agent_logger.warning(
                        "agent_output_missing_reasoning",
                        agent_name=self.NAME,
                        workflow_id=input_data.workflow_id,
                    )

                agent_logger.info(
                    "agent_completed",
                    agent_name=self.NAME,
                    workflow_id=input_data.workflow_id,
                    duration_seconds=timer.elapsed_seconds,
                    success=output.success,
                    confidence=output.confidence,
                    warnings_count=len(output.warnings),
                    ai_tokens_used=output.ai_tokens_used,
                )

                return output

            except AgentError:
                # AgentError is already well-formed — re-raise so
                # the Scheduler's error handling can process it.
                raise

            except Exception as e:
                agent_logger.error(
                    "agent_failed_unexpectedly",
                    agent_name=self.NAME,
                    workflow_id=input_data.workflow_id,
                    error_type=type(e).__name__,
                    error=str(e),
                    duration_seconds=timer.elapsed_seconds,
                )
                # Wrap unexpected exceptions so callers always get
                # a typed AgentError, not a raw exception.
                raise AgentError(
                    message=f"Agent {self.NAME} failed: {e}",
                    agent_name=self.NAME,
                    workflow_id=input_data.workflow_id,
                ) from e

    @abc.abstractmethod
    async def run_impl(self, input_data: AgentInput) -> AgentOutput:
        """
        Implement the agent's actual logic here.

        This method is called by run() after input validation and
        logging setup. It must return a typed AgentOutput subclass.

        Subclasses must:
            - Return an AgentOutput with success=True on success.
            - Return an AgentOutput with success=False and error
              set on non-fatal failure (the agent ran but found
              nothing actionable).
            - Raise AgentError for fatal failures that should
              propagate to the Scheduler's failure handling.
            - Always populate output.reasoning (ADR-011).
            - Always populate output.evidence where relevant (ADR-011).

        Args:
            input_data: Validated agent input.

        Returns:
            Typed AgentOutput subclass.
        """

    def validate_input(self, input_data: AgentInput) -> None:
        """
        Validate agent-specific input constraints.

        Base implementation checks that workflow_id is present.
        Subclasses should call super().validate_input() and then
        add their own checks.

        Args:
            input_data: The input to validate.

        Raises:
            ValueError: If any validation constraint is violated.
        """
        if not input_data.workflow_id:
            msg = (
                f"Agent {self.NAME} received input with empty workflow_id. "
                f"All agent inputs must carry a workflow_id for audit tracking."
            )
            raise ValueError(msg)

    def get_dependencies(self) -> list[str]:
        """
        Return the list of agent names this agent depends on.

        Used by the Agent Registry for execution order resolution.
        Override in subclasses if DEPENDENCIES class variable is
        not sufficient (e.g. dynamic dependencies).

        Returns:
            List of agent name strings.
        """
        return list(self.DEPENDENCIES)

    async def _run_dry(self, input_data: AgentInput) -> AgentOutput:
        """
        Default dry_run implementation.

        Returns a successful output explaining what the agent
        would do without actually doing it. Subclasses may
        override to provide more detailed dry_run descriptions.

        Args:
            input_data: The agent input.

        Returns:
            AgentOutput with dry_run description in reasoning.
        """
        output = AgentOutput()
        output.reasoning = (
            f"[DRY RUN] {self.NAME} would execute with: "
            f"project_path={input_data.project_path!r}. "
            f"No actual work was performed."
        )
        output.metadata["dry_run"] = True
        output.metadata["agent_name"] = self.NAME
        output.metadata["dependencies"] = self.get_dependencies()
        return output

    def _make_error_output(
        self,
        error: str,
        duration_seconds: float = 0.0,
    ) -> AgentOutput:
        """
        Create a failed AgentOutput with a given error message.

        Used internally to return typed errors without raising exceptions.

        Args:
            error: The error message.
            duration_seconds: How long the agent ran before failing.

        Returns:
            AgentOutput with success=False and error set.
        """
        output = AgentOutput()
        output.success = False
        output.error = error
        output.duration_seconds = duration_seconds
        output.confidence = 0.0
        output.reasoning = f"Agent {self.NAME} failed: {error}"
        return output

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.NAME!r}, tier={self.TIER})"
