"""
AIQE Memory & Learning Agent.

Accesses historical workflow data in READ-ONLY mode (ADR-006)
to detect regressions, identify recurring failures, and
improve future test strategies.

Responsibilities:
    - Compare current bugs to historical failures
    - Flag regressions (bugs that were fixed and reappeared)
    - Identify persistently failing tests (flaky tests)
    - Build failure pattern knowledge
    - Update the learning database for future runs
    - Provide trend analysis to the Release Intelligence Engine

ADR-006 compliance:
    This agent reads historical workflow data in READ-ONLY mode.
    It NEVER modifies another workflow's runtime state.
    It writes only to its own designated memory keys.

Tier: 4 (Intelligence)
Dependencies: bug_analysis
Memory Reads: bug_analysis.results (current + historical READ-ONLY)
Memory Writes: none to other workflows (read-only exception)
"""

from __future__ import annotations

from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class MemoryLearningOutput(AgentOutput):
    """Output from the Memory & Learning Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.regressions_detected: list[dict[str, Any]] = []
        self.recurring_failures: list[dict[str, Any]] = []
        self.new_failures: list[dict[str, Any]] = []
        self.flaky_tests: list[str] = []
        self.failure_trends: dict[str, Any] = {}
        self.learning_insights: list[str] = []
        self.historical_runs_analysed: int = 0

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "regressions_detected": self.regressions_detected,
            "recurring_failures": self.recurring_failures,
            "new_failures": self.new_failures,
            "flaky_tests": self.flaky_tests,
            "failure_trends": self.failure_trends,
            "learning_insights": self.learning_insights,
            "historical_runs_analysed": self.historical_runs_analysed,
        }


class MemoryLearningInput(AgentInput):
    """Input for the Memory & Learning Agent."""
    max_historical_runs: int = 10
    regression_lookback_days: int = 30


class MemoryLearningAgent(BaseAgent):
    """
    Memory & Learning Agent — Tier 4.

    Reads historical workflow data to detect regressions
    and improve future test strategies.
    """

    NAME = "memory_learning"
    DESCRIPTION = (
        "Accesses historical workflow data (READ-ONLY, ADR-006) "
        "to detect regressions, identify recurring failures, "
        "and provide trend analysis."
    )
    TIER = 4
    DEPENDENCIES = ["bug_analysis"]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
        persistence_bundle: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway
        self._persistence = persistence_bundle

    async def run_impl(self, input_data: AgentInput) -> MemoryLearningOutput:
        """Run regression detection and learning analysis."""
        assert isinstance(input_data, MemoryLearningInput), (
            f"Expected MemoryLearningInput, got {type(input_data).__name__}"
        )

        output = MemoryLearningOutput()

        # Load current bugs
        current_bugs: list[dict[str, Any]] = []
        if self._memory:
            bug_results = await self._memory.get(
                key=str(MemoryKeys.BUG_ANALYSIS_RESULTS),
                reader=self.NAME,
            ) or {}
            current_bugs = bug_results.get("bugs", [])

        if not current_bugs:
            output.reasoning = (
                "No current bugs to analyse for regressions. "
                "All tests passed — no historical comparison needed."
            )
            output.confidence = 1.0
            return output

        # Load historical bugs from persistence (read-only)
        historical_bugs = await self._load_historical_bugs(input_data)
        output.historical_runs_analysed = len(historical_bugs)

        # Detect regressions
        regressions = self._detect_regressions(
            current_bugs=current_bugs,
            historical_bugs=historical_bugs,
        )
        output.regressions_detected = regressions

        # Classify as new vs recurring
        recurring = self._find_recurring_failures(
            current_bugs=current_bugs,
            historical_bugs=historical_bugs,
        )
        output.recurring_failures = recurring

        current_titles = {b.get("title", "") for b in current_bugs}
        historical_titles = {b.get("title", "") for b in historical_bugs}
        new_bug_titles = current_titles - historical_titles
        output.new_failures = [
            b for b in current_bugs
            if b.get("title") in new_bug_titles
        ]

        # Generate learning insights
        output.learning_insights = self._generate_insights(
            current_bugs=current_bugs,
            regressions=regressions,
            recurring=recurring,
        )

        # Failure trends
        output.failure_trends = self._compute_trends(
            current_bugs=current_bugs,
            historical_bugs=historical_bugs,
        )

        output.reasoning = (
            f"Memory & Learning analysis complete. "
            f"Analysed {output.historical_runs_analysed} historical runs. "
            f"Current bugs: {len(current_bugs)}. "
            f"Regressions: {len(regressions)}. "
            f"Recurring failures: {len(recurring)}. "
            f"New failures: {len(output.new_failures)}."
        )
        output.confidence = 0.80

        if regressions:
            output.add_evidence(
                kind="regression_detection",
                content=(
                    f"{len(regressions)} regressions detected: "
                    f"{[r.get('title') for r in regressions[:3]]}"
                ),
                source="memory_learning_agent",
                relevance=(
                    "Regressions indicate previously fixed bugs have reappeared"
                ),
            )

        output.suggested_next_action = (
            f"Release Intelligence Engine should factor "
            f"{len(regressions)} regressions into its risk assessment."
            if regressions
            else "No regressions detected in this PR."
        )

        return output

    async def _load_historical_bugs(
        self, input_data: MemoryLearningInput
    ) -> list[dict[str, Any]]:
        """Load historical bugs from persistence (read-only)."""
        if not self._persistence:
            return []

        try:
            repository = ""
            if self._memory:
                metadata = await self._memory.get(
                    key=str(MemoryKeys.WORKFLOW_METADATA),
                    reader=self.NAME,
                ) or {}
                repository = metadata.get("repository", "")

            if not repository:
                return []

            # Read historical bugs — this is the ADR-006
            # read-only exception for the Memory & Learning Agent
            historical = await self._persistence.bugs.find_by_severity(
                severity="Critical",
                repository=repository,
                limit=50,
            )
            historical += await self._persistence.bugs.find_by_severity(
                severity="High",
                repository=repository,
                limit=50,
            )
            return historical

        except Exception as e:
            logger.warning(
                "historical_bugs_load_failed",
                error=str(e),
            )
            return []

    def _detect_regressions(
        self,
        current_bugs: list[dict[str, Any]],
        historical_bugs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Find bugs that appeared before and are back."""
        historical_titles = {
            b.get("title", "").lower()
            for b in historical_bugs
        }
        return [
            {**b, "is_regression": True}
            for b in current_bugs
            if b.get("title", "").lower() in historical_titles
        ]

    def _find_recurring_failures(
        self,
        current_bugs: list[dict[str, Any]],
        historical_bugs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Find failures that appear in both current and historical."""
        historical_features = {
            b.get("affected_feature", "").lower()
            for b in historical_bugs
        }
        return [
            b for b in current_bugs
            if b.get("affected_feature", "").lower() in historical_features
        ]

    def _generate_insights(
        self,
        current_bugs: list[dict[str, Any]],
        regressions: list[dict[str, Any]],
        recurring: list[dict[str, Any]],
    ) -> list[str]:
        """Generate learning insights from failure patterns."""
        insights = []

        if regressions:
            insights.append(
                f"{len(regressions)} regression(s) detected. "
                f"Previously fixed bugs have reappeared. "
                f"Consider adding regression tests for: "
                f"{[r.get('affected_feature') for r in regressions[:3]]}."
            )

        if recurring:
            features = list({
                b.get("affected_feature") for b in recurring
            })
            insights.append(
                f"Features with recurring failures: {features[:5]}. "
                f"These areas may need deeper test coverage or "
                f"architectural attention."
            )

        critical_bugs = [
            b for b in current_bugs if b.get("severity") == "Critical"
        ]
        if critical_bugs:
            insights.append(
                f"{len(critical_bugs)} Critical bug(s) found. "
                f"Immediate attention required before merge."
            )

        if not insights:
            insights.append(
                "No significant patterns detected. "
                "Test results are consistent with historical norms."
            )

        return insights

    def _compute_trends(
        self,
        current_bugs: list[dict[str, Any]],
        historical_bugs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Compute failure trend data."""
        current_by_sev: dict[str, int] = {}
        for b in current_bugs:
            s = b.get("severity", "Unknown")
            current_by_sev[s] = current_by_sev.get(s, 0) + 1

        historical_by_sev: dict[str, int] = {}
        for b in historical_bugs:
            s = b.get("severity", "Unknown")
            historical_by_sev[s] = historical_by_sev.get(s, 0) + 1

        return {
            "current_run": current_by_sev,
            "historical_average": historical_by_sev,
            "trend": "improving" if (
                len(current_bugs) < len(historical_bugs)
            ) else "worsening" if (
                len(current_bugs) > len(historical_bugs)
            ) else "stable",
        }
