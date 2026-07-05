"""
AIQE Shared Memory Schema.

Defines all valid memory keys as typed constants.
Agents never use raw string keys — they use MemoryKey.

Why typed keys instead of raw strings?
    Raw string keys ("feature_graph", "feture_graph", "FeatureGraph")
    are silent bugs. A typo in a key name produces None at read time
    with no error — the agent silently operates on missing data.

    Typed constants catch typos at import time (IDE, mypy, grep).
    They also serve as the living documentation of what data flows
    between agents — every inter-agent data contract is visible here.

Memory key naming convention:
    <producer_agent>.<data_name>
    Example: "project_analysis.result" is written by the Project
    Analysis Agent and read by Test Strategy, Test Case Generator, etc.

Memory value contracts:
    Every key has a documented type for its value.
    Agents must write the correct type — no silent coercion.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MemoryKey:
    """
    A typed memory key with documentation.

    Attributes:
        key: The string key used in the store.
        description: What this key holds and who writes/reads it.
        writer: Which agent writes this key.
        readers: Which agents read this key.
    """
    key: str
    description: str
    writer: str
    readers: list[str]

    def __str__(self) -> str:
        return self.key

    def __hash__(self) -> int:
        return hash(self.key)


class MemoryKeys:
    """
    All valid shared memory keys in AIQE.

    Usage:
        from aiqe.memory.schema import MemoryKeys

        # Write
        await memory.set(MemoryKeys.PROJECT_ANALYSIS_RESULT, output.to_dict())

        # Read
        data = await memory.get(MemoryKeys.PROJECT_ANALYSIS_RESULT)
    """

    # ==================================================
    # TIER 1 — PROJECT ANALYSIS
    # ==================================================

    PROJECT_ANALYSIS_RESULT = MemoryKey(
        key="project_analysis.result",
        description=(
            "Full output of the Project Analysis Agent. Contains "
            "detected language, framework, dependencies, routes, auth "
            "method, database, entry points, and test files."
        ),
        writer="project_analysis",
        readers=["test_strategy", "test_case_generator",
                 "security_testing", "bug_analysis",
                 "feature_discovery", "requirement_intelligence"],
    )

    PROJECT_FILE_TREE = MemoryKey(
        key="project_analysis.file_tree",
        description="Structured file tree of the scanned project.",
        writer="project_analysis",
        readers=["test_strategy", "automation_generator", "security_testing"],
    )

    # ==================================================
    # TIER 1 — DEPENDENCY INTELLIGENCE
    # ==================================================

    FEATURE_GRAPH = MemoryKey(
        key="intelligence.feature_graph",
        description=(
            "Business feature graph. Nodes are features, edges are "
            "dependencies between features. Used for test scope "
            "decisions and failure isolation."
        ),
        writer="feature_discovery",
        readers=["test_strategy", "test_case_generator",
                 "bug_analysis", "release_intelligence"],
    )

    CODE_DEPENDENCY_GRAPH = MemoryKey(
        key="intelligence.code_dependency_graph",
        description="Module/class/function import dependency graph.",
        writer="project_analysis",
        readers=["test_strategy", "bug_analysis", "release_intelligence"],
    )

    API_DEPENDENCY_GRAPH = MemoryKey(
        key="intelligence.api_dependency_graph",
        description="API endpoint consumer/dependency graph.",
        writer="project_analysis",
        readers=["api_validation", "test_strategy", "bug_analysis"],
    )

    DATABASE_DEPENDENCY_GRAPH = MemoryKey(
        key="intelligence.database_dependency_graph",
        description="Database table/view/migration dependency graph.",
        writer="project_analysis",
        readers=["database_validation", "bug_analysis"],
    )

    UI_NAVIGATION_GRAPH = MemoryKey(
        key="intelligence.ui_navigation_graph",
        description="UI screen/route/navigation flow graph.",
        writer="project_analysis",
        readers=["browser_execution", "test_case_generator"],
    )

    # ==================================================
    # TIER 1 — TEST STRATEGY
    # ==================================================

    TEST_STRATEGY_RESULT = MemoryKey(
        key="test_strategy.result",
        description=(
            "Complete test strategy output. Contains ordered test plan, "
            "risk assessment, affected features, and regression risk flag."
        ),
        writer="test_strategy",
        readers=["test_case_generator", "release_intelligence"],
    )

    CHANGED_FILES = MemoryKey(
        key="test_strategy.changed_files",
        description=(
            "List of files changed in this PR/branch. Written by the "
            "Orchestrator from git diff. Used by Test Strategy to "
            "determine test scope."
        ),
        writer="orchestrator",
        readers=["test_strategy", "release_intelligence"],
    )

    AFFECTED_FEATURES = MemoryKey(
        key="test_strategy.affected_features",
        description="Business features affected by the current changeset.",
        writer="test_strategy",
        readers=["test_case_generator", "bug_analysis", "release_intelligence"],
    )

    # ==================================================
    # TIER 1 — TEST CASE GENERATOR
    # ==================================================

    GENERATED_TEST_CASES = MemoryKey(
        key="test_case_generator.test_cases",
        description=(
            "All generated test cases. Consumed by Automation Generator, "
            "Browser Execution, and API Validation agents."
        ),
        writer="test_case_generator",
        readers=["automation_generator", "browser_execution", "api_validation"],
    )

    # ==================================================
    # TIER 2 — AUTOMATION GENERATOR
    # ==================================================

    GENERATED_PLAYWRIGHT_SCRIPTS = MemoryKey(
        key="automation_generator.playwright_scripts",
        description="Generated Playwright test scripts ready for execution.",
        writer="automation_generator",
        readers=["browser_execution"],
    )

    GENERATED_API_TESTS = MemoryKey(
        key="automation_generator.api_tests",
        description="Generated API test cases ready for execution.",
        writer="automation_generator",
        readers=["api_validation"],
    )

    # ==================================================
    # TIER 2 — BROWSER EXECUTION
    # ==================================================

    BROWSER_EXECUTION_RESULTS = MemoryKey(
        key="browser_execution.results",
        description=(
            "Browser test execution results. Contains passed/failed tests, "
            "screenshots paths, video paths, console logs, network logs."
        ),
        writer="browser_execution",
        readers=["bug_analysis", "report"],
    )

    BROWSER_FAILED_TESTS = MemoryKey(
        key="browser_execution.failed_tests",
        description="Only the failed browser test results.",
        writer="browser_execution",
        readers=["bug_analysis"],
    )

    # ==================================================
    # TIER 2 — API VALIDATION
    # ==================================================

    API_VALIDATION_RESULTS = MemoryKey(
        key="api_validation.results",
        description="API validation results across all endpoints.",
        writer="api_validation",
        readers=["bug_analysis", "report", "release_intelligence"],
    )

    # ==================================================
    # TIER 3 — SECURITY TESTING
    # ==================================================

    SECURITY_SCAN_RESULTS = MemoryKey(
        key="security_testing.results",
        description=(
            "Security scan results. Contains findings for SQLi, XSS, "
            "auth issues, exposed secrets, dependency CVEs, header issues."
        ),
        writer="security_testing",
        readers=["bug_analysis", "report", "release_intelligence"],
    )

    # ==================================================
    # TIER 3 — PERFORMANCE
    # ==================================================

    PERFORMANCE_RESULTS = MemoryKey(
        key="performance.results",
        description="Performance test results including Core Web Vitals.",
        writer="performance",
        readers=["bug_analysis", "report", "release_intelligence"],
    )

    # ==================================================
    # TIER 3 — DATABASE VALIDATION
    # ==================================================

    DATABASE_VALIDATION_RESULTS = MemoryKey(
        key="database_validation.results",
        description="Database validation results including migration checks.",
        writer="database_validation",
        readers=["bug_analysis", "report"],
    )

    # ==================================================
    # TIER 4 — BUG ANALYSIS
    # ==================================================

    BUG_ANALYSIS_RESULTS = MemoryKey(
        key="bug_analysis.results",
        description=(
            "All bugs found, with severity, confidence, root cause, "
            "evidence, affected features, and suggested fixes."
        ),
        writer="bug_analysis",
        readers=["report", "release_intelligence"],
    )

    # ==================================================
    # TIER 4 — RELEASE INTELLIGENCE
    # ==================================================

    RELEASE_INTELLIGENCE_RESULT = MemoryKey(
        key="release_intelligence.result",
        description=(
            "Final Release Intelligence Engine output. Contains merge "
            "recommendation, risk level, reasoning, and fix priority. "
            "This is the Human Review Gate input (ADR-009, ADR-010)."
        ),
        writer="release_intelligence",
        readers=["report"],
    )

    # ==================================================
    # SYSTEM — WORKFLOW METADATA
    # ==================================================

    WORKFLOW_METADATA = MemoryKey(
        key="system.workflow_metadata",
        description=(
            "Workflow-level metadata: repository, PR number, branch, "
            "trigger, commit SHA, author. Written by Orchestrator."
        ),
        writer="orchestrator",
        readers=["*"],  # All agents may read workflow metadata
    )

    @classmethod
    def all_keys(cls) -> list[MemoryKey]:
        """Return all defined memory keys."""
        return [
            v for v in cls.__dict__.values()
            if isinstance(v, MemoryKey)
        ]

    @classmethod
    def keys_for_agent(cls, agent_name: str) -> dict[str, list[MemoryKey]]:
        """
        Return all memory keys relevant to a given agent,
        grouped by whether the agent writes or reads them.

        Args:
            agent_name: The agent's registered name.

        Returns:
            Dict with "writes" and "reads" lists of MemoryKeys.
        """
        writes = []
        reads = []
        for key in cls.all_keys():
            if key.writer == agent_name:
                writes.append(key)
            if agent_name in key.readers or "*" in key.readers:
                reads.append(key)
        return {"writes": writes, "reads": reads}
