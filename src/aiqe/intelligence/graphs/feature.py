"""
AIQE Feature Graph Builder.

Discovers business features from a project and builds
a directed graph of feature dependencies.

What is a "feature" in AIQE's model?
    A business feature is any identifiable unit of business
    functionality. Examples:
    - "User Authentication" (login, logout, password reset)
    - "Shopping Cart" (add item, remove item, checkout)
    - "Admin Dashboard" (user management, reports, settings)

How features are discovered (deterministic, no AI):
    1. Route files — URL patterns reveal feature boundaries
    2. Test files — test names describe feature scenarios
    3. Directory structure — feature-oriented layout (DDD/Hexagonal)
    4. README/docs — feature section headings
    5. Config files — feature flags

The Feature Graph builder uses heuristics, not AI.
AI interprets the graph later (Test Strategy Agent).

Why deterministic discovery first?
    AI-based feature discovery requires the codebase as context.
    Deterministic discovery is faster, cheaper, and produces
    a structured graph AI can then enrich — not start from scratch.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aiqe.intelligence.models import (
    DependencyGraph,
    FeatureEdgeType,
    FeatureNodeType,
    GraphEdge,
    GraphNode,
)
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import slugify

logger = get_logger(__name__)

# Common route/URL pattern markers across frameworks
_ROUTE_PATTERNS = [
    # FastAPI / Flask / Starlette
    re.compile(r'@(?:app|router|blueprint)\.\w+\(["\']([^"\']+)["\']'),
    # Express.js
    re.compile(r'(?:app|router)\.\w+\(["\']([^"\']+)["\']'),
    # Django urls.py
    re.compile(r'path\(["\']([^"\']+)["\']'),
    re.compile(r'url\(["\']([^"\']+)["\']'),
    # Rails routes
    re.compile(r'(?:get|post|put|delete|patch)\s+["\']([^"\']+)["\']'),
]

# Test file naming patterns that reveal features
_TEST_FEATURE_PATTERN = re.compile(
    r'(?:test_|spec_|describe\s*\(|it\s*\(|def\s+test_)([a-z_]+)',
    re.IGNORECASE,
)

# Feature keywords to extract from README/docs
_FEATURE_HEADING_PATTERN = re.compile(
    r'^#{1,3}\s+(.+)$',
    re.MULTILINE,
)


class FeatureGraphBuilder:
    """
    Builds the Feature Graph from project source files.

    Discovers features using deterministic heuristics:
    routes, test files, directory structure, and documentation.

    Args:
        project_path: Root directory of the project to analyse.
    """

    def __init__(self, project_path: Path) -> None:
        self._project_path = project_path
        self._graph = DependencyGraph(
            name="Feature Graph",
            graph_type="feature",
        )

    def build(self) -> DependencyGraph:
        """
        Build the Feature Graph for the project.

        Returns:
            Populated DependencyGraph with feature nodes and edges.
        """
        logger.info(
            "feature_graph_building",
            project_path=str(self._project_path),
        )

        # Discover features from multiple sources
        self._discover_from_routes()
        self._discover_from_tests()
        self._discover_from_directories()
        self._discover_from_readme()

        # If we found nothing, add a generic feature
        if self._graph.is_empty():
            self._add_generic_feature()

        logger.info(
            "feature_graph_built",
            node_count=len(self._graph.nodes),
            edge_count=len(self._graph.edges),
        )

        return self._graph

    def _discover_from_routes(self) -> None:
        """Discover features from route/URL definitions."""
        route_files = list(self._project_path.rglob("*.py"))
        route_files += list(self._project_path.rglob("*.js"))
        route_files += list(self._project_path.rglob("*.ts"))
        route_files += list(self._project_path.rglob("*.rb"))

        # Cap at 200 files to avoid parsing entire large codebases
        route_files = route_files[:200]

        for file_path in route_files:
            if self._should_skip_file(file_path):
                continue
            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
                for pattern in _ROUTE_PATTERNS:
                    for match in pattern.finditer(content):
                        route = match.group(1)
                        feature = self._route_to_feature(route)
                        if feature:
                            self._add_feature_node(
                                feature_name=feature,
                                source="route",
                                file_path=str(
                                    file_path.relative_to(self._project_path)
                                ),
                                metadata={
                                    "route": route,
                                    "discovery_method": "route_pattern",
                                },
                            )
            except (OSError, PermissionError):
                continue

    def _discover_from_tests(self) -> None:
        """Discover features from test file names and test function names."""
        test_patterns = [
            "test_*.py", "*_test.py", "*_spec.py",
            "spec_*.py", "*.spec.ts", "*.test.ts",
            "*.spec.js", "*.test.js",
        ]

        test_files = []
        for pattern in test_patterns:
            test_files.extend(self._project_path.rglob(pattern))

        for file_path in test_files[:100]:
            if self._should_skip_file(file_path):
                continue
            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
                for match in _TEST_FEATURE_PATTERN.finditer(content):
                    feature_hint = match.group(1)
                    feature = self._test_name_to_feature(feature_hint)
                    if feature and len(feature) > 2:
                        self._add_feature_node(
                            feature_name=feature,
                            source="test",
                            file_path=str(
                                file_path.relative_to(self._project_path)
                            ),
                            metadata={
                                "discovery_method": "test_file",
                                "test_file": file_path.name,
                            },
                        )
            except (OSError, PermissionError):
                continue

    def _discover_from_directories(self) -> None:
        """
        Discover features from directory structure.

        Projects using DDD, Clean Architecture, or feature-based layout
        often have top-level directories per feature:
            src/features/authentication/
            src/features/payments/
            app/modules/user-management/
        """
        feature_dir_patterns = [
            "features", "modules", "domains",
            "components", "pages", "views",
        ]

        for dir_name in feature_dir_patterns:
            feature_root = self._project_path / dir_name
            if not feature_root.exists():
                # Also check src/ prefix
                feature_root = self._project_path / "src" / dir_name
                if not feature_root.exists():
                    continue

            for child in feature_root.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    feature_name = child.name.replace("-", " ").replace("_", " ")
                    self._add_feature_node(
                        feature_name=feature_name,
                        source="directory",
                        file_path=str(
                            child.relative_to(self._project_path)
                        ),
                        metadata={
                            "discovery_method": "directory_structure",
                            "directory": child.name,
                        },
                    )

    def _discover_from_readme(self) -> None:
        """Extract features from README headings."""
        readme_files = list(self._project_path.glob("README*"))
        readme_files += list(self._project_path.glob("readme*"))

        for readme in readme_files[:2]:
            try:
                content = readme.read_text(
                    encoding="utf-8", errors="ignore"
                )
                for match in _FEATURE_HEADING_PATTERN.finditer(content):
                    heading = match.group(1).strip()
                    # Skip common non-feature headings
                    if heading.lower() in {
                        "installation", "getting started", "usage",
                        "contributing", "license", "table of contents",
                        "requirements", "configuration", "api", "faq",
                    }:
                        continue
                    if 3 <= len(heading) <= 50:
                        self._add_feature_node(
                            feature_name=heading,
                            source="readme",
                            file_path=readme.name,
                            metadata={
                                "discovery_method": "readme_heading",
                            },
                        )
            except (OSError, PermissionError):
                continue

    def _add_generic_feature(self) -> None:
        """Add a generic feature when nothing was discovered."""
        project_name = self._project_path.name
        self._add_feature_node(
            feature_name=f"{project_name} Core",
            source="default",
            file_path="",
            metadata={"discovery_method": "default"},
        )

    def _add_feature_node(
        self,
        feature_name: str,
        source: str,
        file_path: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Add a feature node to the graph if it doesn't already exist.

        Returns the node ID.
        """
        node_id = f"feature:{slugify(feature_name)}"

        if node_id not in self._graph.nodes:
            node = GraphNode(
                id=node_id,
                label=feature_name,
                node_type=FeatureNodeType.FEATURE.value,
                file_path=file_path,
                metadata={
                    "source": source,
                    **(metadata or {}),
                },
            )
            self._graph.add_node(node)

        return node_id

    def _route_to_feature(self, route: str) -> str | None:
        """Convert a URL route to a feature name."""
        if not route or route in {"/", ""}:
            return None

        # Remove path parameters: /users/{id} → /users
        route = re.sub(r'\{[^}]+\}', '', route)
        route = re.sub(r':[a-z_]+', '', route)

        # Take the first meaningful path segment
        parts = [p for p in route.strip("/").split("/") if p]
        if not parts:
            return None

        feature = parts[0].replace("-", " ").replace("_", " ")

        # Skip generic/infrastructure routes
        if feature.lower() in {
            "static", "media", "assets", "favicon",
            "robots", "sitemap", "health", "metrics",
            "docs", "swagger", "openapi",
        }:
            return None

        return feature.title() if feature else None

    def _test_name_to_feature(self, test_name: str) -> str:
        """Convert a test function name to a feature name."""
        # Remove common prefixes/suffixes
        name = test_name.lower()
        for prefix in ["test_", "spec_", "should_", "can_", "when_"]:
            if name.startswith(prefix):
                name = name[len(prefix):]

        # Convert snake_case to Title Case
        words = name.replace("_", " ").split()
        if not words:
            return ""

        # Skip test utility function names
        if words[0] in {
            "setup", "teardown", "fixture", "helper",
            "util", "mock", "fake", "stub",
        }:
            return ""

        return " ".join(word.title() for word in words[:3])

    def _should_skip_file(self, file_path: Path) -> bool:
        """Return True if this file should be skipped during analysis."""
        skip_dirs = {
            ".git", ".venv", "venv", "node_modules",
            "__pycache__", ".pytest_cache", "dist", "build",
            ".mypy_cache", "htmlcov",
        }
        return any(part in skip_dirs for part in file_path.parts)
