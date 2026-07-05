"""
AIQE Code Dependency Graph Builder.

Parses Python source files and builds a directed graph of
module import relationships.

Approach:
    Uses Python's built-in ast module for Python files.
    Uses regex for JavaScript/TypeScript import statements.
    Deterministic — no AI, no subprocess calls.

What this graph enables:
    When a file changes, the Code Dependency Graph tells
    Test Strategy which other modules import it (dependents)
    and which modules it imports (dependencies). This drives
    targeted test selection — only test what could be affected.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from aiqe.intelligence.models import (
    CodeEdgeType,
    CodeNodeType,
    DependencyGraph,
    GraphEdge,
    GraphNode,
)
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

# JavaScript/TypeScript import patterns
_JS_IMPORT_PATTERN = re.compile(
    r'(?:import\s+.*?\s+from\s+|require\s*\(\s*)["\']([^"\']+)["\']',
)


class CodeDependencyGraphBuilder:
    """
    Builds the Code Dependency Graph by parsing import statements.

    Args:
        project_path: Root directory of the project.
        max_files: Maximum number of files to parse (performance cap).
    """

    def __init__(
        self,
        project_path: Path,
        max_files: int = 300,
    ) -> None:
        self._project_path = project_path
        self._max_files = max_files
        self._graph = DependencyGraph(
            name="Code Dependency Graph",
            graph_type="code",
        )

    def build(self) -> DependencyGraph:
        """Build the Code Dependency Graph."""
        logger.info(
            "code_graph_building",
            project_path=str(self._project_path),
        )

        python_files = list(self._project_path.rglob("*.py"))
        js_files = (
            list(self._project_path.rglob("*.js")) +
            list(self._project_path.rglob("*.ts")) +
            list(self._project_path.rglob("*.jsx")) +
            list(self._project_path.rglob("*.tsx"))
        )

        # Filter and cap
        python_files = [
            f for f in python_files
            if not self._should_skip(f)
        ][:self._max_files]

        js_files = [
            f for f in js_files
            if not self._should_skip(f)
        ][:self._max_files // 2]

        # Add all files as nodes first
        for file_path in python_files:
            self._add_file_node(file_path, "python")

        for file_path in js_files:
            self._add_file_node(file_path, "javascript")

        # Then parse imports and add edges
        for file_path in python_files:
            self._parse_python_imports(file_path)

        for file_path in js_files:
            self._parse_js_imports(file_path)

        logger.info(
            "code_graph_built",
            node_count=len(self._graph.nodes),
            edge_count=len(self._graph.edges),
            python_files=len(python_files),
            js_files=len(js_files),
        )

        return self._graph

    def _add_file_node(
        self, file_path: Path, language: str
    ) -> str:
        """Add a source file as a node."""
        rel_path = str(file_path.relative_to(self._project_path))
        node_id = f"file:{rel_path}"

        node = GraphNode(
            id=node_id,
            label=file_path.name,
            node_type=CodeNodeType.FILE.value,
            file_path=rel_path,
            metadata={
                "language": language,
                "size_bytes": file_path.stat().st_size
                if file_path.exists() else 0,
            },
        )
        self._graph.add_node(node)
        return node_id

    def _parse_python_imports(self, file_path: Path) -> None:
        """Parse Python import statements using ast."""
        try:
            content = file_path.read_text(
                encoding="utf-8", errors="ignore"
            )
            tree = ast.parse(content, filename=str(file_path))
        except (SyntaxError, OSError, ValueError):
            return

        rel_path = str(file_path.relative_to(self._project_path))
        source_id = f"file:{rel_path}"

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._add_import_edge(
                        source_id=source_id,
                        module_name=alias.name,
                        import_type="import",
                        line=node.lineno,
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self._add_import_edge(
                        source_id=source_id,
                        module_name=node.module,
                        import_type="from_import",
                        line=node.lineno,
                        level=node.level,
                    )

    def _parse_js_imports(self, file_path: Path) -> None:
        """Parse JavaScript/TypeScript import statements using regex."""
        try:
            content = file_path.read_text(
                encoding="utf-8", errors="ignore"
            )
        except (OSError, PermissionError):
            return

        rel_path = str(file_path.relative_to(self._project_path))
        source_id = f"file:{rel_path}"

        for match in _JS_IMPORT_PATTERN.finditer(content):
            module_path = match.group(1)
            self._add_import_edge(
                source_id=source_id,
                module_name=module_path,
                import_type="js_import",
                line=content[:match.start()].count("\n") + 1,
            )

    def _add_import_edge(
        self,
        source_id: str,
        module_name: str,
        import_type: str,
        line: int = 0,
        level: int = 0,
    ) -> None:
        """
        Add an import edge between two file nodes.

        Resolves the imported module to a file path if possible.
        If the module cannot be resolved to a project file,
        it is treated as an external dependency.
        """
        # Try to resolve to a project file
        target_id = self._resolve_module(module_name, level)

        if target_id is None:
            # External dependency — add as a node if not already present
            ext_id = f"external:{module_name.split('.')[0]}"
            if ext_id not in self._graph.nodes:
                self._graph.add_node(GraphNode(
                    id=ext_id,
                    label=module_name.split(".")[0],
                    node_type=CodeNodeType.MODULE.value,
                    metadata={"is_external": True},
                ))
            target_id = ext_id

        edge = GraphEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=CodeEdgeType.IMPORTS.value,
            metadata={
                "import_type": import_type,
                "line": line,
                "module_name": module_name,
            },
        )
        self._graph.add_edge(edge)

    def _resolve_module(
        self,
        module_name: str,
        level: int = 0,
    ) -> str | None:
        """
        Try to resolve a module name to a project file path.

        Returns the node_id if found, None if external.
        """
        # Convert module path to file path candidates
        module_path = module_name.replace(".", "/")
        candidates = [
            self._project_path / f"{module_path}.py",
            self._project_path / f"{module_path}/__init__.py",
            self._project_path / "src" / f"{module_path}.py",
            self._project_path / "src" / f"{module_path}/__init__.py",
        ]

        for candidate in candidates:
            if candidate.exists():
                rel = str(candidate.relative_to(self._project_path))
                return f"file:{rel}"

        return None

    def _should_skip(self, file_path: Path) -> bool:
        """Return True if this file should be skipped."""
        skip_dirs = {
            ".git", ".venv", "venv", "node_modules",
            "__pycache__", ".pytest_cache", "dist", "build",
            "htmlcov", "migrations",
        }
        return any(part in skip_dirs for part in file_path.parts)
