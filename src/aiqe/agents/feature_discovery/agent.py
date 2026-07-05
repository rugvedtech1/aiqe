"""
AIQE Feature Discovery Agent.

Enriches the feature graph with AI-assisted understanding
of business features, their relationships, and business value.

While the deterministic FeatureGraphBuilder (Step 13) discovers
features from routes and directories, this agent uses AI to:
    - Give features meaningful business names
    - Understand the business purpose of each feature
    - Identify feature dependencies not visible in code
    - Assess the business criticality of each feature
    - Map technical components to user-facing capabilities

Tier: 4 (Intelligence)
Dependencies: project_analysis
Memory Reads: project_analysis.result, intelligence.feature_graph
Memory Writes: Updates feature_graph with AI-enriched data
"""

from __future__ import annotations

import json
from typing import Any

from aiqe.agents.base import BaseAgent
from aiqe.agents.types import AgentInput, AgentOutput
from aiqe.memory.schema import MemoryKeys
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class FeatureDiscoveryOutput(AgentOutput):
    """Output from the Feature Discovery Agent."""

    def __init__(self) -> None:
        super().__init__()
        self.enriched_features: list[dict[str, Any]] = []
        self.feature_count: int = 0
        self.critical_features: list[str] = []
        self.feature_relationships: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        base = super().to_dict()
        return {
            **base,
            "enriched_features": self.enriched_features,
            "feature_count": self.feature_count,
            "critical_features": self.critical_features,
            "feature_relationships": self.feature_relationships,
        }


class FeatureDiscoveryInput(AgentInput):
    """Input for the Feature Discovery Agent."""
    max_features_to_enrich: int = 20


class FeatureDiscoveryAgent(BaseAgent):
    """
    Feature Discovery Agent — Tier 4.

    Enriches the deterministically-discovered feature graph
    with AI-assisted business context understanding.
    """

    NAME = "feature_discovery"
    DESCRIPTION = (
        "Enriches the feature graph with AI-assisted business context, "
        "criticality assessment, and relationship mapping."
    )
    TIER = 4
    DEPENDENCIES = ["project_analysis"]

    def __init__(
        self,
        memory_store: Any = None,
        gateway: Any = None,
    ) -> None:
        self._memory = memory_store
        self._gateway = gateway

    async def run_impl(self, input_data: AgentInput) -> FeatureDiscoveryOutput:
        """Discover and enrich business features."""
        assert isinstance(input_data, FeatureDiscoveryInput), (
            f"Expected FeatureDiscoveryInput, got {type(input_data).__name__}"
        )

        output = FeatureDiscoveryOutput()

        # Load feature graph and project analysis
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

        raw_features = list(feature_graph_data.get("nodes", {}).values())
        if not raw_features:
            output.reasoning = (
                "No features in the feature graph to enrich. "
                "Deterministic analysis found no feature indicators."
            )
            output.confidence = 1.0
            return output

        features_to_enrich = raw_features[:input_data.max_features_to_enrich]

        # AI enrichment
        if self._gateway and not input_data.dry_run:
            enriched = await self._ai_enrich_features(
                features=features_to_enrich,
                project_analysis=project_analysis,
                input_data=input_data,
            )
            output.enriched_features = enriched
        else:
            # Deterministic enrichment fallback
            output.enriched_features = [
                {
                    "id": f.get("id", ""),
                    "label": f.get("label", ""),
                    "business_name": f.get("label", ""),
                    "business_purpose": f"Provides {f.get('label', 'core')} functionality",
                    "criticality": "medium",
                    "user_facing": True,
                }
                for f in features_to_enrich
            ]

        output.feature_count = len(output.enriched_features)
        output.critical_features = [
            f.get("business_name", f.get("label", ""))
            for f in output.enriched_features
            if f.get("criticality") in {"critical", "high"}
        ]

        output.reasoning = (
            f"Feature discovery complete. "
            f"Enriched {output.feature_count} features. "
            f"Critical features: {output.critical_features[:5]}."
        )
        output.confidence = 0.80

        # Update feature graph in memory with enriched data
        if self._memory and output.enriched_features:
            for enriched_feature in output.enriched_features:
                feature_id = enriched_feature.get("id", "")
                if feature_id and feature_id in feature_graph_data.get("nodes", {}):
                    feature_graph_data["nodes"][feature_id].update({
                        "metadata": {
                            **feature_graph_data["nodes"][feature_id].get(
                                "metadata", {}
                            ),
                            "enriched": True,
                            "business_purpose": enriched_feature.get(
                                "business_purpose", ""
                            ),
                            "criticality": enriched_feature.get(
                                "criticality", "medium"
                            ),
                        }
                    })

            await self._memory.set(
                key=str(MemoryKeys.FEATURE_GRAPH),
                value=feature_graph_data,
                written_by=self.NAME,
            )

        return output

    async def _ai_enrich_features(
        self,
        features: list[dict[str, Any]],
        project_analysis: dict[str, Any],
        input_data: FeatureDiscoveryInput,
    ) -> list[dict[str, Any]]:
        """Use AI to enrich features with business context."""
        from aiqe.gateway.types import AIRequest, AITaskType, PromptMessage

        feature_list = "\n".join([
            f"- {f.get('label', 'unknown')} (source: {f.get('metadata', {}).get('source', 'unknown')})"
            for f in features
        ])

        user_message = f"""Analyse these discovered features from a {project_analysis.get('language', 'unknown')}/{project_analysis.get('framework', 'unknown')} application.

FEATURES:
{feature_list}

For each feature, provide:
1. A clear business name (user-facing language, not technical)
2. The business purpose in one sentence
3. Criticality: critical|high|medium|low
4. Is it user-facing: true|false

Return as JSON array:
[
  {{
    "label": "original technical label",
    "business_name": "User-friendly feature name",
    "business_purpose": "What this feature enables for users",
    "criticality": "critical|high|medium|low",
    "user_facing": true
  }}
]"""

        try:
            request = AIRequest(
                messages=[PromptMessage.user(user_message)],
                task_type=AITaskType.ANALYSIS,
                max_tokens=1500,
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

            enriched_data = json.loads(clean)
            if not isinstance(enriched_data, list):
                return []

            result = []
            for i, enriched in enumerate(enriched_data):
                original = features[i] if i < len(features) else {}
                result.append({
                    "id": original.get("id", ""),
                    "label": original.get("label", ""),
                    **enriched,
                })

            return result

        except Exception as e:
            logger.warning(
                "feature_discovery_ai_failed",
                error=str(e),
            )
            return [
                {
                    "id": f.get("id", ""),
                    "label": f.get("label", ""),
                    "business_name": f.get("label", ""),
                    "business_purpose": f"Provides {f.get('label', 'core')} capability",
                    "criticality": "medium",
                    "user_facing": True,
                }
                for f in features
            ]
