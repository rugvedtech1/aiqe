"""
AIQE Database Dependency Graph Builder.

Discovers database schemas, migrations, and table relationships
to build the Database Dependency Graph.

Discovery sources:
    - SQLAlchemy model files (Python)
    - Django model files (Python)
    - Alembic migration files
    - SQL schema files (.sql)
    - Prisma schema files
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from aiqe.intelligence.models import (
    DatabaseEdgeType,
    DatabaseNodeType,
    DependencyGraph,
    GraphEdge,
    GraphNode,
)
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

# Table/model detection patterns
_SQLALCHEMY_TABLE = re.compile(
    r'class\s+(\w+)\s*\(.*?(?:Base|Model|db\.Model)',
    re.DOTALL,
)
_SQLALCHEMY_FK = re.compile(
    r'ForeignKey\s*\(\s*["\']([^"\'\.]+)\.([^"\']+)["\']',
)
_DJANGO_MODEL = re.compile(
    r'class\s+(\w+)\s*\(\s*models\.Model\s*\)',
)
_DJANGO_FK = re.compile(
    r'(?:ForeignKey|ManyToManyField|OneToOneField)'
    r'\s*\(\s*["\']?(\w+)["\']?',
)
_SQL_CREATE_TABLE = re.compile(
    r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\[]?(\w+)[`"\]]?',
    re.IGNORECASE,
)
_SQL_FK = re.compile(
    r'REFERENCES\s+[`"\[]?(\w+)[`"\]]?\s*\(',
    re.IGNORECASE,
)
_ALEMBIC_MIGRATION = re.compile(
    r'def\s+upgrade\s*\(\s*\)',
)


class DatabaseDependencyGraphBuilder:
    """
    Builds the Database Dependency Graph.

    Args:
        project_path: Root directory of the project.
    """

    def __init__(self, project_path: Path) -> None:
        self._project_path = project_path
        self._graph = DependencyGraph(
            name="Database Dependency Graph",
            graph_type="database",
        )

    def build(self) -> DependencyGraph:
        """Build the Database Dependency Graph."""
        logger.info(
            "database_graph_building",
            project_path=str(self._project_path),
        )

        self._discover_python_models()
        self._discover_sql_schemas()
        self._discover_migrations()

        logger.info(
            "database_graph_built",
            node_count=len(self._graph.nodes),
            edge_count=len(self._graph.edges),
        )

        return self._graph

    def _discover_python_models(self) -> None:
        """Discover SQLAlchemy and Django models."""
        python_files = [
            f for f in self._project_path.rglob("*.py")
            if not self._should_skip(f)
        ][:100]

        for file_path in python_files:
            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
                rel_path = str(
                    file_path.relative_to(self._project_path)
                )

                # SQLAlchemy models
                for match in _SQLALCHEMY_TABLE.finditer(content):
                    table_name = match.group(1)
                    if self._is_valid_table_name(table_name):
                        node_id = f"table:{table_name.lower()}"
                        self._graph.add_node(GraphNode(
                            id=node_id,
                            label=table_name,
                            node_type=DatabaseNodeType.TABLE.value,
                            file_path=rel_path,
                            metadata={
                                "orm": "sqlalchemy",
                                "class_name": table_name,
                            },
                        ))

                # SQLAlchemy foreign keys
                for match in _SQLALCHEMY_FK.finditer(content):
                    ref_table = match.group(1)
                    # Add edge from current file's models to referenced table
                    for sa_match in _SQLALCHEMY_TABLE.finditer(content):
                        source_table = sa_match.group(1)
                        if self._is_valid_table_name(source_table):
                            source_id = f"table:{source_table.lower()}"
                            target_id = f"table:{ref_table.lower()}"
                            if target_id not in self._graph.nodes:
                                self._graph.add_node(GraphNode(
                                    id=target_id,
                                    label=ref_table,
                                    node_type=DatabaseNodeType.TABLE.value,
                                ))
                            self._graph.add_edge(GraphEdge(
                                source_id=source_id,
                                target_id=target_id,
                                edge_type=DatabaseEdgeType.FOREIGN_KEY.value,
                            ))

                # Django models
                for match in _DJANGO_MODEL.finditer(content):
                    model_name = match.group(1)
                    if self._is_valid_table_name(model_name):
                        node_id = f"table:{model_name.lower()}"
                        self._graph.add_node(GraphNode(
                            id=node_id,
                            label=model_name,
                            node_type=DatabaseNodeType.TABLE.value,
                            file_path=rel_path,
                            metadata={"orm": "django"},
                        ))

            except (OSError, PermissionError):
                continue

    def _discover_sql_schemas(self) -> None:
        """Discover tables from raw SQL files."""
        sql_files = [
            f for f in self._project_path.rglob("*.sql")
            if not self._should_skip(f)
        ][:30]

        for file_path in sql_files:
            try:
                content = file_path.read_text(
                    encoding="utf-8", errors="ignore"
                )
                rel_path = str(
                    file_path.relative_to(self._project_path)
                )

                for match in _SQL_CREATE_TABLE.finditer(content):
                    table_name = match.group(1)
                    if self._is_valid_table_name(table_name):
                        node_id = f"table:{table_name.lower()}"
                        self._graph.add_node(GraphNode(
                            id=node_id,
                            label=table_name,
                            node_type=DatabaseNodeType.TABLE.value,
                            file_path=rel_path,
                            metadata={"source": "sql_schema"},
                        ))

                for match in _SQL_FK.finditer(content):
                    ref_table = match.group(1)
                    ref_id = f"table:{ref_table.lower()}"
                    if ref_id not in self._graph.nodes:
                        self._graph.add_node(GraphNode(
                            id=ref_id,
                            label=ref_table,
                            node_type=DatabaseNodeType.TABLE.value,
                        ))

            except (OSError, PermissionError):
                continue

    def _discover_migrations(self) -> None:
        """Discover and index migration files."""
        migration_patterns = [
            "**/migrations/*.py",
            "**/alembic/versions/*.py",
            "**/db/migrate/*.rb",
        ]

        for pattern in migration_patterns:
            for file_path in self._project_path.glob(pattern):
                if self._should_skip(file_path):
                    continue
                try:
                    content = file_path.read_text(
                        encoding="utf-8", errors="ignore"
                    )
                    if _ALEMBIC_MIGRATION.search(content):
                        node_id = f"migration:{file_path.stem}"
                        self._graph.add_node(GraphNode(
                            id=node_id,
                            label=file_path.name,
                            node_type=DatabaseNodeType.MIGRATION.value,
                            file_path=str(
                                file_path.relative_to(self._project_path)
                            ),
                            metadata={"source": "alembic"},
                        ))
                except (OSError, PermissionError):
                    continue

    def _is_valid_table_name(self, name: str) -> bool:
        """Filter out non-table class names."""
        invalid = {
            "Base", "Model", "AbstractModel", "TimestampedModel",
            "SoftDeleteModel", "BaseModel", "DeclarativeBase",
        }
        return name not in invalid and len(name) > 2

    def _should_skip(self, file_path: Path) -> bool:
        skip_dirs = {
            ".git", ".venv", "venv", "node_modules",
            "__pycache__", "dist", "build", "htmlcov",
        }
        return any(part in skip_dirs for part in file_path.parts)
