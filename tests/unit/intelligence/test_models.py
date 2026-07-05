"""Unit tests for dependency graph models."""
import pytest
from aiqe.intelligence.models import (
    DependencyGraph,
    GraphEdge,
    GraphNode,
    CodeEdgeType,
    CodeNodeType,
)


@pytest.fixture
def simple_graph():
    g = DependencyGraph(name="Test", graph_type="code")
    g.add_node(GraphNode(id="a", label="Module A", node_type="file"))
    g.add_node(GraphNode(id="b", label="Module B", node_type="file"))
    g.add_node(GraphNode(id="c", label="Module C", node_type="file"))
    g.add_edge(GraphEdge(source_id="a", target_id="b", edge_type="imports"))
    g.add_edge(GraphEdge(source_id="b", target_id="c", edge_type="imports"))
    return g


class TestDependencyGraph:
    def test_add_node(self, simple_graph):
        assert "a" in simple_graph.nodes
        assert simple_graph.nodes["a"].label == "Module A"

    def test_duplicate_node_ignored(self, simple_graph):
        initial_count = len(simple_graph.nodes)
        simple_graph.add_node(GraphNode(
            id="a", label="Duplicate A", node_type="file"
        ))
        assert len(simple_graph.nodes) == initial_count

    def test_edge_requires_both_nodes(self):
        g = DependencyGraph(name="T", graph_type="code")
        g.add_node(GraphNode(id="x", label="X", node_type="file"))
        g.add_edge(GraphEdge(
            source_id="x", target_id="nonexistent",
            edge_type="imports"
        ))
        assert len(g.edges) == 0

    def test_duplicate_edge_ignored(self, simple_graph):
        initial_count = len(simple_graph.edges)
        simple_graph.add_edge(GraphEdge(
            source_id="a", target_id="b", edge_type="imports"
        ))
        assert len(simple_graph.edges) == initial_count

    def test_get_dependencies(self, simple_graph):
        deps = simple_graph.get_dependencies("a")
        assert len(deps) == 1
        assert deps[0].id == "b"

    def test_get_dependents(self, simple_graph):
        dependents = simple_graph.get_dependents("b")
        assert len(dependents) == 1
        assert dependents[0].id == "a"

    def test_find_affected_nodes(self, simple_graph):
        affected = simple_graph.find_affected_nodes("a")
        assert "b" in affected
        assert "c" in affected

    def test_find_path(self, simple_graph):
        path = simple_graph.find_path("a", "c")
        assert path == ["a", "b", "c"]

    def test_find_path_no_path(self, simple_graph):
        path = simple_graph.find_path("c", "a")
        assert path is None

    def test_to_dict_and_from_dict(self, simple_graph):
        d = simple_graph.to_dict()
        assert d["graph_type"] == "code"
        assert d["node_count"] == 3
        assert d["edge_count"] == 2

        restored = DependencyGraph.from_dict(d)
        assert len(restored.nodes) == 3
        assert len(restored.edges) == 2

    def test_is_empty(self):
        g = DependencyGraph(name="Empty", graph_type="feature")
        assert g.is_empty()


class TestGraphNode:
    def test_construction(self):
        node = GraphNode(
            id="test_id",
            label="Test Node",
            node_type="file",
            file_path="src/test.py",
            line_number=42,
        )
        assert node.id == "test_id"
        assert node.line_number == 42

    def test_to_dict(self):
        node = GraphNode(
            id="n1", label="Node 1", node_type="module"
        )
        d = node.to_dict()
        assert d["id"] == "n1"
        assert d["label"] == "Node 1"


class TestGraphEdge:
    def test_to_dict(self):
        edge = GraphEdge(
            source_id="a",
            target_id="b",
            edge_type=CodeEdgeType.IMPORTS.value,
            weight=0.8,
        )
        d = edge.to_dict()
        assert d["source_id"] == "a"
        assert d["weight"] == 0.8
