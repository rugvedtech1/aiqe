"""
AIQE Test Case Generator Agent.

Generates comprehensive, typed test cases from the test strategy.

Test case types generated:
    Positive:   Valid inputs, expected happy-path behaviour
    Negative:   Invalid inputs, error handling, boundary violations
    Boundary:   Edge values (min, max, empty, null, overflow)
    Edge:       Unusual combinations, concurrent access, timing
    Exploratory: AI-discovered scenarios based on business context

Each test case includes:
    - Unique ID
    - Human-readable title
    - Test type (positive/negative/boundary/edge/exploratory)
    - Feature being tested
    - Preconditions
    - Test steps
    - Expected result
    - Priority
    - Automation hints (can this be automated? how?)

Tier: 1 (Core)
Dependencies: test_strategy, project_analysis
Memory Reads:
    - test_strategy.result
    - project_analysis.result
    - intelligence.feature_graph
Memory Writes:
    - test_case_generator.test_cases
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
    TestCaseGeneratorInput,
)
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class TestCase:
    """A single generated test case."""
    id: str = field(default_factory=lambda: f"tc_{uuid.uuid4().hex[:8]}")
    title: str = ""
    test_type: str = "positive"
    feature: str = ""
    area: str = ""
    priority: str = "Medium"
    preconditions: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    expected_result: str = ""
    automation_hint: str = ""
    is_automatable: bool = True
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "test_type": self.test_type,
            "feature": self.feature,
            "area": self.area,
            "priority": self.priority,
            "preconditions": self.preconditions,
            "steps": self.steps,
            "expected_result": self.expected_result,
            "automation_hint": self.automation_hint,
            "is_automatable": self.is_automatable,
            "tags": self.tags,
        }


class TestCaseGeneratorOutput(AgentOutput):
    """Output from the Test Case Generator Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.test_cases: list[dict[str, Any]] = []
        self.total_generated: int = 0
        self.by_type: dict[str, int] = {}
        self.by_priority: dict[str, int] = {}
        self.by_feature: dict[str, int] = {}
        self.automation_coverage: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "test_cases": self.test_cases,
            "total_generated": self.total_generated,
            "by_type": self.by_type,
            "by_priority": self.by_priority,
            "by_feature": self.by_feature,
            "automation_coverage": self.automation_coverage,
        }


class TestCaseGeneratorAgent(BaseAgent):
    """
    Test Case Generator Agent — Tier 1.

    Generates comprehensive test cases for each area in the
    test plan. Uses AI for business-context-aware generation
    with deterministic fallbacks for common patterns.
    """

    NAME = "test_case_generator"
    DESCRIPTION = (
        "Generates positive, negative, boundary, edge, and "
        "exploratory test cases for each test area in the strategy."
    )
    TIER = 1
    DEPENDENCIES = ["test_strategy", "project_analysis"]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway

    async def run_impl(
        self, input_data: AgentInput
    ) -> TestCaseGeneratorOutput:
        """Generate test cases from the test strategy."""
        assert isinstance(input_data, TestCaseGeneratorInput), (
            f"Expected TestCaseGeneratorInput, "
            f"got {type(input_data).__name__}"
        )

        output = TestCaseGeneratorOutput()

        # ==================================================
        # PHASE 1: LOAD CONTEXT
        # ==================================================

        test_strategy = {}
        project_analysis = {}

        if self._memory:
            test_strategy = await self._memory.get(
                key=str(MemoryKeys.TEST_STRATEGY_RESULT),
                reader=self.NAME,
            ) or {}
            project_analysis = await self._memory.get(
                key=str(MemoryKeys.PROJECT_ANALYSIS_RESULT),
                reader=self.NAME,
            ) or {}
        else:
            test_strategy = input_data.test_strategy
            project_analysis = input_data.project_analysis

        test_plan = test_strategy.get("test_plan", [])
        max_per_feature = input_data.max_cases_per_feature

        if not test_plan:
            output.reasoning = (
                "No test plan found. Generating default test cases."
            )
            test_plan = [{
                "area": "Core",
                "priority": "High",
                "risk_score": 0.5,
                "test_types": ["positive", "negative"],
                "estimated_cases": 5,
                "reason": "Default coverage",
            }]

        # ==================================================
        # PHASE 2: GENERATE TEST CASES PER AREA
        # ==================================================

        all_test_cases: list[TestCase] = []

        for area in test_plan:
            area_cases = await self._generate_for_area(
                area=area,
                project_analysis=project_analysis,
                input_data=input_data,
                max_cases=max_per_feature,
            )
            all_test_cases.extend(area_cases)

        # ==================================================
        # PHASE 3: COMPUTE STATISTICS
        # ==================================================

        output.test_cases = [tc.to_dict() for tc in all_test_cases]
        output.total_generated = len(all_test_cases)

        # By type
        for tc in all_test_cases:
            t = tc.test_type
            output.by_type[t] = output.by_type.get(t, 0) + 1

        # By priority
        for tc in all_test_cases:
            p = tc.priority
            output.by_priority[p] = output.by_priority.get(p, 0) + 1

        # By feature
        for tc in all_test_cases:
            f = tc.feature or tc.area
            output.by_feature[f] = output.by_feature.get(f, 0) + 1

        # Automation coverage
        automatable = sum(1 for tc in all_test_cases if tc.is_automatable)
        output.automation_coverage = (
            automatable / len(all_test_cases)
            if all_test_cases else 0.0
        )

        output.reasoning = (
            f"Generated {output.total_generated} test cases "
            f"across {len(test_plan)} test areas. "
            f"Types: {output.by_type}. "
            f"Automation coverage: {output.automation_coverage:.0%}."
        )
        output.confidence = 0.85

        # ==================================================
        # PHASE 4: WRITE TO MEMORY
        # ==================================================

        if self._memory:
            await self._memory.set(
                key=str(MemoryKeys.GENERATED_TEST_CASES),
                value=output.test_cases,
                written_by=self.NAME,
            )

        output.add_evidence(
            kind="test_generation_summary",
            content=(
                f"Generated {output.total_generated} test cases: "
                f"{output.by_type}"
            ),
            source="test_case_generator",
            relevance="Test coverage summary for the test plan",
        )

        output.suggested_next_action = (
            f"Automation Generator should now convert the "
            f"{output.total_generated} test cases into executable "
            f"Playwright and API test scripts. "
            f"{automatable} cases are marked as automatable."
        )

        logger.info(
            "test_cases_generated",
            workflow_id=input_data.workflow_id,
            total=output.total_generated,
            by_type=output.by_type,
            automation_coverage=output.automation_coverage,
        )

        return output

    async def _generate_for_area(
        self,
        area: dict[str, Any],
        project_analysis: dict[str, Any],
        input_data: TestCaseGeneratorInput,
        max_cases: int,
    ) -> list[TestCase]:
        """Generate test cases for a single test area."""
        area_name = area.get("area", "Unknown")
        priority = area.get("priority", "Medium")
        test_types = area.get("test_types", ["positive", "negative"])
        risk_score = area.get("risk_score", 0.5)
        reason = area.get("reason", "")

        if self._gateway and not input_data.dry_run:
            cases = await self._ai_generate_cases(
                area_name=area_name,
                priority=priority,
                test_types=test_types,
                risk_score=risk_score,
                reason=reason,
                project_analysis=project_analysis,
                input_data=input_data,
                max_cases=max_cases,
            )
            if cases:
                return cases

        # Deterministic fallback
        return self._deterministic_cases(
            area_name=area_name,
            priority=priority,
            test_types=test_types,
            input_data=input_data,
            max_cases=max_cases,
        )

    async def _ai_generate_cases(
        self,
        area_name: str,
        priority: str,
        test_types: list[str],
        risk_score: float,
        reason: str,
        project_analysis: dict[str, Any],
        input_data: TestCaseGeneratorInput,
        max_cases: int,
    ) -> list[TestCase]:
        """Use AI to generate context-aware test cases."""
        from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage

        # Calculate how many of each type to generate
        cases_per_type = max(1, max_cases // max(len(test_types), 1))

        types_to_generate = {
            t: cases_per_type for t in test_types
            if t in {"positive", "negative", "boundary", "edge", "exploratory"}
        }
        if not input_data.include_negative_cases:
            types_to_generate.pop("negative", None)
        if not input_data.include_boundary_cases:
            types_to_generate.pop("boundary", None)
        if not input_data.include_exploratory_cases:
            types_to_generate.pop("exploratory", None)

        system_prompt = (
            "You are a senior QA engineer who writes comprehensive, "
            "executable test cases. Each test case should be specific, "
            "actionable, and cover a distinct scenario. "
            "Focus on finding real bugs, not obvious happy paths."
        )

        user_message = f"""Generate test cases for this test area.

TEST AREA: {area_name}
PRIORITY: {priority}
RISK SCORE: {risk_score:.0%}
RISK REASON: {reason}
PROJECT: {project_analysis.get('language', 'unknown')}/{project_analysis.get('framework', 'unknown')}
HAS AUTH: {bool(project_analysis.get('auth_method'))}
HAS DATABASE: {project_analysis.get('has_database', False)}

GENERATE THESE TYPES:
{json.dumps(types_to_generate, indent=2)}

For each test case provide:
- title: specific, descriptive test name
- test_type: positive|negative|boundary|edge|exploratory
- priority: Critical|High|Medium|Low
- preconditions: list of setup requirements
- steps: list of specific test steps
- expected_result: exact expected outcome
- automation_hint: how to automate this (e.g. "Playwright form fill", "API POST request")
- is_automatable: true|false

Return as JSON array:
[
  {{
    "title": "...",
    "test_type": "...",
    "priority": "...",
    "preconditions": ["..."],
    "steps": ["..."],
    "expected_result": "...",
    "automation_hint": "...",
    "is_automatable": true
  }}
]"""

        try:
            request = AIRequest(
                messages=[PromptMessage.user(user_message)],
                task_type=AITaskType.GENERATION,
                max_tokens=2000,
                system_prompt=system_prompt,
                temperature=0.2,
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

            cases_data = json.loads(clean)
            if not isinstance(cases_data, list):
                return []

            test_cases = []
            for case_data in cases_data[:max_cases]:
                tc = TestCase(
                    title=case_data.get("title", "Untitled test"),
                    test_type=case_data.get("test_type", "positive"),
                    feature=area_name,
                    area=area_name,
                    priority=case_data.get("priority", priority),
                    preconditions=case_data.get("preconditions", []),
                    steps=case_data.get("steps", ["Execute test"]),
                    expected_result=case_data.get("expected_result", ""),
                    automation_hint=case_data.get("automation_hint", ""),
                    is_automatable=case_data.get("is_automatable", True),
                    tags=[area_name.lower(), case_data.get("test_type", "")],
                )
                test_cases.append(tc)

            return test_cases

        except Exception as e:
            logger.warning(
                "ai_test_case_generation_failed",
                area=area_name,
                error=str(e),
                workflow_id=input_data.workflow_id,
            )
            return []

    def _deterministic_cases(
        self,
        area_name: str,
        priority: str,
        test_types: list[str],
        input_data: TestCaseGeneratorInput,
        max_cases: int,
    ) -> list[TestCase]:
        """
        Generate deterministic test case templates.

        Used as fallback when AI is unavailable.
        These are generic templates — AI generates
        context-specific cases when available.
        """
        cases = []
        area_slug = area_name.lower().replace(" ", "_")

        type_templates = {
            "positive": [
                (
                    f"Verify {area_name} works with valid input",
                    ["System is running", "User is authenticated"],
                    [
                        "Prepare valid input data",
                        f"Execute {area_name} operation",
                        "Verify successful response",
                        "Verify data is persisted correctly",
                    ],
                    "Operation completes successfully with expected output",
                    f"Playwright or API test for {area_name}",
                    True,
                ),
                (
                    f"Verify {area_name} returns correct data format",
                    ["System is running"],
                    [
                        "Send valid request",
                        "Verify response schema",
                        "Verify response content type",
                    ],
                    "Response matches expected schema",
                    "API schema validation test",
                    True,
                ),
            ],
            "negative": [
                (
                    f"Verify {area_name} rejects invalid input",
                    ["System is running"],
                    [
                        "Prepare invalid input data",
                        f"Attempt {area_name} operation",
                        "Verify error response",
                        "Verify appropriate error message",
                    ],
                    "Error returned with appropriate status code and message",
                    "API negative test with invalid payload",
                    True,
                ),
            ],
            "boundary": [
                (
                    f"Verify {area_name} handles empty input",
                    ["System is running"],
                    [
                        "Prepare empty/null input",
                        f"Attempt {area_name} operation",
                        "Verify response",
                    ],
                    "Appropriate error or default handling for empty input",
                    "Boundary value test",
                    True,
                ),
            ],
        }

        count = 0
        for test_type in test_types:
            if count >= max_cases:
                break
            if test_type not in type_templates:
                continue

            templates = type_templates[test_type]
            for (title, preconds, steps, expected, hint, auto) in templates:
                if count >= max_cases:
                    break
                cases.append(TestCase(
                    title=title,
                    test_type=test_type,
                    feature=area_name,
                    area=area_name,
                    priority=priority,
                    preconditions=preconds,
                    steps=steps,
                    expected_result=expected,
                    automation_hint=hint,
                    is_automatable=auto,
                    tags=[area_slug, test_type],
                ))
                count += 1

        return cases
