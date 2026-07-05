"""
AIQE Dependency Analyzer.

Orchestrates all five graph builders to produce the complete
Application Dependency Intelligence Model (ADR-007).

This is the deterministic analysis layer that the Project Analysis
Agent (Tier 1, Step 15) calls before invoking the AI Gateway.
"""

from __future__ import annotations

from pathlib import Path

from aiqe.intelligence.graphs.api import APIDependencyGraphBuilder
from aiqe.intelligence.graphs.code import CodeDependencyGraphBuilder
from aiqe.intelligence.graphs.database import DatabaseDependencyGraphBuilder
from aiqe.intelligence.graphs.feature import FeatureGraphBuilder
from aiqe.intelligence.graphs.ui import UINavigationGraphBuilder
from aiqe.intelligence.models import DependencyGraph
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import Timer

logger = get_logger(__name__)


class DependencyAnalyzer:
    """
    Builds all five dependency graphs for a project.

    Args:
        project_path: Root directory of the project to analyse.
    """

    def __init__(self, project_path: Path) -> None:
        self._project_path = project_path

    def build_all(self) -> dict[str, DependencyGraph]:
        """
        Build all five dependency graphs.

        Returns:
            Dict mapping graph type name to DependencyGraph.
            Keys: feature, code, api, database, ui
        """
        logger.info(
            "dependency_analysis_started",
            project_path=str(self._project_path),
        )

        graphs: dict[str, DependencyGraph] = {}

        with Timer() as timer:
            # Feature Graph
            try:
                feature_builder = FeatureGraphBuilder(self._project_path)
                graphs["feature"] = feature_builder.build()
                logger.info(
                    "feature_graph_complete",
                    nodes=len(graphs["feature"].nodes),
                )
            except Exception as e:
                logger.warning(
                    "feature_graph_failed", error=str(e)
                )
                graphs["feature"] = DependencyGraph(
                    name="Feature Graph", graph_type="feature"
                )

            # Code Dependency Graph
            try:
                code_builder = CodeDependencyGraphBuilder(
                    self._project_path
                )
                graphs["code"] = code_builder.build()
                logger.info(
                    "code_graph_complete",
                    nodes=len(graphs["code"].nodes),
                )
            except Exception as e:
                logger.warning(
                    "code_graph_failed", error=str(e)
                )
                graphs["code"] = DependencyGraph(
                    name="Code Dependency Graph", graph_type="code"
                )

            # API Dependency Graph
            try:
                api_builder = APIDependencyGraphBuilder(
                    self._project_path
                )
                graphs["api"] = api_builder.build()
                logger.info(
                    "api_graph_complete",
                    nodes=len(graphs["api"].nodes),
                )
            except Exception as e:
                logger.warning(
                    "api_graph_failed", error=str(e)
                )
                graphs["api"] = DependencyGraph(
                    name="API Dependency Graph", graph_type="api"
                )

            # Database Dependency Graph
            try:
                db_builder = DatabaseDependencyGraphBuilder(
                    self._project_path
                )
                graphs["database"] = db_builder.build()
                logger.info(
                    "database_graph_complete",
                    nodes=len(graphs["database"].nodes),
                )
            except Exception as e:
                logger.warning(
                    "database_graph_failed", error=str(e)
                )
                graphs["database"] = DependencyGraph(
                    name="Database Dependency Graph",
                    graph_type="database",
                )

            # UI Navigation Graph
            try:
                ui_builder = UINavigationGraphBuilder(
                    self._project_path
                )
                graphs["ui"] = ui_builder.build()
                logger.info(
                    "ui_graph_complete",
                    nodes=len(graphs["ui"].nodes),
                )
            except Exception as e:
                logger.warning(
                    "ui_graph_failed", error=str(e)
                )
                graphs["ui"] = DependencyGraph(
                    name="UI Navigation Graph", graph_type="ui"
                )

        logger.info(
            "dependency_analysis_complete",
            total_duration_seconds=timer.elapsed_seconds,
            total_nodes=sum(
                len(g.nodes) for g in graphs.values()
            ),
            total_edges=sum(
                len(g.edges) for g in graphs.values()
            ),
        )

        return graphs
