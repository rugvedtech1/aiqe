"""
AIQE Dependency Intelligence Models.

Typed graph primitives for the Application Dependency
Intelligence Model (ADR-007).

Five graphs form the complete intelligence model:
    1. Feature Graph        — business features and relationships
    2. Code Dependency Graph — module/class/function imports
    3. API Dependency Graph  — endpoint consumers/dependencies
    4. Database Dependency Graph — table/view/migration relationships
    5. UI Navigation Graph   — screen/route/flow relationships

Design decisions:
    - Nodes and edges are frozen dataclasses (immutable).
    - Every node has a unique ID within its graph.
    - Every edge has a source node ID, target node ID, and edge type.
    - Graphs are adjacency-list-based (dict of node_id → list of edges).
    - All types are JSON-serialisable for memory store and persistence.

Why five separate graphs instead of one?
    Each graph answers a different question:
    Feature graph answers "which features are affected by this PR?"
    Code graph answers "which modules depend on the changed file?"
    API graph answers "which endpoints call this service?"
    Database graph answers "which tables use this migration?"
    UI graph answers "which screens can the user reach from here?"
    Mixing them into one graph makes queries complex and brittle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ==================================================
# NODE TYPES
# ==================================================

class FeatureNodeType(str, Enum):
    """Types of nodes in the Feature Graph."""
    FEATURE = "feature"
    MODULE = "module"
    COMPONENT = "component"
    SERVICE = "service"


class CodeNodeType(str, Enum):
    """Types of nodes in the Code Dependency Graph."""
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    FILE = "file"


class APINodeType(str, Enum):
    """Types of nodes in the API Dependency Graph."""
    ENDPOINT = "endpoint"
    SERVICE = "service"
    CLIENT = "client"
    MIDDLEWARE = "middleware"


class DatabaseNodeType(str, Enum):
    """Types of nodes in the Database Dependency Graph."""
    TABLE = "table"
    VIEW = "view"
    MIGRATION = "migration"
    INDEX = "index"
    PROCEDURE = "procedure"


class UINodeType(str, Enum):
    """Types of nodes in the UI Navigation Graph."""
    SCREEN = "screen"
    ROUTE = "route"
    COMPONENT = "component"
    MODAL = "modal"
    LAYOUT = "layout"


# ==================================================
# EDGE TYPES
# ==================================================

class FeatureEdgeType(str, Enum):
    """Relationship types in the Feature Graph."""
    DEPENDS_ON = "depends_on"
    INCLUDES = "includes"
    EXTENDS = "extends"
    CONFLICTS_WITH = "conflicts_with"


class CodeEdgeType(str, Enum):
    """Relationship types in the Code Dependency Graph."""
    IMPORTS = "imports"
    INHERITS = "inherits"
    CALLS = "calls"
    INSTANTIATES = "instantiates"
    EXPORTS = "exports"


class APIEdgeType(str, Enum):
    """Relationship types in the API Dependency Graph."""
    CALLS = "calls"
    AUTHENTICATED_BY = "authenticated_by"
    RATE_LIMITED_BY = "rate_limited_by"
    RETURNS = "returns"
    DEPENDS_ON = "depends_on"


class DatabaseEdgeType(str, Enum):
    """Relationship types in the Database Dependency Graph."""
    FOREIGN_KEY = "foreign_key"
    REFERENCES = "references"
    INDEXES = "indexes"
    APPLIED_BY = "applied_by"
    DEPENDS_ON = "depends_on"


class UIEdgeType(str, Enum):
    """Relationship types in the UI Navigation Graph."""
    NAVIGATES_TO = "navigates_to"
    RENDERS = "renders"
    REQUIRES_AUTH = "requires_auth"
    REDIRECTS_TO = "redirects_to"
    MODAL_OPENS = "modal_opens"


# ==================================================
# BASE GRAPH PRIMITIVES
# ==================================================

@dataclass(frozen=True)
class GraphNode:
    """
    A node in any dependency graph.

    Attributes:
        id: Unique identifier within its graph.
        label: Human-readable display name.
        node_type: What type of entity this node represents.
        file_path: Source file where this entity is defined.
        line_number: Line number in the source file (if applicable).
        metadata: Additional type-specific data.
    """
    id: str
    label: str
    node_type: str
    file_path: str = ""
    line_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "node_type": self.node_type,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class GraphEdge:
    """
    A directed edge between two nodes in a dependency graph.

    Attributes:
        source_id: ID of the source node.
        target_id: ID of the target node.
        edge_type: What kind of relationship this edge represents.
        weight: Strength of the relationship (0.0-1.0).
        metadata: Additional edge-specific data.
    """
    source_id: str
    target_id: str
    edge_type: str
    weight: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
            "weight": self.weight,
            "metadata": self.metadata,
        }


@dataclass
class DependencyGraph:
    """
    A directed dependency graph.

    Generic graph container used by all five graph types.
    Provides common operations: add nodes/edges, find paths,
    get dependents, get dependencies.

    Attributes:
        name: Human-readable graph name.
        graph_type: Which of the five graph types this is.
        nodes: Dict of node_id → GraphNode.
        edges: List of all directed edges.
        metadata: Additional graph-level data.
    """
    name: str
    graph_type: str
    nodes: dict[str, GraphNode] = field(default_factory=dict)
    edges: list[GraphEdge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_node(self, node: GraphNode) -> None:
        """Add a node. Silently ignores duplicate IDs."""
        if node.id not in self.nodes:
            self.nodes[node.id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        """
        Add a directed edge.

        Skips if source or target node does not exist.
        Skips duplicate edges (same source, target, and type).
        """
        if edge.source_id not in self.nodes:
            return
        if edge.target_id not in self.nodes:
            return
        for existing in self.edges:
            if (existing.source_id == edge.source_id and
                    existing.target_id == edge.target_id and
                    existing.edge_type == edge.edge_type):
                return
        self.edges.append(edge)

    def get_node(self, node_id: str) -> GraphNode | None:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def get_dependencies(self, node_id: str) -> list[GraphNode]:
        """
        Get all nodes that the given node depends on.
        (nodes this node has outgoing edges to)
        """
        dep_ids = {
            e.target_id for e in self.edges
            if e.source_id == node_id
        }
        return [self.nodes[nid] for nid in dep_ids if nid in self.nodes]

    def get_dependents(self, node_id: str) -> list[GraphNode]:
        """
        Get all nodes that depend on the given node.
        (nodes that have incoming edges from node_id)
        """
        dep_ids = {
            e.source_id for e in self.edges
            if e.target_id == node_id
        }
        return [self.nodes[nid] for nid in dep_ids if nid in self.nodes]

    def find_affected_nodes(self, changed_node_id: str) -> list[str]:
        """
        Find all nodes transitively affected by a change to the given node.

        Uses BFS to find all downstream dependents.
        Used by Test Strategy to determine test scope.

        Args:
            changed_node_id: The node that changed.

        Returns:
            List of affected node IDs in BFS order.
        """
        visited: set[str] = set()
        queue = [changed_node_id]
        affected = []

        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)

            dependents = self.get_dependents(current)
            for dep in dependents:
                if dep.id not in visited:
                    affected.append(dep.id)
                    queue.append(dep.id)

        return affected

    def find_path(
        self,
        source_id: str,
        target_id: str,
    ) -> list[str] | None:
        """
        Find the shortest path between two nodes using BFS.

        Args:
            source_id: Starting node ID.
            target_id: Destination node ID.

        Returns:
            List of node IDs forming the path, or None if no path exists.
        """
        if source_id not in self.nodes or target_id not in self.nodes:
            return None

        visited = {source_id}
        queue = [[source_id]]

        while queue:
            path = queue.pop(0)
            current = path[-1]

            if current == target_id:
                return path

            for dep in self.get_dependencies(current):
                if dep.id not in visited:
                    visited.add(dep.id)
                    queue.append(path + [dep.id])

        return None

    def is_empty(self) -> bool:
        """True if this graph has no nodes."""
        return len(self.nodes) == 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize this graph for memory store and persistence."""
        return {
            "name": self.name,
            "graph_type": self.graph_type,
            "nodes": {
                nid: node.to_dict()
                for nid, node in self.nodes.items()
            },
            "edges": [e.to_dict() for e in self.edges],
            "metadata": self.metadata,
            "node_count": len(self.nodes),
            "edge_count": len(self.edges),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DependencyGraph:
        """Deserialize a graph from a dict."""
        graph = cls(
            name=data.get("name", ""),
            graph_type=data.get("graph_type", ""),
            metadata=data.get("metadata", {}),
        )
        for nid, node_data in data.get("nodes", {}).items():
            graph.nodes[nid] = GraphNode(
                id=node_data["id"],
                label=node_data["label"],
                node_type=node_data["node_type"],
                file_path=node_data.get("file_path", ""),
                line_number=node_data.get("line_number", 0),
                metadata=node_data.get("metadata", {}),
            )
        for edge_data in data.get("edges", []):
            graph.edges.append(GraphEdge(
                source_id=edge_data["source_id"],
                target_id=edge_data["target_id"],
                edge_type=edge_data["edge_type"],
                weight=edge_data.get("weight", 1.0),
                metadata=edge_data.get("metadata", {}),
            ))
        return graph

    def __repr__(self) -> str:
        return (
            f"DependencyGraph("
            f"type={self.graph_type!r}, "
            f"nodes={len(self.nodes)}, "
            f"edges={len(self.edges)})"
        )
