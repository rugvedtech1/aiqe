"""
AIQE Application Dependency Intelligence.

Implements the Application Dependency Intelligence Model (ADR-007).
All analysis is deterministic — no AI is used in this package.
AI agents use this model's output as context for their decisions.

Public API:
    ApplicationDependencyIntelligence — the complete model
    build_intelligence_model          — factory function
    DependencyGraph                   — generic graph container
    GraphNode, GraphEdge              — graph primitives
    ProjectProfile                    — raw project analysis result
    ProjectAnalyzer                   — analyse a project directory
    DependencyAnalyzer                — build all five graphs

Graph builders (use via DependencyAnalyzer):
    FeatureGraphBuilder
    CodeDependencyGraphBuilder
    APIDependencyGraphBuilder
    DatabaseDependencyGraphBuilder
    UINavigationGraphBuilder
"""

from aiqe.intelligence.analyzers.dependency import DependencyAnalyzer
from aiqe.intelligence.analyzers.project import ProjectAnalyzer, ProjectProfile
from aiqe.intelligence.graphs.api import APIDependencyGraphBuilder
from aiqe.intelligence.graphs.code import CodeDependencyGraphBuilder
from aiqe.intelligence.graphs.database import DatabaseDependencyGraphBuilder
from aiqe.intelligence.graphs.feature import FeatureGraphBuilder
from aiqe.intelligence.graphs.ui import UINavigationGraphBuilder
from aiqe.intelligence.model import (
    ApplicationDependencyIntelligence,
    build_intelligence_model,
)
from aiqe.intelligence.models import (
    DependencyGraph,
    GraphEdge,
    GraphNode,
)

__all__ = [
    "APIDependencyGraphBuilder",
    "ApplicationDependencyIntelligence",
    "CodeDependencyGraphBuilder",
    "DatabaseDependencyGraphBuilder",
    "DependencyAnalyzer",
    "DependencyGraph",
    "FeatureGraphBuilder",
    "GraphEdge",
    "GraphNode",
    "ProjectAnalyzer",
    "ProjectProfile",
    "UINavigationGraphBuilder",
    "build_intelligence_model",
]
