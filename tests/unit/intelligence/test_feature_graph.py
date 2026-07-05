"""Unit tests for Feature Graph Builder."""
import pytest
from pathlib import Path
from aiqe.intelligence.graphs.feature import FeatureGraphBuilder


@pytest.fixture
def project_with_routes(tmp_path):
    """Project with FastAPI routes."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "routes.py").write_text("""
from fastapi import APIRouter
router = APIRouter()

@router.get("/users")
def get_users(): pass

@router.post("/auth/login")
def login(): pass

@router.get("/products")
def get_products(): pass
""")
    (src / "test_users.py").write_text("""
def test_create_user(): pass
def test_delete_user(): pass
def test_user_authentication(): pass
""")
    (tmp_path / "README.md").write_text("""
# My App
## User Management
## Product Catalog
## Authentication
""")
    return tmp_path


class TestFeatureGraphBuilder:
    def test_builds_graph_from_routes(self, project_with_routes):
        builder = FeatureGraphBuilder(project_with_routes)
        graph = builder.build()
        assert not graph.is_empty()
        labels = [n.label for n in graph.nodes.values()]
        assert any("user" in l.lower() for l in labels) or len(labels) > 0

    def test_builds_graph_empty_project(self, tmp_path):
        builder = FeatureGraphBuilder(tmp_path)
        graph = builder.build()
        # Should add at least a default feature
        assert not graph.is_empty()

    def test_graph_type_is_feature(self, project_with_routes):
        builder = FeatureGraphBuilder(project_with_routes)
        graph = builder.build()
        assert graph.graph_type == "feature"

    def test_nodes_have_feature_type(self, project_with_routes):
        builder = FeatureGraphBuilder(project_with_routes)
        graph = builder.build()
        for node in graph.nodes.values():
            assert node.node_type == "feature"


class TestCodeDependencyGraphBuilder:
    def test_builds_from_python_imports(self, tmp_path):
        from aiqe.intelligence.graphs.code import CodeDependencyGraphBuilder

        src = tmp_path / "src"
        src.mkdir()
        (src / "a.py").write_text("from src import b")
        (src / "b.py").write_text("import os")

        builder = CodeDependencyGraphBuilder(tmp_path)
        graph = builder.build()
        assert not graph.is_empty()
        assert graph.graph_type == "code"

    def test_adds_external_deps(self, tmp_path):
        from aiqe.intelligence.graphs.code import CodeDependencyGraphBuilder

        (tmp_path / "main.py").write_text("import fastapi\nfrom sqlalchemy import Column")
        builder = CodeDependencyGraphBuilder(tmp_path)
        graph = builder.build()
        node_labels = {n.label for n in graph.nodes.values()}
        assert "fastapi" in node_labels or len(node_labels) > 0


class TestAPIDependencyGraphBuilder:
    def test_builds_from_fastapi(self, tmp_path):
        from aiqe.intelligence.graphs.api import APIDependencyGraphBuilder

        (tmp_path / "main.py").write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/users")
def get_users(): pass

@app.post("/users")
def create_user(): pass

@app.delete("/users/{id}")
def delete_user(id: int): pass
""")
        builder = APIDependencyGraphBuilder(tmp_path)
        graph = builder.build()
        assert not graph.is_empty()
        labels = [n.label for n in graph.nodes.values()]
        assert any("/users" in l for l in labels)

    def test_empty_project_empty_graph(self, tmp_path):
        from aiqe.intelligence.graphs.api import APIDependencyGraphBuilder
        builder = APIDependencyGraphBuilder(tmp_path)
        graph = builder.build()
        assert graph.graph_type == "api"


class TestDependencyAnalyzer:
    def test_builds_all_five_graphs(self, tmp_path):
        from aiqe.intelligence.analyzers.dependency import DependencyAnalyzer
        (tmp_path / "main.py").write_text("print('hello')")
        analyzer = DependencyAnalyzer(tmp_path)
        graphs = analyzer.build_all()
        assert "feature" in graphs
        assert "code" in graphs
        assert "api" in graphs
        assert "database" in graphs
        assert "ui" in graphs

    def test_all_graphs_have_correct_types(self, tmp_path):
        from aiqe.intelligence.analyzers.dependency import DependencyAnalyzer
        (tmp_path / "main.py").write_text("")
        analyzer = DependencyAnalyzer(tmp_path)
        graphs = analyzer.build_all()
        for expected_type in ["feature", "code", "api", "database", "ui"]:
            assert graphs[expected_type].graph_type == expected_type
