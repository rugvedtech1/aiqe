"""
AIQE Requirement Intelligence Agent.

Automatically generates business requirements from code
analysis and feature discovery.

This agent bridges the gap between code and business intent:
given the technical structure of the project, it infers
what business requirements the code is trying to fulfil.

These inferred requirements are used by:
    - Test Strategy Agent (what should be tested)
    - Test Case Generator (what scenarios are required)
    - Report Agent (what are we actually testing)
    - Release Intelligence Engine (are requirements met?)

Tier: 4 (Intelligence)
Dependencies: feature_discovery, project_analysis
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass
class Requirement:
    """An inferred business requirement."""
    id: str = ""
    title: str = ""
    description: str = ""
    feature: str = ""
    type: str = "functional"  # functional | non_functional | security | performance
    priority: str = "medium"
    acceptance_criteria: list[str] = field(default_factory=list)
    source: str = "inferred"
    confidence: float = 0.7

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "feature": self.feature,
            "type": self.type,
            "priority": self.priority,
            "acceptance_criteria": self.acceptance_criteria,
            "source": self.source,
            "confidence": self.confidence,
        }


class RequirementIntelligenceOutput(AgentOutput):
    """Output from the Requirement Intelligence Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.requirements: list[dict[str, Any]] = []
        self.total_requirements: int = 0
        self.by_type: dict[str, int] = {}
        self.by_priority: dict[str, int] = {}

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "requirements": self.requirements,
            "total_requirements": self.total_requirements,
            "by_type": self.by_type,
            "by_priority": self.by_priority,
        }


class RequirementIntelligenceInput(AgentInput):
    """Input for the Requirement Intelligence Agent."""
    max_requirements: int = 30


class RequirementIntelligenceAgent(BaseAgent):
    """
    Requirement Intelligence Agent — Tier 4.

    Automatically infers business requirements from the
    project's code structure and feature graph.
    """

    NAME = "requirement_intelligence"
    DESCRIPTION = (
        "Automatically generates business requirements from code "
        "analysis and feature discovery, with acceptance criteria."
    )
    TIER = 4
    DEPENDENCIES = ["feature_discovery", "project_analysis"]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway

    async def run_impl(self, input_data: AgentInput) -> RequirementIntelligenceOutput:
        """Generate business requirements from code analysis."""
        assert isinstance(input_data, RequirementIntelligenceInput), (
            f"Expected RequirementIntelligenceInput, "
            f"got {type(input_data).__name__}"
        )

        output = RequirementIntelligenceOutput()

        # Load context
        feature_graph_data: dict[str, Any] = {}
        project_analysis: dict[str, Any] = {}

        if self._memory:
            feature_graph_data = await self._memory.get(
                key=str(MemoryKeys.FEATURE_GRAPH),
                reader=self.NAME,
            ) or {}
            project_analysis = await self._memory.get(
                key=str(MemoryKeys.PROJECT_ANALYSIS_RESULT),
                reader=self.NAME,
            ) or {}

        features = [
            node.get("label", "")
            for node in feature_graph_data.get("nodes", {}).values()
        ]

        if not features:
            output.reasoning = (
                "No features discovered to generate requirements from."
            )
            output.confidence = 1.0
            return output

        # Generate requirements
        if self._gateway and not input_data.dry_run:
            requirements = await self._ai_generate_requirements(
                features=features,
                project_analysis=project_analysis,
                input_data=input_data,
            )
        else:
            requirements = self._deterministic_requirements(
                features=features,
                project_analysis=project_analysis,
            )

        output.requirements = [r.to_dict() for r in requirements]
        output.total_requirements = len(requirements)

        for req in requirements:
            t = req.type
            p = req.priority
            output.by_type[t] = output.by_type.get(t, 0) + 1
            output.by_priority[p] = output.by_priority.get(p, 0) + 1

        output.reasoning = (
            f"Generated {output.total_requirements} requirements "
            f"from {len(features)} discovered features. "
            f"Types: {output.by_type}. "
            f"Priorities: {output.by_priority}."
        )
        output.confidence = 0.75

        output.suggested_next_action = (
            "These inferred requirements can be used to validate "
            "test coverage and ensure all business needs are tested."
        )

        return output

    async def _ai_generate_requirements(
        self,
        features: list[str],
        project_analysis: dict[str, Any],
        input_data: RequirementIntelligenceInput,
    ) -> list[Requirement]:
        """Use AI to generate business requirements from features."""
        from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage

        has_auth = bool(project_analysis.get("auth_method"))
        has_db = project_analysis.get("has_database", False)

        user_message = f"""Generate business requirements for this {project_analysis.get('framework', 'application')}.

DISCOVERED FEATURES:
{chr(10).join(f'- {f}' for f in features[:15])}

PROJECT CONTEXT:
- Has Authentication: {has_auth}
- Has Database: {has_db}
- API Endpoints: {len(project_analysis.get('routes', []))}

Generate up to {min(input_data.max_requirements, 20)} business requirements.
Include functional, security, and performance requirements.

Return as JSON array:
[
  {{
    "id": "REQ-001",
    "title": "Requirement title",
    "description": "Detailed description",
    "feature": "which feature this covers",
    "type": "functional|non_functional|security|performance",
    "priority": "critical|high|medium|low",
    "acceptance_criteria": ["criteria 1", "criteria 2"],
    "confidence": 0.0
  }}
]"""

        try:
            request = AIRequest(
                messages=[PromptMessage.user(user_message)],
                task_type=AITaskType.ANALYSIS,
                max_tokens=2000,
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

            reqs_data = json.loads(clean)
            if not isinstance(reqs_data, list):
                return []

            return [
                Requirement(
                    id=r.get("id", f"REQ-{i+1:03d}"),
                    title=r.get("title", ""),
                    description=r.get("description", ""),
                    feature=r.get("feature", ""),
                    type=r.get("type", "functional"),
                    priority=r.get("priority", "medium"),
                    acceptance_criteria=r.get("acceptance_criteria", []),
                    source="ai_inferred",
                    confidence=float(r.get("confidence", 0.7)),
                )
                for i, r in enumerate(reqs_data[:input_data.max_requirements])
            ]

        except Exception as e:
            logger.warning(
                "requirement_intelligence_ai_failed",
                error=str(e),
            )
            return self._deterministic_requirements(
                features=features,
                project_analysis=project_analysis,
            )

    def _deterministic_requirements(
        self,
        features: list[str],
        project_analysis: dict[str, Any],
    ) -> list[Requirement]:
        """Generate basic requirements deterministically."""
        requirements = []
        has_auth = bool(project_analysis.get("auth_method"))
        has_db = project_analysis.get("has_database", False)

        for i, feature in enumerate(features[:10]):
            requirements.append(Requirement(
                id=f"REQ-{i+1:03d}",
                title=f"{feature} must be available",
                description=(
                    f"The {feature} feature must function correctly "
                    f"and be accessible to authorised users."
                ),
                feature=feature,
                type="functional",
                priority="high",
                acceptance_criteria=[
                    f"{feature} responds within 500ms",
                    f"{feature} returns correct data format",
                    f"{feature} handles errors gracefully",
                ],
                source="deterministic",
                confidence=0.6,
            ))

        if has_auth:
            requirements.append(Requirement(
                id="REQ-AUTH-001",
                title="Authentication must be enforced",
                description="All protected endpoints require valid authentication.",
                feature="authentication",
                type="security",
                priority="critical",
                acceptance_criteria=[
                    "Unauthenticated requests return 401",
                    "Expired tokens are rejected",
                    "Invalid tokens are rejected",
                ],
                source="deterministic",
                confidence=0.9,
            ))

        if has_db:
            requirements.append(Requirement(
                id="REQ-DB-001",
                title="Data must be persisted correctly",
                description="All CRUD operations must complete successfully.",
                feature="database",
                type="functional",
                priority="high",
                acceptance_criteria=[
                    "Data is saved to database",
                    "Data can be retrieved after save",
                    "Deleted data is no longer returned",
                ],
                source="deterministic",
                confidence=0.85,
            ))

        return requirements
