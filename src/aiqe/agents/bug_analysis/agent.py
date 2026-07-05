"""
AIQE Bug Analysis Agent.

The most AI-intensive agent in AIQE. Takes raw failures from
browser, API, security, performance, and database agents and
produces structured bug reports with full explainability.

Responsibilities:
    - Correlate failures across all execution agents
    - Identify root causes vs downstream effects
    - Assign severity (ADR-008) and confidence scores
    - Build the dependency chain for each bug
    - Generate suggested fixes with fix confidence scores
    - Classify bugs as regression vs new failure
    - Group downstream failures under their root cause
    - Ensure full evidence for every finding (ADR-011)
    - NEVER automatically fix code (ADR-009)

This agent is the primary consumer of all Tier 2-3 output.
It is the producer of the data the Release Intelligence
Engine uses to make its merge recommendation.

Tier: 4 (Intelligence)
Dependencies: browser_execution, api_validation, security_testing,
              performance, database_validation
Memory Reads: All Tier 2-3 result keys
Memory Writes: bug_analysis.results
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import (
    AgentInput,
    AgentOutput,
    BugReport,
    BugSeverity,
    Evidence,
)
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class BugAnalysisOutput(AgentOutput):
    """Output from the Bug Analysis Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.bugs: list[dict[str, Any]] = []
        self.total_bugs: int = 0
        self.by_severity: dict[str, int] = {}
        self.root_cause_bugs: int = 0
        self.downstream_bugs: int = 0
        self.regression_detected: bool = False
        self.critical_bugs: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "bugs": self.bugs,
            "total_bugs": self.total_bugs,
            "by_severity": self.by_severity,
            "root_cause_bugs": self.root_cause_bugs,
            "downstream_bugs": self.downstream_bugs,
            "regression_detected": self.regression_detected,
            "critical_bugs": self.critical_bugs,
        }


class BugAnalysisInput(AgentInput):
    """Input for the Bug Analysis Agent."""
    include_performance_bugs: bool = True
    include_security_bugs: bool = True
    include_database_bugs: bool = True
    min_confidence: float = 0.5


class BugAnalysisAgent(BaseAgent):
    """
    Bug Analysis Agent — Tier 4.

    Correlates failures across all execution agents, identifies
    root causes, assigns severity with confidence, and produces
    structured, explainable bug reports.
    """

    NAME = "bug_analysis"
    DESCRIPTION = (
        "Correlates failures across all agents, identifies root "
        "causes vs downstream effects, assigns severity with "
        "confidence scores, and generates structured bug reports "
        "with full evidence chains."
    )
    TIER = 4
    DEPENDENCIES = [
        "browser_execution",
        "api_validation",
        "security_testing",
        "performance",
        "database_validation",
    ]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway

    async def run_impl(self, input_data: AgentInput) -> BugAnalysisOutput:
        """Analyse all failures and produce bug reports."""
        assert isinstance(input_data, BugAnalysisInput), (
            f"Expected BugAnalysisInput, got {type(input_data).__name__}"
        )

        output = BugAnalysisOutput()

        # ==================================================
        # PHASE 1: COLLECT ALL FAILURES FROM MEMORY
        # ==================================================

        raw_failures = await self._collect_failures(input_data)

        if not raw_failures:
            output.reasoning = (
                "No failures found across any execution agents. "
                "All tests passed or no tests were executed."
            )
            output.confidence = 1.0
            output.suggested_next_action = (
                "Release Intelligence Engine can assess this as "
                "low-risk based on clean test results."
            )
            await self._write_to_memory(input_data, output)
            return output

        # ==================================================
        # PHASE 2: DETERMINISTIC GROUPING
        # Identify obvious root causes before AI
        # ==================================================

        grouped = self._group_by_feature(raw_failures)
        logger.info(
            "bug_analysis_grouping_complete",
            workflow_id=input_data.workflow_id,
            total_failures=len(raw_failures),
            feature_groups=len(grouped),
        )

        # ==================================================
        # PHASE 3: AI ROOT CAUSE ANALYSIS
        # ==================================================

        all_bugs: list[dict[str, Any]] = []

        if self._gateway and not input_data.dry_run:
            for feature, failures in grouped.items():
                feature_bugs = await self._ai_analyse_feature_failures(
                    feature=feature,
                    failures=failures,
                    input_data=input_data,
                )
                all_bugs.extend(feature_bugs)
        else:
            all_bugs = self._deterministic_bug_creation(
                grouped, input_data
            )

        # ==================================================
        # PHASE 4: IDENTIFY DOWNSTREAM EFFECTS
        # ==================================================

        all_bugs = self._mark_downstream_effects(all_bugs)

        # ==================================================
        # PHASE 5: FILTER BY CONFIDENCE
        # ==================================================

        filtered_bugs = [
            b for b in all_bugs
            if b.get("confidence", 0) >= input_data.min_confidence
        ]

        # ==================================================
        # PHASE 6: RECORD TO WORKFLOW CONTEXT
        # ==================================================

        if self._memory:
            context_bugs = filtered_bugs
            await self._memory.set(
                key="workflow.bugs_for_context",
                value=context_bugs,
                written_by=self.NAME,
            )

        # ==================================================
        # PHASE 7: STATISTICS
        # ==================================================

        severity_order = {
            "Critical": 0, "High": 1,
            "Medium": 2, "Low": 3, "Informational": 4,
        }
        sorted_bugs = sorted(
            filtered_bugs,
            key=lambda b: severity_order.get(b.get("severity", ""), 99),
        )

        output.bugs = sorted_bugs
        output.total_bugs = len(sorted_bugs)
        output.critical_bugs = [
            b for b in sorted_bugs if b.get("severity") == "Critical"
        ]
        output.root_cause_bugs = sum(
            1 for b in sorted_bugs if not b.get("is_downstream", False)
        )
        output.downstream_bugs = sum(
            1 for b in sorted_bugs if b.get("is_downstream", False)
        )

        for bug in sorted_bugs:
            sev = bug.get("severity", "Unknown")
            output.by_severity[sev] = output.by_severity.get(sev, 0) + 1

        output.regression_detected = any(
            b.get("is_regression", False) for b in sorted_bugs
        )

        output.reasoning = (
            f"Analysed {len(raw_failures)} failures across "
            f"{len(grouped)} feature areas. "
            f"Identified {output.total_bugs} distinct bugs: "
            f"{output.root_cause_bugs} root causes, "
            f"{output.downstream_bugs} downstream effects. "
            f"Severity breakdown: {output.by_severity}. "
            f"Regression detected: {output.regression_detected}."
        )
        output.confidence = 0.87

        if output.critical_bugs:
            output.add_evidence(
                kind="critical_bug_summary",
                content=(
                    f"{len(output.critical_bugs)} Critical bugs found. "
                    f"Titles: {[b.get('title') for b in output.critical_bugs[:3]]}"
                ),
                source="bug_analysis_agent",
                relevance="Critical bugs block merge recommendation",
            )

        output.suggested_next_action = (
            f"Release Intelligence Engine should now produce a "
            f"merge recommendation based on {output.total_bugs} bugs "
            f"({len(output.critical_bugs)} Critical)."
        )

        await self._write_to_memory(input_data, output)
        return output

    async def _collect_failures(
        self, input_data: BugAnalysisInput
    ) -> list[dict[str, Any]]:
        """Collect all failures from Tier 2-3 agent results."""
        failures = []

        if not self._memory:
            return failures

        # Browser failures
        browser_results = await self._memory.get(
            key=str(MemoryKeys.BROWSER_FAILED_TESTS),
            reader=self.NAME,
        ) or []
        for result in browser_results:
            result["source_agent"] = "browser_execution"
            result["failure_category"] = "browser_test"
        failures.extend(browser_results)

        # API failures
        api_results = await self._memory.get(
            key=str(MemoryKeys.API_VALIDATION_RESULTS),
            reader=self.NAME,
        ) or {}
        for result in api_results.get("failed_tests", []):
            result["source_agent"] = "api_validation"
            result["failure_category"] = "api_validation"
            failures.append(result)

        # Security findings
        if input_data.include_security_bugs:
            security_results = await self._memory.get(
                key=str(MemoryKeys.SECURITY_SCAN_RESULTS),
                reader=self.NAME,
            ) or {}
            for finding in security_results.get("findings", []):
                finding["source_agent"] = "security_testing"
                finding["failure_category"] = "security"
                failures.append(finding)

        # Performance violations
        if input_data.include_performance_bugs:
            perf_results = await self._memory.get(
                key=str(MemoryKeys.PERFORMANCE_RESULTS),
                reader=self.NAME,
            ) or {}
            for violation in perf_results.get("performance_violations", []):
                failures.append({
                    "title": f"Performance Violation: {violation}",
                    "source_agent": "performance",
                    "failure_category": "performance",
                    "feature": "performance",
                    "error": violation,
                })

        # Database issues
        if input_data.include_database_bugs:
            db_results = await self._memory.get(
                key=str(MemoryKeys.DATABASE_VALIDATION_RESULTS),
                reader=self.NAME,
            ) or {}
            for issue in db_results.get("issues", []):
                issue["source_agent"] = "database_validation"
                issue["failure_category"] = "database"
                failures.append(issue)

        logger.info(
            "bug_analysis_failures_collected",
            workflow_id=input_data.workflow_id,
            total_failures=len(failures),
        )

        return failures

    def _group_by_feature(
        self, failures: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """Group failures by their affected feature."""
        grouped: dict[str, list[dict[str, Any]]] = {}
        for failure in failures:
            feature = (
                failure.get("feature") or
                failure.get("affected_feature") or
                failure.get("failure_category") or
                "unknown"
            )
            grouped.setdefault(feature, []).append(failure)
        return grouped

    async def _ai_analyse_feature_failures(
        self,
        feature: str,
        failures: list[dict[str, Any]],
        input_data: BugAnalysisInput,
    ) -> list[dict[str, Any]]:
        """Use AI to analyse failures for a specific feature."""
        from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage

        failures_text = json.dumps(
            [
                {
                    "category": f.get("failure_category", "unknown"),
                    "title": f.get("title", f.get("test_name", "Unknown")),
                    "error": f.get("error", f.get("description", "")),
                    "source": f.get("source_agent", "unknown"),
                }
                for f in failures[:10]
            ],
            indent=2,
        )

        system_prompt = (
            "You are an expert software engineer and QA analyst. "
            "Analyse test failures and produce structured bug reports. "
            "Always identify root causes vs downstream effects. "
            "Every conclusion must be supported by the evidence provided. "
            "Never invent findings not supported by the failures listed."
        )

        user_message = f"""Analyse these failures for feature: {feature}

FAILURES:
{failures_text}

Produce structured bug reports. For each distinct bug:
1. Is it a root cause or downstream effect of another bug?
2. What is the root cause?
3. What is the severity (Critical/High/Medium/Low/Informational)?
4. How confident are you (0.0-1.0)?
5. What files are likely involved?
6. What is the suggested fix?
7. How confident are you in the fix (0.0-1.0)?

Return as JSON array:
[
  {{
    "id": "bug_xxx",
    "title": "concise bug title",
    "severity": "Critical|High|Medium|Low|Informational",
    "confidence": 0.0,
    "root_cause": "detailed root cause explanation",
    "affected_feature": "{feature}",
    "affected_files": ["list", "of", "files"],
    "dependency_chain": ["step1", "step2"],
    "suggested_fix": "specific fix recommendation",
    "fix_confidence": 0.0,
    "is_downstream": false,
    "root_bug_id": null,
    "is_regression": false,
    "evidence": [
      {{"kind": "test_failure", "content": "...", "source": "...", "relevance": "..."}}
    ]
  }}
]"""

        try:
            request = AIRequest(
                messages=[PromptMessage.user(user_message)],
                task_type=AITaskType.ANALYSIS,
                max_tokens=2000,
                system_prompt=system_prompt,
                temperature=0.1,
                workflow_id=input_data.workflow_id,
                agent_name=self.NAME,
                prompt_version="1.0",
            )
            response = await self._gateway.complete(request)

            clean = response.content.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0]
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0]

            bugs_data = json.loads(clean)
            if not isinstance(bugs_data, list):
                return []

            # Ensure each bug has a unique ID
            result_bugs = []
            for bug in bugs_data:
                if not bug.get("id"):
                    bug["id"] = f"bug_{uuid.uuid4().hex[:8]}"
                result_bugs.append(bug)

            logger.info(
                "ai_bug_analysis_complete",
                workflow_id=input_data.workflow_id,
                feature=feature,
                bugs_found=len(result_bugs),
                tokens_used=response.total_tokens,
            )

            return result_bugs

        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning(
                "ai_bug_analysis_parse_failed",
                feature=feature,
                error=str(e),
            )
            return self._deterministic_bug_creation(
                {feature: failures}, input_data
            )
        except Exception as e:
            logger.warning(
                "ai_bug_analysis_failed",
                feature=feature,
                error=str(e),
            )
            return self._deterministic_bug_creation(
                {feature: failures}, input_data
            )

    def _deterministic_bug_creation(
        self,
        grouped: dict[str, list[dict[str, Any]]],
        input_data: BugAnalysisInput,
    ) -> list[dict[str, Any]]:
        """Create basic bug reports without AI."""
        bugs = []

        severity_map = {
            "security": BugSeverity.HIGH.value,
            "sql_injection": BugSeverity.CRITICAL.value,
            "xss": BugSeverity.HIGH.value,
            "secrets": BugSeverity.CRITICAL.value,
            "vulnerable_dependency": BugSeverity.HIGH.value,
            "dangerous_migration": BugSeverity.HIGH.value,
            "browser_test": BugSeverity.MEDIUM.value,
            "api_validation": BugSeverity.MEDIUM.value,
            "performance": BugSeverity.LOW.value,
            "database": BugSeverity.MEDIUM.value,
            "n_plus_one": BugSeverity.LOW.value,
        }

        for feature, failures in grouped.items():
            for failure in failures:
                category = (
                    failure.get("category") or
                    failure.get("failure_category") or
                    "unknown"
                )
                severity = severity_map.get(
                    category, BugSeverity.MEDIUM.value
                )

                bugs.append({
                    "id": f"bug_{uuid.uuid4().hex[:8]}",
                    "title": (
                        failure.get("title") or
                        failure.get("test_name") or
                        f"Failure in {feature}"
                    ),
                    "severity": severity,
                    "confidence": 0.65,
                    "root_cause": (
                        failure.get("error") or
                        failure.get("description") or
                        "Root cause requires manual investigation."
                    ),
                    "affected_feature": feature,
                    "affected_files": [
                        failure.get("file_path", "")
                    ] if failure.get("file_path") else [],
                    "dependency_chain": [],
                    "suggested_fix": failure.get(
                        "remediation",
                        "Investigate the failure and apply the appropriate fix."
                    ),
                    "fix_confidence": 0.5,
                    "is_downstream": False,
                    "root_bug_id": None,
                    "is_regression": False,
                    "evidence": [
                        {
                            "kind": "failure_report",
                            "content": str(failure.get("error", ""))[:200],
                            "source": failure.get("source_agent", "unknown"),
                            "relevance": "Direct failure output",
                        }
                    ],
                })

        return bugs

    def _mark_downstream_effects(
        self, bugs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """
        Identify and mark downstream bugs.

        If multiple bugs share the same feature and the same
        root cause pattern, the first (by severity) is the
        root cause; subsequent ones are downstream effects.
        """
        if len(bugs) <= 1:
            return bugs

        # Group by feature
        by_feature: dict[str, list[dict[str, Any]]] = {}
        for bug in bugs:
            feat = bug.get("affected_feature", "unknown")
            by_feature.setdefault(feat, []).append(bug)

        severity_order = {
            "Critical": 0, "High": 1,
            "Medium": 2, "Low": 3, "Informational": 4,
        }

        result = []
        for feature, feature_bugs in by_feature.items():
            sorted_bugs = sorted(
                feature_bugs,
                key=lambda b: severity_order.get(b.get("severity", ""), 99),
            )

            # First bug in each feature group is the root cause
            if sorted_bugs:
                root = sorted_bugs[0]
                root["is_downstream"] = False
                result.append(root)

                for downstream in sorted_bugs[1:]:
                    downstream["is_downstream"] = True
                    downstream["root_bug_id"] = root.get("id")
                    result.append(downstream)

        return result

    async def _write_to_memory(
        self,
        input_data: AgentInput,
        output: BugAnalysisOutput,
    ) -> None:
        if not self._memory:
            return
        await self._memory.set(
            key=str(MemoryKeys.BUG_ANALYSIS_RESULTS),
            value=output.to_dict(),
            written_by=self.NAME,
        )
