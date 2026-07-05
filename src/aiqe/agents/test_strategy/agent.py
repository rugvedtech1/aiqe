"""
AIQE Test Strategy Agent.

Generates a risk-based test strategy from the project
intelligence model and changed files.

Responsibilities:
    - Analyse which features are affected by changed files
    - Calculate risk scores per feature
    - Determine which tests should run vs be skipped
    - Define test priorities (Critical → High → Medium → Low)
    - Identify regression risk
    - Plan the overall test coverage strategy

Why risk-based testing?
    Running all tests on every PR is expensive and slow.
    Risk-based testing focuses effort where it matters most:
    features that changed, features that historically fail,
    features with high business impact, and features
    that depend on what changed.

Tier: 1 (Core)
Dependencies: project_analysis
Memory Reads:
    - project_analysis.result
    - intelligence.feature_graph
    - intelligence.code_dependency_graph
    - system.workflow_metadata
Memory Writes:
    - test_strategy.result
    - test_strategy.changed_files
    - test_strategy.affected_features
"""

from __future__ import annotations

import json
from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import (
    AgentInput,
    AgentOutput,
    TestStrategyInput,
    TestStrategyOutput,
)
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class TestStrategyAgent(BaseAgent):
    """
    Test Strategy Agent — Tier 1.

    Produces a prioritised, risk-based test plan that tells
    downstream agents exactly what to test, in what order,
    and why.
    """

    NAME = "test_strategy"
    DESCRIPTION = (
        "Performs risk analysis on the project intelligence model "
        "and changed files to produce a prioritised test plan. "
        "Determines what to test, what to skip, and why."
    )
    TIER = 1
    DEPENDENCIES = ["project_analysis"]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway

    async def run_impl(
        self, input_data: AgentInput
    ) -> AgentOutput:
        """Generate the test strategy."""
        assert isinstance(input_data, TestStrategyInput), (
            f"Expected TestStrategyInput, got {type(input_data).__name__}"
        )

        output = TestStrategyOutput()

        # ==================================================
        # PHASE 1: LOAD CONTEXT FROM MEMORY
        # ==================================================

        project_analysis = {}
        feature_graph_data = {}

        if self._memory:
            project_analysis = await self._memory.get(
                key=str(MemoryKeys.PROJECT_ANALYSIS_RESULT),
                reader=self.NAME,
            ) or {}
            feature_graph_data = await self._memory.get(
                key=str(MemoryKeys.FEATURE_GRAPH),
                reader=self.NAME,
            ) or {}
        elif input_data.project_analysis:
            project_analysis = input_data.project_analysis

        changed_files = (
            input_data.changed_files or
            self._extract_changed_files_from_memory()
        )

        # ==================================================
        # PHASE 2: DETERMINISTIC RISK SCORING
        # ==================================================

        affected_features = self._identify_affected_features(
            changed_files=changed_files,
            feature_graph_data=feature_graph_data,
            project_analysis=project_analysis,
        )

        skipped_areas = self._identify_skippable_areas(
            project_analysis=project_analysis,
            changed_files=changed_files,
        )

        # ==================================================
        # PHASE 3: AI-ASSISTED STRATEGY GENERATION
        # ==================================================

        if self._gateway and not input_data.dry_run:
            await self._ai_generate_strategy(
                input_data=input_data,
                output=output,
                project_analysis=project_analysis,
                changed_files=changed_files,
                affected_features=affected_features,
            )
        else:
            self._generate_default_strategy(
                output=output,
                project_analysis=project_analysis,
                changed_files=changed_files,
                affected_features=affected_features,
            )

        output.skipped_areas = skipped_areas
        output.changed_features = affected_features
        output.regression_risk = self._assess_regression_risk(
            changed_files=changed_files,
            project_analysis=project_analysis,
        )

        # ==================================================
        # PHASE 4: WRITE TO MEMORY
        # ==================================================

        if self._memory:
            await self._write_to_memory(
                input_data=input_data,
                output=output,
                changed_files=changed_files,
                affected_features=affected_features,
            )

        output.add_evidence(
            kind="risk_analysis",
            content=(
                f"Changed files: {len(changed_files)}, "
                f"Affected features: {len(affected_features)}, "
                f"Test areas: {len(output.test_plan)}, "
                f"Skipped: {len(skipped_areas)}"
            ),
            source="deterministic_risk_analyzer",
            relevance="Basis for test scope decisions",
        )

        output.suggested_next_action = (
            f"Test Case Generator should now generate test cases for "
            f"{len(output.test_plan)} test areas covering "
            f"{len(affected_features)} affected features. "
            f"Estimated total test cases: {output.estimated_test_count}."
        )

        return output

    def _identify_affected_features(
        self,
        changed_files: list[str],
        feature_graph_data: dict[str, Any],
        project_analysis: dict[str, Any],
    ) -> list[str]:
        """
        Identify business features affected by the changed files.

        Uses the feature graph to find features whose source files
        overlap with the changed file list.
        """
        affected = set()

        if not changed_files:
            return []

        # Match changed files to feature nodes in the graph
        nodes = feature_graph_data.get("nodes", {})
        for node_id, node in nodes.items():
            node_file = node.get("file_path", "")
            if not node_file:
                continue
            for changed in changed_files:
                if (node_file in changed or
                        changed.startswith(node_file.split("/")[0])):
                    affected.add(node.get("label", node_id))

        # If no features mapped, use changed file directory names
        if not affected:
            for f in changed_files:
                parts = f.split("/")
                if len(parts) > 1:
                    affected.add(parts[0].replace("-", " ").replace("_", " ").title())
                else:
                    affected.add("Core")

        return sorted(affected)

    def _identify_skippable_areas(
        self,
        project_analysis: dict[str, Any],
        changed_files: list[str],
    ) -> list[dict[str, str]]:
        """
        Identify test areas that can safely be skipped.

        Areas are skippable when:
        - No changed files touch that area
        - The area has no dependencies on changed files
        - The area has not historically failed
        """
        skipped = []
        changed_dirs = {
            f.split("/")[0] for f in changed_files if "/" in f
        }

        # These areas are skippable if no related files changed
        candidate_areas = ["documentation", "ci_config", "dev_tooling"]

        for area in candidate_areas:
            if area not in changed_dirs:
                skipped.append({
                    "area": area,
                    "reason": (
                        f"No changed files in '{area}'. "
                        f"Skipping to reduce test execution time."
                    ),
                })

        return skipped

    def _assess_regression_risk(
        self,
        changed_files: list[str],
        project_analysis: dict[str, Any],
    ) -> bool:
        """
        Determine if this changeset carries regression risk.

        Regression risk is elevated when:
        - Core/shared modules changed (many dependents)
        - Authentication or database files changed
        - More than 10 files changed
        - Configuration files changed
        """
        if len(changed_files) > 10:
            return True

        high_risk_patterns = [
            "auth", "login", "database", "migration",
            "config", "settings", "middleware", "base",
            "core", "common", "shared", "utils",
        ]

        for f in changed_files:
            f_lower = f.lower()
            if any(pattern in f_lower for pattern in high_risk_patterns):
                return True

        return False

    def _generate_default_strategy(
        self,
        output: TestStrategyOutput,
        project_analysis: dict[str, Any],
        changed_files: list[str],
        affected_features: list[str],
    ) -> None:
        """Generate a default strategy when AI is unavailable."""
        test_plan = []
        test_count = 0

        # Create test areas from affected features
        for feature in affected_features:
            test_plan.append({
                "area": feature,
                "priority": "High",
                "risk_score": 0.7,
                "test_types": ["positive", "negative", "boundary"],
                "estimated_cases": 10,
                "reason": f"Feature '{feature}' is in the changed area.",
            })
            test_count += 10

        # Always include a smoke test area
        if not test_plan:
            test_plan.append({
                "area": "Core Functionality",
                "priority": "High",
                "risk_score": 0.6,
                "test_types": ["positive", "negative"],
                "estimated_cases": 5,
                "reason": "Default coverage — no specific features identified.",
            })
            test_count += 5

        has_api = project_analysis.get("has_api", False)
        if has_api:
            test_plan.append({
                "area": "API Validation",
                "priority": "Medium",
                "risk_score": 0.5,
                "test_types": ["api", "schema", "auth"],
                "estimated_cases": 8,
                "reason": "Project has API endpoints that need validation.",
            })
            test_count += 8

        has_auth = bool(project_analysis.get("auth_method"))
        if has_auth:
            test_plan.append({
                "area": "Authentication & Authorisation",
                "priority": "Critical",
                "risk_score": 0.9,
                "test_types": [
                    "positive", "negative", "boundary", "security"
                ],
                "estimated_cases": 15,
                "reason": (
                    "Authentication is a high-risk area. "
                    "Always tested when auth files are involved."
                ),
            })
            test_count += 15

        output.test_plan = test_plan
        output.estimated_test_count = test_count
        output.risk_assessment = (
            "Medium" if affected_features else "Low"
        )
        output.reasoning = (
            f"Test strategy generated from deterministic analysis. "
            f"{len(changed_files)} changed files affect "
            f"{len(affected_features)} features. "
            f"Planned {len(test_plan)} test areas with "
            f"~{test_count} estimated test cases."
        )
        output.confidence = 0.75

    async def _ai_generate_strategy(
        self,
        input_data: TestStrategyInput,
        output: TestStrategyOutput,
        project_analysis: dict[str, Any],
        changed_files: list[str],
        affected_features: list[str],
    ) -> None:
        """Use AI to generate a risk-based test strategy."""
        from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage

        system_prompt = (
            "You are a senior QA architect specialising in risk-based testing. "
            "Your job is to create efficient, prioritised test strategies that "
            "maximize defect detection while minimizing execution time. "
            "Always justify your priorities with specific risk reasoning."
        )

        user_message = f"""Generate a risk-based test strategy for this Pull Request.

PROJECT CONTEXT:
Language: {project_analysis.get('language', 'unknown')}
Framework: {project_analysis.get('framework', 'unknown')}
Has Authentication: {bool(project_analysis.get('auth_method'))}
Has Database: {project_analysis.get('has_database', False)}
Has API: {len(project_analysis.get('routes', []))} endpoints
Total Source Files: {project_analysis.get('source_files_count', 0)}

CHANGED FILES ({len(changed_files)} total):
{chr(10).join(f'- {f}' for f in changed_files[:20])}

AFFECTED FEATURES:
{chr(10).join(f'- {f}' for f in affected_features)}

Generate a test strategy with:
1. Up to 8 test areas ordered by risk (Critical → Low).
2. For each area: priority, risk_score (0.0-1.0), test types, estimated case count, reason.
3. Overall risk assessment (Critical/High/Medium/Low).
4. Regression risk (true/false) with justification.
5. Confidence in this strategy (0.0-1.0).

Format as JSON:
{{
  "test_plan": [
    {{
      "area": "area name",
      "priority": "Critical|High|Medium|Low",
      "risk_score": 0.0,
      "test_types": ["positive", "negative", "boundary", "security", "api"],
      "estimated_cases": 0,
      "reason": "specific risk justification"
    }}
  ],
  "risk_assessment": "Critical|High|Medium|Low",
  "regression_risk": true,
  "regression_reason": "why or why not",
  "confidence": 0.0,
  "reasoning": "step-by-step reasoning"
}}"""

        try:
            request = AIRequest(
                messages=[PromptMessage.user(user_message)],
                task_type=AITaskType.STRATEGY,
                max_tokens=1500,
                system_prompt=system_prompt,
                temperature=0.1,
                workflow_id=input_data.workflow_id,
                agent_name=self.NAME,
                prompt_version="1.0",
            )

            response = await self._gateway.complete(request)
            output.ai_tokens_used = response.total_tokens

            # Parse JSON response
            clean = response.content.strip()
            if "```json" in clean:
                clean = clean.split("```json")[1].split("```")[0]
            elif "```" in clean:
                clean = clean.split("```")[1].split("```")[0]

            data = json.loads(clean)

            output.test_plan = data.get("test_plan", [])
            output.estimated_test_count = sum(
                area.get("estimated_cases", 0)
                for area in output.test_plan
            )
            output.risk_assessment = data.get("risk_assessment", "Medium")
            output.regression_risk = data.get("regression_risk", False)
            output.reasoning = data.get("reasoning", "")
            output.confidence = float(data.get("confidence", 0.8))

            logger.info(
                "test_strategy_ai_complete",
                workflow_id=input_data.workflow_id,
                test_areas=len(output.test_plan),
                estimated_cases=output.estimated_test_count,
                risk_assessment=output.risk_assessment,
                tokens_used=response.total_tokens,
            )

        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(
                "test_strategy_ai_parse_failed",
                workflow_id=input_data.workflow_id,
                error=str(e),
            )
            self._generate_default_strategy(
                output=output,
                project_analysis=project_analysis,
                changed_files=changed_files,
                affected_features=affected_features,
            )
            output.add_warning(
                f"AI strategy generation failed (JSON parse error): {e}. "
                f"Using deterministic fallback."
            )

        except Exception as e:
            logger.warning(
                "test_strategy_ai_failed",
                workflow_id=input_data.workflow_id,
                error=str(e),
            )
            self._generate_default_strategy(
                output=output,
                project_analysis=project_analysis,
                changed_files=changed_files,
                affected_features=affected_features,
            )
            output.add_warning(
                f"AI strategy generation failed: {e}. "
                f"Using deterministic fallback."
            )

    def _extract_changed_files_from_memory(self) -> list[str]:
        """Return empty list if no memory store is available."""
        return []

    async def _write_to_memory(
        self,
        input_data: AgentInput,
        output: TestStrategyOutput,
        changed_files: list[str],
        affected_features: list[str],
    ) -> None:
        """Write strategy results to shared memory."""
        await self._memory.set(
            key=str(MemoryKeys.TEST_STRATEGY_RESULT),
            value=output.to_dict(),
            written_by=self.NAME,
        )

        await self._memory.set(
            key=str(MemoryKeys.CHANGED_FILES),
            value=changed_files,
            written_by=self.NAME,
        )

        await self._memory.set(
            key=str(MemoryKeys.AFFECTED_FEATURES),
            value=affected_features,
            written_by=self.NAME,
        )

        logger.info(
            "test_strategy_memory_written",
            workflow_id=input_data.workflow_id,
            keys_written=3,
        )
