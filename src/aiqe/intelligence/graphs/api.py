"""
AIQE API Dependency Graph Builder.

Discovers API endpoints and builds a graph of HTTP endpoint
relationships — which endpoints call each other, which share
middleware, and which require authentication.

Discovery methods:
    - FastAPI route decorators
    - Flask/Blueprint route decorators
    - Django URL patterns
    - Express.js route definitions
    - OpenAPI/Swagger spec files (openapi.json, swagger.yaml)

All deterministic — no AI needed to detect routes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from aiqe.intelligence.models import (
    APIEdgeType,
    APINodeType,
    DependencyGraph,
    GraphEdge,
    GraphNode,
)
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

# HTTP method + route extraction patterns
_FASTAPI_ROUTE = re.compile(
    r'@(?:app|router|api_router)\.'
    r'(get|post|put|delete|patch|head|options)'
    r'\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

_FLASK_ROUTE = re.compile(
    r'@(?:app|bp|blueprint)\.'
    r'route\s*\(\s*["\']([^"\']+)["\']'
    r'(?:.*?methods\s*=\s*\[([^\]]+)\])?',
    re.DOTALL,
)

_DJANGO_PATH = re.compile(
    r'(?:path|re_path|url)\s*\(\s*["\']([^"\']+)["\']'
    r'\s*,\s*(\w+)',
)

_EXPRESS_ROUTE = re.compile(
    r'(?:app|router)\.'
    r'(get|post|put|delete|patch|use)'
    r'\s*\(\s*["\']([^"\']+)["\']',
    re.IGNORECASE,
)

_AUTH_PATTERNS = re.compile(
    r'(?:require_auth|login_required|@auth|'
    r'Depends\(.*?auth|verify_token|authenticate)',
    re.IGNORECASE,
)


class APIDependencyGraphBuilder:
    """
    Builds the API Dependency Graph by parsing route definitions.

    Args:
        project_path: Root directory of the project.
    """

    def __init__(self, project_path: Path) -> None:
        self._project_path = project_path
        self._graph = DependencyGraph(
            name="API Dependency Graph",
            graph_type="api",
        )

    def build(self) -> DependencyGraph:
        """Build the API Dependency Graph."""
        logger.info(
            "api_graph_building",
            project_path=str(self._project_path),
        )

        # Try to load OpenAPI spec first (most complete source)
        if not self._load_openapi_spec():
            # Fall back to source code parsing
            self._parse_python_routes()
            self._parse_js_routes()

        logger.info(
            "api_graph_built",
            node_count=len(self._graph.nodes),
            edge_count=len(self._graph.edges),
        )

        return self._graph

    def _load_openapi_spec(self) -> bool:
        """
        Try to load endpoints from an OpenAPI/Swagger spec file.

        Returns True if a spec was found and loaded.
        """
        spec_candidates = [
            "openapi.json", "swagger.json",
            "openapi.yaml", "openapi.yml",
            "swagger.yaml", "swagger.yml",
            "docs/openapi.json", "api/openapi.json",
        ]

        for spec_name in spec_candidates:
            spec_path = self._project_path / spec_name
            if not spec_path.exists():
                continue

            try:
                if spec_path.suffix == ".json":
                    content = json.loads(
                        spec_path.read_text(encoding="utf-8")
                    )
                else:
                    import yaml
                    content = yaml.safe_load(
                        spec_path.read_text(encoding="utf-8")
                    )

                paths = content.get("paths", {})
                for path, methods in paths.items():
                    for method, operation in methods.items():
                        if method.upper() not in {
                            "GET", "POST", "PUT", "DELETE",
                            "PATCH", "HEAD", "OPTIONS",
                        }:
                            continue

                        node_id = f"endpoint:{method.upper()}:{path}"
                        tags = operation.get("tags", ["default"])
                        requires_auth = bool(
                            operation.get("security")
                        )

                        self._graph.add_node(GraphNode(
                            id=node_id,
                            label=f"{method.upper()} {path}",
                            node_type=APINodeType.ENDPOINT.value,
                            metadata={
                                "method": method.upper(),
                                "path": path,
                                "tags": tags,
                                "requires_auth": requires_auth,
                                "summary": operation.get("summary", ""),
                                "source": "openapi_spec",
                            },
                        ))

                logger.info(
                    "openapi_spec_loaded",
                    spec_path=spec_name,
                    endpoint_count=len(self._graph.nodes),
                )
                return True

            except Exception as e:
                logger.warning(
                    "openapi_spec_load_failed",
                    spec_path=spec_name,
                    error=str(e),
                )
                continue

        return False

    def _parse_python_routes(self) -> None:
        """Parse Python route definitions from source files."""
        python_files = [
            f for f in self._project_path.rglob("*.py")
            if not self._should_skip(f)
        ][:150]

        for file_path in python_files:
            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
                rel_path = str(
                    file_path.relative_to(self._project_path)
                )
                has_auth = bool(_AUTH_PATTERNS.search(content))

                # FastAPI patterns
                for match in _FASTAPI_ROUTE.finditer(content):
                    method = match.group(1).upper()
                    path = match.group(2)
                    self._add_endpoint_node(
                        method=method,
                        path=path,
                        file_path=rel_path,
                        requires_auth=has_auth,
                        source="fastapi",
                    )

                # Flask patterns
                for match in _FLASK_ROUTE.finditer(content):
                    path = match.group(1)
                    methods_str = match.group(2) or "GET"
                    methods = [
                        m.strip().strip('"\'').upper()
                        for m in methods_str.split(",")
                    ]
                    for method in methods:
                        if method:
                            self._add_endpoint_node(
                                method=method,
                                path=path,
                                file_path=rel_path,
                                requires_auth=has_auth,
                                source="flask",
                            )

                # Django patterns
                for match in _DJANGO_PATH.finditer(content):
                    path = match.group(1)
                    view_name = match.group(2)
                    self._add_endpoint_node(
                        method="ANY",
                        path=path,
                        file_path=rel_path,
                        requires_auth=has_auth,
                        source="django",
                        metadata={"view": view_name},
                    )

            except (OSError, PermissionError):
                continue

    def _parse_js_routes(self) -> None:
        """Parse JavaScript/TypeScript route definitions."""
        js_files = [
            f for f in (
                list(self._project_path.rglob("*.js")) +
                list(self._project_path.rglob("*.ts"))
            )
            if not self._should_skip(f)
        ][:100]

        for file_path in js_files:
            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
                rel_path = str(
                    file_path.relative_to(self._project_path)
                )

                for match in _EXPRESS_ROUTE.finditer(content):
                    method = match.group(1).upper()
                    path = match.group(2)
                    if path.startswith("/"):
                        self._add_endpoint_node(
                            method=method,
                            path=path,
                            file_path=rel_path,
                            requires_auth=False,
                            source="express",
                        )

            except (OSError, PermissionError):
                continue

    def _add_endpoint_node(
        self,
        method: str,
        path: str,
        file_path: str,
        requires_auth: bool,
        source: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Add an API endpoint node."""
        node_id = f"endpoint:{method}:{path}"

        if node_id not in self._graph.nodes:
            node = GraphNode(
                id=node_id,
                label=f"{method} {path}",
                node_type=APINodeType.ENDPOINT.value,
                file_path=file_path,
                metadata={
                    "method": method,
                    "path": path,
                    "requires_auth": requires_auth,
                    "source": source,
                    **(metadata or {}),
                },
            )
            self._graph.add_node(node)

        return node_id

    def _should_skip(self, file_path: Path) -> bool:
        skip_dirs = {
            ".git", ".venv", "venv", "node_modules",
            "__pycache__", "dist", "build", "htmlcov",
        }
        return any(part in skip_dirs for part in file_path.parts)
