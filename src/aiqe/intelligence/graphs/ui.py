"""
AIQE UI Navigation Graph Builder.

Discovers UI routes and navigation flows to build the
UI Navigation Graph.

Discovery sources:
    - React Router (JSX/TSX)
    - Vue Router (JS/TS config files)
    - Next.js pages directory
    - Angular routes
    - HTML links
"""

from __future__ import annotations

import re
from pathlib import Path

from aiqe.intelligence.models import (
    DependencyGraph,
    GraphNode,
    UIEdgeType,
    UINodeType,
)
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

_REACT_ROUTE = re.compile(
    r'<Route\s+(?:[^>]*?)path\s*=\s*["{]([^"}]+)["}]',
)
_NEXT_PAGE = re.compile(r'pages/([^.]+)\.(?:tsx?|jsx?)$')
_VUE_ROUTE = re.compile(
    r'path\s*:\s*["\']([^"\']+)["\']',
)
_HTML_LINK = re.compile(
    r'<a\s+[^>]*href\s*=\s*["\']([^"\'#?]+)["\']',
)
_AUTH_ROUTE = re.compile(
    r'(?:requireAuth|isAuthenticated|PrivateRoute|'
    r'AuthGuard|canActivate)',
    re.IGNORECASE,
)


class UINavigationGraphBuilder:
    """
    Builds the UI Navigation Graph.

    Args:
        project_path: Root directory of the project.
    """

    def __init__(self, project_path: Path) -> None:
        self._project_path = project_path
        self._graph = DependencyGraph(
            name="UI Navigation Graph",
            graph_type="ui",
        )

    def build(self) -> DependencyGraph:
        """Build the UI Navigation Graph."""
        logger.info(
            "ui_graph_building",
            project_path=str(self._project_path),
        )

        self._discover_react_routes()
        self._discover_nextjs_pages()
        self._discover_vue_routes()
        self._discover_html_pages()

        logger.info(
            "ui_graph_built",
            node_count=len(self._graph.nodes),
            edge_count=len(self._graph.edges),
        )

        return self._graph

    def _discover_react_routes(self) -> None:
        """Discover React Router route definitions."""
        jsx_files = [
            f for f in (
                list(self._project_path.rglob("*.jsx")) +
                list(self._project_path.rglob("*.tsx"))
            )
            if not self._should_skip(f)
        ][:100]

        for file_path in jsx_files:
            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
                rel_path = str(
                    file_path.relative_to(self._project_path)
                )
                requires_auth = bool(_AUTH_ROUTE.search(content))

                for match in _REACT_ROUTE.finditer(content):
                    path = match.group(1)
                    node_id = f"route:{path}"
                    label = self._path_to_label(path)

                    self._graph.add_node(GraphNode(
                        id=node_id,
                        label=label,
                        node_type=UINodeType.ROUTE.value,
                        file_path=rel_path,
                        metadata={
                            "path": path,
                            "requires_auth": requires_auth,
                            "framework": "react-router",
                        },
                    ))
            except (OSError, PermissionError):
                continue

    def _discover_nextjs_pages(self) -> None:
        """Discover Next.js pages from the pages/ directory."""
        pages_dir = self._project_path / "pages"
        if not pages_dir.exists():
            pages_dir = self._project_path / "app"  # Next.js 13+
        if not pages_dir.exists():
            return

        for file_path in pages_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix not in {
                ".tsx", ".ts", ".jsx", ".js"
            }:
                continue
            if file_path.name.startswith("_"):
                continue

            rel = str(file_path.relative_to(pages_dir))
            match = _NEXT_PAGE.search(str(file_path))
            if match:
                page_path = "/" + match.group(1).replace(
                    "index", ""
                ).rstrip("/")
                page_path = page_path or "/"

                node_id = f"route:{page_path}"
                self._graph.add_node(GraphNode(
                    id=node_id,
                    label=self._path_to_label(page_path),
                    node_type=UINodeType.SCREEN.value,
                    file_path=rel,
                    metadata={
                        "path": page_path,
                        "framework": "nextjs",
                    },
                ))

    def _discover_vue_routes(self) -> None:
        """Discover Vue Router route configurations."""
        vue_router_files = list(
            self._project_path.rglob("router*.{js,ts}")
        ) + list(
            self._project_path.rglob("routes*.{js,ts}")
        )

        for file_path in vue_router_files[:10]:
            if self._should_skip(file_path):
                continue
            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
                rel_path = str(
                    file_path.relative_to(self._project_path)
                )

                for match in _VUE_ROUTE.finditer(content):
                    path = match.group(1)
                    if path.startswith("/"):
                        node_id = f"route:{path}"
                        self._graph.add_node(GraphNode(
                            id=node_id,
                            label=self._path_to_label(path),
                            node_type=UINodeType.ROUTE.value,
                            file_path=rel_path,
                            metadata={
                                "path": path,
                                "framework": "vue-router",
                            },
                        ))
            except (OSError, PermissionError):
                continue

    def _discover_html_pages(self) -> None:
        """Discover HTML pages and navigation links."""
        html_files = [
            f for f in self._project_path.rglob("*.html")
            if not self._should_skip(f)
        ][:50]

        for file_path in html_files:
            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
                rel_path = str(
                    file_path.relative_to(self._project_path)
                )

                page_id = f"page:{rel_path}"
                self._graph.add_node(GraphNode(
                    id=page_id,
                    label=file_path.name,
                    node_type=UINodeType.SCREEN.value,
                    file_path=rel_path,
                    metadata={"framework": "html"},
                ))

                for match in _HTML_LINK.finditer(content):
                    href = match.group(1).strip()
                    if href and not href.startswith(("http", "mailto", "#")):
                        target_id = f"page:{href}"
                        if target_id not in self._graph.nodes:
                            self._graph.add_node(GraphNode(
                                id=target_id,
                                label=href,
                                node_type=UINodeType.SCREEN.value,
                                metadata={"href": href},
                            ))
                        from aiqe.intelligence.models import GraphEdge
                        self._graph.add_edge(GraphEdge(
                            source_id=page_id,
                            target_id=target_id,
                            edge_type=UIEdgeType.NAVIGATES_TO.value,
                        ))

            except (OSError, PermissionError):
                continue

    def _path_to_label(self, path: str) -> str:
        """Convert a URL path to a human-readable label."""
        if path == "/":
            return "Home"
        parts = [p for p in path.strip("/").split("/") if p]
        if not parts:
            return path
        return " ".join(
            p.replace("-", " ").replace("_", " ").title()
            for p in parts[:2]
        )

    def _should_skip(self, file_path: Path) -> bool:
        skip_dirs = {
            ".git", ".venv", "venv", "node_modules",
            "__pycache__", "dist", "build",
        }
        return any(part in skip_dirs for part in file_path.parts)
