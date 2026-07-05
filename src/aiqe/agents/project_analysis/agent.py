"""
AIQE Project Analysis Agent.

The foundational Tier 1 agent. Every other agent depends on
what this agent produces. It runs first, always.

Responsibilities (deterministic — no AI):
    - Detect programming language and version
    - Detect framework (FastAPI, Django, React, etc.)
    - Detect dependencies from manifest files
    - Detect routes / API endpoints
    - Detect authentication patterns
    - Detect database usage
    - Collect source and test files
    - Build Application Dependency Intelligence Model

Responsibilities (AI-assisted):
    - Summarise what the project does in plain English
    - Identify the most critical areas for testing
    - Flag unusual patterns that need attention

Why deterministic first, AI second?
    Framework detection via pyproject.toml is 100% accurate.
    AI-based detection from file contents is ~85% accurate.
    We get the best of both: deterministic facts + AI interpretation.

Tier: 1 (Core)
Dependencies: orchestrator (must run after orchestrator plans)
Memory Writes:
    - project_analysis.result
    - project_analysis.file_tree
    - intelligence.feature_graph
    - intelligence.code_dependency_graph
    - intelligence.api_dependency_graph
    - intelligence.database_dependency_graph
    - intelligence.ui_navigation_graph
    - system.workflow_metadata
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import (
    AgentInput,
    AgentOutput,
    ProjectAnalysisInput,
    ProjectAnalysisOutput,
)
from aiqe.intelligence.model import build_intelligence_model
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.exceptions import AgentError
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import Timer

logger = get_logger(__name__)


class ProjectAnalysisAgent(BaseAgent):
    """
    Project Analysis Agent — Tier 1.

    Analyses the project structure deterministically then uses
    the AI Gateway to generate a plain-English understanding
    of what the project does and what should be tested first.

    This agent produces the intelligence model that every
    subsequent agent uses for context.
    """

    NAME = "project_analysis"
    DESCRIPTION = (
        "Detects language, framework, dependencies, routes, APIs, "
        "auth patterns, and database usage. Builds the complete "
        "Application Dependency Intelligence Model."
    )
    TIER = 1
    DEPENDENCIES = ["orchestrator"]

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
        """Run project analysis."""
        assert isinstance(input_data, ProjectAnalysisInput), (
            f"Expected ProjectAnalysisInput, got {type(input_data).__name__}"
        )

        project_path = Path(input_data.project_path)
        if not project_path.exists():
            return self._make_error_output(
                f"Project path does not exist: {project_path}"
            )

        output = ProjectAnalysisOutput()

        # ==================================================
        # PHASE 1: DETERMINISTIC ANALYSIS (no AI)
        # ==================================================

        logger.info(
            "project_analysis_phase1_deterministic",
            workflow_id=input_data.workflow_id,
            project_path=str(project_path),
        )

        with Timer() as det_timer:
            intelligence_model = build_intelligence_model(project_path)

        profile = intelligence_model.project_profile

        # Populate output from deterministic results
        output.language = profile.language
        output.framework = profile.framework
        output.test_framework = profile.test_framework
        output.package_manager = profile.package_manager
        output.dependencies = profile.dependencies[:50]
        output.has_docker = profile.has_docker
        output.has_ci = profile.has_ci
        output.database = profile.database_type
        output.auth_method = "detected" if profile.has_auth else ""
        output.entry_points = profile.entry_points
        output.test_files = profile.test_files[:50]
        output.config_files = profile.config_files
        output.source_files_count = profile.file_count
        output.lines_of_code = profile.lines_of_code

        # Collect routes from API graph
        output.routes = [
            {
                "method": node.metadata.get("method", "ANY"),
                "path": node.metadata.get("path", node.label),
                "requires_auth": node.metadata.get("requires_auth", False),
            }
            for node in intelligence_model.api_graph.nodes.values()
        ][:50]

        logger.info(
            "project_analysis_deterministic_complete",
            workflow_id=input_data.workflow_id,
            language=profile.language,
            framework=profile.framework,
            source_files=profile.file_count,
            routes=len(output.routes),
            duration_seconds=det_timer.elapsed_seconds,
        )

        # ==================================================
        # PHASE 2: AI-ASSISTED INTERPRETATION
        # ==================================================

        if self._gateway and not input_data.dry_run:
            await self._ai_interpret(
                input_data=input_data,
                output=output,
                profile=profile,
                intelligence_model=intelligence_model,
            )
        else:
            output.reasoning = (
                f"Deterministic analysis complete. "
                f"Detected {profile.language} project using "
                f"{profile.framework} framework with "
                f"{profile.file_count} files. "
                f"AI interpretation skipped "
                f"({'dry run' if input_data.dry_run else 'no gateway'})."
            )
            output.confidence = 0.85

        # ==================================================
        # PHASE 3: WRITE TO SHARED MEMORY
        # ==================================================

        if self._memory:
            await self._write_to_memory(
                input_data=input_data,
                output=output,
                intelligence_model=intelligence_model,
            )

        output.add_evidence(
            kind="project_manifest",
            content=f"Language: {output.language}, "
                    f"Framework: {output.framework}, "
                    f"Files: {output.source_files_count}",
            source="pyproject.toml / package.json / manifest",
            relevance="Primary project identification source",
        )

        output.suggested_next_action = (
            f"Test Strategy Agent should now analyse the "
            f"{len(intelligence_model.feature_graph.nodes)} discovered features "
            f"and {len(output.routes)} API endpoints to generate a risk-based "
            f"test plan."
        )

        return output

    async def _ai_interpret(
        self,
        input_data: ProjectAnalysisInput,
        output: ProjectAnalysisOutput,
        profile: Any,
        intelligence_model: Any,
    ) -> None:
        """Use AI to interpret the deterministic findings."""
        from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage
        from aiqe.shared.security import sanitize_for_prompt

        features = intelligence_model.get_all_features()
        endpoints = intelligence_model.get_all_api_endpoints()
        tables = intelligence_model.get_database_tables()

        system_prompt = (
            "You are an expert software architect and QA engineer. "
            "Analyse the project profile and provide quality engineering insights. "
            "Be concise, specific, and actionable. "
            "Never make assumptions not supported by the evidence provided."
        )

        user_message = f"""Analyse this project profile and provide quality engineering insights.

PROJECT PROFILE:
Language: {profile.language}
Framework: {profile.framework}
Test Framework: {profile.test_framework}
Package Manager: {profile.package_manager}
Has Docker: {profile.has_docker}
Has CI: {profile.has_ci}
Has Authentication: {profile.has_auth}
Has Database: {profile.has_database}
Database Type: {profile.database_type}
Source Files: {profile.file_count}
Lines of Code: {profile.lines_of_code}
Dependencies: {profile.dependencies[:20]}

DISCOVERED FEATURES ({len(features)} total):
{chr(10).join(f'- {f}' for f in features[:15])}

API ENDPOINTS ({len(endpoints)} total):
{chr(10).join(f'- {e}' for e in endpoints[:15])}

DATABASE TABLES ({len(tables)} total):
{chr(10).join(f'- {t}' for t in tables[:10])}

Provide:
1. A 2-3 sentence plain English description of what this project does.
2. The 3 most critical areas to test first and why.
3. Any patterns that suggest elevated risk.
4. Confidence in this analysis (0.0-1.0).

Format your response as:
DESCRIPTION: <description>
CRITICAL_AREAS: <area1> | <area2> | <area3>
RISK_PATTERNS: <patterns or 'None detected'>
CONFIDENCE: <0.0-1.0>
REASONING: <your step-by-step reasoning>
"""

        try:
            request = AIRequest(
                messages=[PromptMessage.user(user_message)],
                task_type=AITaskType.ANALYSIS,
                max_tokens=800,
                system_prompt=system_prompt,
                workflow_id=input_data.workflow_id,
                agent_name=self.NAME,
                prompt_version="1.0",
            )

            response = await self._gateway.complete(request)
            output.ai_tokens_used = response.total_tokens

            self._parse_ai_response(response.content, output)

            output.add_evidence(
                kind="ai_analysis",
                content=f"AI analysed {len(features)} features, "
                        f"{len(endpoints)} endpoints",
                source=f"AI Gateway ({response.provider}/{response.model})",
                relevance="AI interpretation of project structure",
            )

        except Exception as e:
            logger.warning(
                "project_analysis_ai_failed",
                workflow_id=input_data.workflow_id,
                error=str(e),
            )
            output.reasoning = (
                f"Deterministic analysis succeeded. "
                f"AI interpretation unavailable: {e}"
            )
            output.confidence = 0.75
            output.add_warning(
                f"AI interpretation failed: {e}. "
                f"Proceeding with deterministic results only."
            )

    def _parse_ai_response(
        self,
        response_text: str,
        output: ProjectAnalysisOutput,
    ) -> None:
        """Parse the structured AI response into the output object."""
        lines = response_text.strip().split("\n")
        reasoning_parts = []

        for line in lines:
            line = line.strip()
            if line.startswith("DESCRIPTION:"):
                desc = line[len("DESCRIPTION:"):].strip()
                output.metadata["project_description"] = desc

            elif line.startswith("CRITICAL_AREAS:"):
                areas_str = line[len("CRITICAL_AREAS:"):].strip()
                areas = [a.strip() for a in areas_str.split("|")]
                output.metadata["critical_test_areas"] = areas

            elif line.startswith("RISK_PATTERNS:"):
                patterns = line[len("RISK_PATTERNS:"):].strip()
                if patterns and patterns.lower() != "none detected":
                    output.metadata["risk_patterns"] = patterns
                    output.add_warning(f"Risk pattern detected: {patterns}")

            elif line.startswith("CONFIDENCE:"):
                try:
                    conf = float(line[len("CONFIDENCE:"):].strip())
                    output.confidence = max(0.0, min(1.0, conf))
                except ValueError:
                    output.confidence = 0.8

            elif line.startswith("REASONING:"):
                reasoning_parts.append(
                    line[len("REASONING:"):].strip()
                )
            elif reasoning_parts:
                reasoning_parts.append(line)

        output.reasoning = " ".join(reasoning_parts) if reasoning_parts else (
            f"Project analysis complete. "
            f"Detected {output.language}/{output.framework} project."
        )

    async def _write_to_memory(
        self,
        input_data: AgentInput,
        output: ProjectAnalysisOutput,
        intelligence_model: Any,
    ) -> None:
        """Write all results to the workflow shared memory."""
        agent_name = self.NAME

        await self._memory.set(
            key=str(MemoryKeys.PROJECT_ANALYSIS_RESULT),
            value=output.to_dict(),
            written_by=agent_name,
        )

        await self._memory.set(
            key=str(MemoryKeys.PROJECT_FILE_TREE),
            value={
                "source_files": output.source_files_count,
                "test_files": len(output.test_files),
                "config_files": output.config_files,
            },
            written_by=agent_name,
        )

        await self._memory.set(
            key=str(MemoryKeys.FEATURE_GRAPH),
            value=intelligence_model.feature_graph.to_dict(),
            written_by=agent_name,
        )

        await self._memory.set(
            key=str(MemoryKeys.CODE_DEPENDENCY_GRAPH),
            value=intelligence_model.code_graph.to_dict(),
            written_by=agent_name,
        )

        await self._memory.set(
            key=str(MemoryKeys.API_DEPENDENCY_GRAPH),
            value=intelligence_model.api_graph.to_dict(),
            written_by=agent_name,
        )

        await self._memory.set(
            key=str(MemoryKeys.DATABASE_DEPENDENCY_GRAPH),
            value=intelligence_model.database_graph.to_dict(),
            written_by=agent_name,
        )

        await self._memory.set(
            key=str(MemoryKeys.UI_NAVIGATION_GRAPH),
            value=intelligence_model.ui_graph.to_dict(),
            written_by=agent_name,
        )

        logger.info(
            "project_analysis_memory_written",
            workflow_id=input_data.workflow_id,
            keys_written=7,
        )

    def validate_input(self, input_data: AgentInput) -> None:
        super().validate_input(input_data)
        if not input_data.project_path:
            raise ValueError(
                "ProjectAnalysisAgent requires project_path in input."
            )
