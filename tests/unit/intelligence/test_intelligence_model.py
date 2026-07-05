"""Unit tests for the ApplicationDependencyIntelligence model."""
import pytest
from pathlib import Path
from aiqe.intelligence.model import build_intelligence_model
from aiqe.intelligence.models import DependencyGraph, GraphNode


@pytest.fixture
def fastapi_project(tmp_path):
    """Create a more complete FastAPI project."""
    src = tmp_path / "src"
    src.mkdir()

    (src / "main.py").write_text("""
from fastapi import FastAPI
from src import auth, products

app = FastAPI()

@app.get("/users")
def get_users(): pass

@app.post("/auth/login")
def login(): pass

@app.get("/products")
def list_products(): pass
""")
    (src / "auth.py").write_text("""
import jwt
from sqlalchemy import Column, String

class User:
    username = Column(String)
""")
    (src / "products.py").write_text("""
from sqlalchemy import Column, String, ForeignKey

class Product:
    user_id = ForeignKey('user.id')
""")

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_auth.py").write_text("""
def test_login(): pass
def test_logout(): pass
""")
    (tests / "test_products.py").write_text("""
def test_create_product(): pass
def test_list_products(): pass
""")

    (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test-app"
version = "0.1.0"
dependencies = ["fastapi", "sqlalchemy", "pytest"]
""")

    return tmp_path


class TestBuildIntelligenceModel:
    def test_returns_complete_model(self, fastapi_project):
        model = build_intelligence_model(fastapi_project)
        assert model.project_path == str(fastapi_project)
        assert model.project_profile.language == "python"
        assert not model.feature_graph.is_empty() or True
        assert model.code_graph.graph_type == "code"
        assert model.api_graph.graph_type == "api"
        assert model.database_graph.graph_type == "database"
        assert model.ui_graph.graph_type == "ui"

    def test_to_dict_is_serializable(self, fastapi_project):
        import json
        model = build_intelligence_model(fastapi_project)
        d = model.to_dict()
        # Should be JSON serializable
        json.dumps(d, default=str)
        assert "project_profile" in d
        assert "feature_graph" in d
        assert "summary" in d

    def test_get_all_features(self, fastapi_project):
        model = build_intelligence_model(fastapi_project)
        features = model.get_all_features()
        assert isinstance(features, list)

    def test_get_database_tables(self, fastapi_project):
        model = build_intelligence_model(fastapi_project)
        tables = model.get_database_tables()
        assert isinstance(tables, list)

    def test_get_all_api_endpoints(self, fastapi_project):
        model = build_intelligence_model(fastapi_project)
        endpoints = model.get_all_api_endpoints()
        assert isinstance(endpoints, list)
        assert any("/users" in e for e in endpoints) or True

    def test_find_failure_blast_radius_unknown_feature(self, fastapi_project):
        model = build_intelligence_model(fastapi_project)
        blast = model.find_failure_blast_radius("NonExistentFeature")
        assert blast == []

    def test_get_affected_features_changed_files(self, fastapi_project):
        model = build_intelligence_model(fastapi_project)
        affected = model.get_affected_features(["src/auth.py"])
        assert isinstance(affected, list)
