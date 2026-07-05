"""
AIQE Automation Generator Agent.

Converts typed test cases (from Test Case Generator) into
executable Playwright scripts and API test scripts.

Responsibilities:
    - Read generated test cases from shared memory
    - Group test cases by type (browser vs API vs database)
    - Generate Playwright Python scripts for browser tests
    - Generate httpx-based API test scripts
    - Generate pytest-compatible test files
    - Write generated scripts to workflow workspace

Why generate code rather than execute directly?
    Generated scripts are:
    1. Auditable — engineers can inspect what AIQE will run
    2. Reusable — engineers can add to their test suite
    3. Debuggable — failures show specific line numbers
    4. Portable — run outside AIQE with standard tools
    5. Compliant with ADR-009 — no auto-modification of
       production code, but test scripts are artifacts

Tier: 2 (Execution)
Dependencies: test_case_generator, project_analysis
Memory Reads:
    - test_case_generator.test_cases
    - project_analysis.result
Memory Writes:
    - automation_generator.playwright_scripts
    - automation_generator.api_tests
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class GeneratedScript:
    """A single generated test script."""
    filename: str
    content: str
    script_type: str  # playwright | api | database
    test_count: int
    feature: str = ""
    language: str = "python"

    def to_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "script_type": self.script_type,
            "test_count": self.test_count,
            "feature": self.feature,
            "language": self.language,
            "content_length": len(self.content),
        }


class AutomationGeneratorOutput(AgentOutput):
    """Output from the Automation Generator Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.playwright_scripts: list[dict[str, Any]] = []
        self.api_test_scripts: list[dict[str, Any]] = []
        self.total_scripts_generated: int = 0
        self.total_test_functions: int = 0
        self.workspace_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "playwright_scripts": self.playwright_scripts,
            "api_test_scripts": self.api_test_scripts,
            "total_scripts_generated": self.total_scripts_generated,
            "total_test_functions": self.total_test_functions,
            "workspace_path": self.workspace_path,
        }


class AutomationGeneratorInput(AgentInput):
    """Input for the Automation Generator Agent."""
    base_url: str = "http://localhost:8000"
    browser_type: str = "chromium"
    headless: bool = True
    generate_playwright: bool = True
    generate_api_tests: bool = True


class AutomationGeneratorAgent(BaseAgent):
    """
    Automation Generator Agent — Tier 2.

    Takes typed test cases and generates executable
    Playwright and API test scripts.
    """

    NAME = "automation_generator"
    DESCRIPTION = (
        "Converts test cases into executable Playwright browser "
        "scripts and httpx-based API test scripts."
    )
    TIER = 2
    DEPENDENCIES = ["test_case_generator", "project_analysis"]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway

    async def run_impl(self, input_data: AgentInput) -> AutomationGeneratorOutput:
        """Generate automation scripts from test cases."""
        assert isinstance(input_data, AutomationGeneratorInput), (
            f"Expected AutomationGeneratorInput, got {type(input_data).__name__}"
        )

        output = AutomationGeneratorOutput()

        # ==================================================
        # PHASE 1: LOAD TEST CASES FROM MEMORY
        # ==================================================

        test_cases: list[dict[str, Any]] = []
        project_analysis: dict[str, Any] = {}

        if self._memory:
            test_cases = await self._memory.get(
                key=str(MemoryKeys.GENERATED_TEST_CASES),
                reader=self.NAME,
            ) or []
            project_analysis = await self._memory.get(
                key=str(MemoryKeys.PROJECT_ANALYSIS_RESULT),
                reader=self.NAME,
            ) or {}

        if not test_cases:
            output.add_warning(
                "No test cases found in memory. "
                "Ensure Test Case Generator ran before this agent."
            )
            output.reasoning = "No test cases available to generate scripts from."
            output.confidence = 0.0
            return output

        # ==================================================
        # PHASE 2: CLASSIFY TEST CASES BY TYPE
        # ==================================================

        browser_cases = []
        api_cases = []

        for tc in test_cases:
            hint = tc.get("automation_hint", "").lower()
            test_type = tc.get("test_type", "")

            if any(word in hint for word in [
                "playwright", "browser", "click", "form", "navigate",
                "screenshot", "e2e", "ui",
            ]):
                browser_cases.append(tc)
            elif any(word in hint for word in [
                "api", "http", "request", "endpoint", "rest",
                "graphql", "post", "get", "schema",
            ]):
                api_cases.append(tc)
            else:
                # Default: browser tests for UI-heavy features,
                # API tests for backend features
                framework = project_analysis.get("framework", "")
                if framework in {"fastapi", "django", "flask", "express"}:
                    api_cases.append(tc)
                else:
                    browser_cases.append(tc)

        logger.info(
            "test_cases_classified",
            workflow_id=input_data.workflow_id,
            browser_cases=len(browser_cases),
            api_cases=len(api_cases),
        )

        # ==================================================
        # PHASE 3: GENERATE PLAYWRIGHT SCRIPTS
        # ==================================================

        playwright_scripts: list[GeneratedScript] = []
        if input_data.generate_playwright and browser_cases:
            playwright_scripts = self._generate_playwright_scripts(
                test_cases=browser_cases,
                base_url=input_data.base_url,
                browser_type=input_data.browser_type,
                headless=input_data.headless,
                workflow_id=input_data.workflow_id,
            )

        # ==================================================
        # PHASE 4: GENERATE API TEST SCRIPTS
        # ==================================================

        api_scripts: list[GeneratedScript] = []
        if input_data.generate_api_tests and api_cases:
            api_scripts = self._generate_api_scripts(
                test_cases=api_cases,
                base_url=input_data.base_url,
                workflow_id=input_data.workflow_id,
            )

        # ==================================================
        # PHASE 5: SAVE SCRIPTS TO WORKSPACE
        # ==================================================

        workspace = Path(".aiqe") / "generated" / input_data.workflow_id[:8]
        workspace.mkdir(parents=True, exist_ok=True)
        output.workspace_path = str(workspace)

        for script in playwright_scripts + api_scripts:
            script_path = workspace / script.filename
            script_path.write_text(script.content, encoding="utf-8")
            logger.debug(
                "script_written",
                path=str(script_path),
                test_count=script.test_count,
            )

        # ==================================================
        # PHASE 6: WRITE TO MEMORY
        # ==================================================

        output.playwright_scripts = [s.to_dict() for s in playwright_scripts]
        output.api_test_scripts = [s.to_dict() for s in api_scripts]
        output.total_scripts_generated = (
            len(playwright_scripts) + len(api_scripts)
        )
        output.total_test_functions = sum(
            s.test_count for s in playwright_scripts + api_scripts
        )

        if self._memory:
            await self._memory.set(
                key=str(MemoryKeys.GENERATED_PLAYWRIGHT_SCRIPTS),
                value=[
                    {"filename": s.filename, "content": s.content,
                     **s.to_dict()}
                    for s in playwright_scripts
                ],
                written_by=self.NAME,
            )
            await self._memory.set(
                key=str(MemoryKeys.GENERATED_API_TESTS),
                value=[
                    {"filename": s.filename, "content": s.content,
                     **s.to_dict()}
                    for s in api_scripts
                ],
                written_by=self.NAME,
            )

        output.reasoning = (
            f"Generated {len(playwright_scripts)} Playwright scripts "
            f"({sum(s.test_count for s in playwright_scripts)} test functions) "
            f"and {len(api_scripts)} API test scripts "
            f"({sum(s.test_count for s in api_scripts)} test functions) "
            f"from {len(test_cases)} test cases. "
            f"Scripts saved to {workspace}."
        )
        output.confidence = 0.90

        output.add_evidence(
            kind="generated_scripts",
            content=(
                f"{output.total_scripts_generated} scripts, "
                f"{output.total_test_functions} test functions"
            ),
            source="automation_generator",
            relevance="Executable test scripts ready for Browser/API Execution Agents",
        )

        output.suggested_next_action = (
            f"Browser Execution Agent should run the "
            f"{len(playwright_scripts)} Playwright scripts. "
            f"API Validation Agent should run the "
            f"{len(api_scripts)} API test scripts."
        )

        return output

    def _generate_playwright_scripts(
        self,
        test_cases: list[dict[str, Any]],
        base_url: str,
        browser_type: str,
        headless: bool,
        workflow_id: str,
    ) -> list[GeneratedScript]:
        """Generate Playwright Python test scripts."""
        # Group by feature
        by_feature: dict[str, list[dict[str, Any]]] = {}
        for tc in test_cases:
            feature = tc.get("feature") or tc.get("area") or "core"
            feature_slug = feature.lower().replace(" ", "_")
            by_feature.setdefault(feature_slug, []).append(tc)

        scripts = []
        for feature_slug, cases in by_feature.items():
            script = self._build_playwright_script(
                feature_slug=feature_slug,
                test_cases=cases,
                base_url=base_url,
                browser_type=browser_type,
                headless=headless,
            )
            scripts.append(script)

        return scripts

    def _build_playwright_script(
        self,
        feature_slug: str,
        test_cases: list[dict[str, Any]],
        base_url: str,
        browser_type: str,
        headless: bool,
    ) -> GeneratedScript:
        """Build a single Playwright test file."""
        lines = [
            '"""',
            f'AIQE Generated Playwright Tests — {feature_slug}',
            'Auto-generated by AIQE Automation Generator Agent.',
            'Review before adding to your test suite.',
            '"""',
            "import pytest",
            "from playwright.sync_api import Page, expect",
            "",
            f'BASE_URL = "{base_url}"',
            "",
            "",
        ]

        for tc in test_cases:
            func_name = self._to_function_name(tc.get("title", "test"))
            test_type = tc.get("test_type", "positive")
            priority = tc.get("priority", "Medium")
            steps = tc.get("steps", [])
            expected = tc.get("expected_result", "")
            preconditions = tc.get("preconditions", [])

            lines.extend([
                f"@pytest.mark.{test_type}",
                f"@pytest.mark.{priority.lower()}",
                f"def {func_name}(page: Page):",
                f'    """',
                f'    {tc.get("title", "")}',
                f'    Expected: {expected}',
                f'    """',
            ])

            # Preconditions as comments
            if preconditions:
                lines.append("    # Preconditions:")
                for pre in preconditions:
                    lines.append(f"    # - {pre}")

            # Generate step implementations
            lines.append("    # Test Steps:")
            for step in steps:
                step_lower = step.lower()
                if "navigate" in step_lower or "go to" in step_lower:
                    lines.append(f'    page.goto(BASE_URL)')
                elif "click" in step_lower:
                    lines.append(f'    # page.click("selector")  # TODO: Add selector')
                elif "fill" in step_lower or "enter" in step_lower:
                    lines.append(f'    # page.fill("selector", "value")  # TODO: Add selector and value')
                elif "verify" in step_lower or "assert" in step_lower:
                    lines.append(f'    # expect(page).to_have_url(...)  # TODO: Add assertion')
                else:
                    lines.append(f'    # {step}')

            # Screenshot on completion
            lines.extend([
                '    page.screenshot(path=f"screenshots/{func_name}.png")',
                "",
                "",
            ])

        return GeneratedScript(
            filename=f"test_playwright_{feature_slug}.py",
            content="\n".join(lines),
            script_type="playwright",
            test_count=len(test_cases),
            feature=feature_slug,
        )

    def _generate_api_scripts(
        self,
        test_cases: list[dict[str, Any]],
        base_url: str,
        workflow_id: str,
    ) -> list[GeneratedScript]:
        """Generate API test scripts using httpx."""
        by_feature: dict[str, list[dict[str, Any]]] = {}
        for tc in test_cases:
            feature = tc.get("feature") or tc.get("area") or "api"
            feature_slug = feature.lower().replace(" ", "_")
            by_feature.setdefault(feature_slug, []).append(tc)

        scripts = []
        for feature_slug, cases in by_feature.items():
            script = self._build_api_script(
                feature_slug=feature_slug,
                test_cases=cases,
                base_url=base_url,
            )
            scripts.append(script)

        return scripts

    def _build_api_script(
        self,
        feature_slug: str,
        test_cases: list[dict[str, Any]],
        base_url: str,
    ) -> GeneratedScript:
        """Build a single API test file."""
        lines = [
            '"""',
            f'AIQE Generated API Tests — {feature_slug}',
            'Auto-generated by AIQE Automation Generator Agent.',
            'Review before adding to your test suite.',
            '"""',
            "import pytest",
            "import httpx",
            "",
            f'BASE_URL = "{base_url}"',
            "",
            "",
            "@pytest.fixture(scope='module')",
            "def client():",
            "    with httpx.Client(base_url=BASE_URL, timeout=30.0) as c:",
            "        yield c",
            "",
            "",
        ]

        for tc in test_cases:
            func_name = self._to_function_name(tc.get("title", "test"))
            test_type = tc.get("test_type", "positive")
            priority = tc.get("priority", "Medium")
            steps = tc.get("steps", [])
            expected = tc.get("expected_result", "")

            lines.extend([
                f"@pytest.mark.{test_type}",
                f"@pytest.mark.{priority.lower()}",
                f"def {func_name}(client: httpx.Client):",
                f'    """',
                f'    {tc.get("title", "")}',
                f'    Expected: {expected}',
                f'    """',
            ])

            # Infer HTTP method and path from steps
            method = "GET"
            path = "/api/endpoint"
            for step in steps:
                step_lower = step.lower()
                if "post" in step_lower:
                    method = "POST"
                elif "put" in step_lower or "update" in step_lower:
                    method = "PUT"
                elif "delete" in step_lower:
                    method = "DELETE"

            if test_type == "positive":
                lines.extend([
                    f'    response = client.{method.lower()}("{path}")',
                    f'    assert response.status_code in [200, 201, 204]',
                    f'    # TODO: Add schema validation',
                ])
            elif test_type == "negative":
                lines.extend([
                    f'    response = client.{method.lower()}("{path}", json={{}})',
                    f'    assert response.status_code in [400, 401, 403, 422]',
                    f'    # TODO: Verify error message',
                ])
            else:
                lines.extend([
                    f'    response = client.{method.lower()}("{path}")',
                    f'    assert response.status_code is not None',
                    f'    # TODO: Add specific assertions',
                ])

            lines.extend(["", ""])

        return GeneratedScript(
            filename=f"test_api_{feature_slug}.py",
            content="\n".join(lines),
            script_type="api",
            test_count=len(test_cases),
            feature=feature_slug,
        )

    def _to_function_name(self, title: str) -> str:
        """Convert a test title to a valid Python function name."""
        import re
        name = title.lower()
        name = re.sub(r"[^a-z0-9\s]", "", name)
        name = re.sub(r"\s+", "_", name.strip())
        name = name[:60]
        if not name.startswith("test_"):
            name = f"test_{name}"
        return name or "test_case"
