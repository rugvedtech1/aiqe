"""
AIQE Application Dependency Intelligence Model.

The ApplicationDependencyIntelligence is the combined result
of all five dependency graphs. It is the central intelligence
object that Test Strategy, Bug Analysis, and Release Intelligence
use to answer questions about the codebase.

See ADR-007.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiqe.intelligence.analyzers.dependency import DependencyAnalyzer
from aiqe.intelligence.analyzers.project import ProjectAnalyzer, ProjectProfile
from aiqe.intelligence.models import DependencyGraph
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import Timer

logger = get_logger(__name__)


@dataclass
class ApplicationDependencyIntelligence:
    """
    The complete Application Dependency Intelligence Model (ADR-007).

    Contains all five dependency graphs plus the project profile.
    Provides high-level query methods used by agents.

    Attributes:
        project_path: The project this model describes.
        project_profile: Detected language, framework, dependencies.
        feature_graph: Business feature dependency graph.
        code_graph: Module import dependency graph.
        api_graph: API endpoint dependency graph.
        database_graph: Database schema dependency graph.
        ui_graph: UI navigation dependency graph.
    """
    project_path: str
    project_profile: ProjectProfile
    feature_graph: DependencyGraph
    code_graph: DependencyGraph
    api_graph: DependencyGraph
    database_graph: DependencyGraph
    ui_graph: DependencyGraph

    def get_affected_features(
        self, changed_files: list[str]
    ) -> list[str]:
        """
        Find all features potentially affected by changed files.

        Used by the Test Strategy Agent to determine test scope.

        Args:
            changed_files: List of relative file paths that changed.

        Returns:
            List of feature node labels potentially affected.
        """
        affected_features = set()

        for changed_file in changed_files:
            changed_id = f"file:{changed_file}"

            # Check code graph: which modules import the changed file?
            code_affected = self.code_graph.find_affected_nodes(
                changed_id
            )
            for node_id in code_affected:
                node = self.code_graph.get_node(node_id)
                if node:
                    # Map code file back to a feature
                    file_path = node.file_path
                    for feat_node in self.feature_graph.nodes.values():
                        if feat_node.file_path and (
                            feat_node.file_path in file_path or
                            file_path.startswith(
                                feat_node.file_path.split("/")[0]
                            )
                        ):
                            affected_features.add(feat_node.label)

        return sorted(affected_features)

    def get_affected_api_endpoints(
        self, changed_files: list[str]
    ) -> list[str]:
        """
        Find API endpoints potentially affected by changed files.

        Args:
            changed_files: List of relative file paths that changed.

        Returns:
            List of affected endpoint labels (e.g. "POST /users").
        """
        affected = []
        for node in self.api_graph.nodes.values():
            if any(
                changed in node.file_path
                for changed in changed_files
                if node.file_path
            ):
                affected.append(node.label)
        return affected

    def find_failure_blast_radius(
        self, failed_feature: str
    ) -> list[str]:
        """
        Find all features that will be affected if a feature fails.

        Used by the Bug Analysis Agent to identify downstream effects.

        Args:
            failed_feature: Label of the feature that failed.

        Returns:
            List of feature labels in the blast radius.
        """
        # Find the node for this feature
        failed_id = None
        for node_id, node in self.feature_graph.nodes.items():
            if node.label.lower() == failed_feature.lower():
                failed_id = node_id
                break

        if failed_id is None:
            return []

        affected_ids = self.feature_graph.find_affected_nodes(failed_id)
        return [
            self.feature_graph.nodes[nid].label
            for nid in affected_ids
            if nid in self.feature_graph.nodes
        ]

    def get_all_features(self) -> list[str]:
        """Return all discovered feature labels."""
        return [
            node.label
            for node in self.feature_graph.nodes.values()
        ]

    def get_all_api_endpoints(self) -> list[str]:
        """Return all discovered API endpoint labels."""
        return [
            node.label
            for node in self.api_graph.nodes.values()
        ]

    def get_database_tables(self) -> list[str]:
        """Return all discovered database table names."""
        from aiqe.intelligence.models import DatabaseNodeType
        return [
            node.label
            for node in self.database_graph.nodes.values()
            if node.node_type == DatabaseNodeType.TABLE.value
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the intelligence model for memory store."""
        return {
            "project_path": self.project_path,
            "project_profile": self.project_profile.to_dict(),
            "feature_graph": self.feature_graph.to_dict(),
            "code_graph": self.code_graph.to_dict(),
            "api_graph": self.api_graph.to_dict(),
            "database_graph": self.database_graph.to_dict(),
            "ui_graph": self.ui_graph.to_dict(),
            "summary": {
                "total_features": len(self.feature_graph.nodes),
                "total_code_nodes": len(self.code_graph.nodes),
                "total_api_endpoints": len(self.api_graph.nodes),
                "total_db_tables": len(self.database_graph.nodes),
                "total_ui_routes": len(self.ui_graph.nodes),
            },
        }


def build_intelligence_model(
    project_path: Path,
) -> ApplicationDependencyIntelligence:
    """
    Build the complete Application Dependency Intelligence Model.

    Entry point called by the Project Analysis Agent.

    Args:
        project_path: Root directory of the project to analyse.

    Returns:
        Complete ApplicationDependencyIntelligence model.
    """
    logger.info(
        "intelligence_model_building",
        project_path=str(project_path),
    )

    with Timer() as timer:
        # Step 1: Project profile (language, framework, files)
        analyzer = ProjectAnalyzer(project_path)
        profile = analyzer.analyze()

        # Step 2: All five dependency graphs
        dep_analyzer = DependencyAnalyzer(project_path)
        graphs = dep_analyzer.build_all()

    model = ApplicationDependencyIntelligence(
        project_path=str(project_path),
        project_profile=profile,
        feature_graph=graphs["feature"],
        code_graph=graphs["code"],
        api_graph=graphs["api"],
        database_graph=graphs["database"],
        ui_graph=graphs["ui"],
    )

    logger.info(
        "intelligence_model_built",
        duration_seconds=timer.elapsed_seconds,
        features=len(model.feature_graph.nodes),
        code_nodes=len(model.code_graph.nodes),
        api_endpoints=len(model.api_graph.nodes),
        db_tables=len(model.database_graph.nodes),
        ui_routes=len(model.ui_graph.nodes),
    )

    return model
