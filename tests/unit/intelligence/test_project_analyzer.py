"""Unit tests for ProjectAnalyzer."""
import pytest
from pathlib import Path
from aiqe.intelligence.analyzers.project import ProjectAnalyzer


@pytest.fixture
def python_project(tmp_path):
    """Create a minimal Python/FastAPI project."""
    (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test-project"
version = "0.1.0"
dependencies = [
    "fastapi>=0.111.0",
    "sqlalchemy>=2.0.0",
    "pytest>=8.0.0",
]
""")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/users")
def get_users():
    return []
""")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("""
def test_health():
    assert True
""")
    (tmp_path / "Dockerfile").write_text("FROM python:3.12")
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text("name: CI")
    return tmp_path


@pytest.fixture
def js_project(tmp_path):
    """Create a minimal JS/React project."""
    (tmp_path / "package.json").write_text("""
{
    "name": "test-app",
    "dependencies": {
        "react": "^18.0.0",
        "next": "^14.0.0"
    },
    "devDependencies": {
        "jest": "^29.0.0"
    }
}
""")
    (tmp_path / "next.config.js").write_text("module.exports = {}")
    (tmp_path / "pages").mkdir()
    (tmp_path / "pages" / "index.tsx").write_text("export default function Home() {}")
    return tmp_path


class TestProjectAnalyzer:
    def test_detects_python(self, python_project):
        analyzer = ProjectAnalyzer(python_project)
        profile = analyzer.analyze()
        assert profile.language == "python"
        assert profile.package_manager == "pip"

    def test_detects_fastapi_framework(self, python_project):
        analyzer = ProjectAnalyzer(python_project)
        profile = analyzer.analyze()
        assert profile.framework == "fastapi"

    def test_detects_pytest(self, python_project):
        analyzer = ProjectAnalyzer(python_project)
        profile = analyzer.analyze()
        assert profile.test_framework == "pytest"

    def test_detects_docker(self, python_project):
        analyzer = ProjectAnalyzer(python_project)
        profile = analyzer.analyze()
        assert profile.has_docker is True

    def test_detects_ci(self, python_project):
        analyzer = ProjectAnalyzer(python_project)
        profile = analyzer.analyze()
        assert profile.has_ci is True

    def test_collects_source_files(self, python_project):
        analyzer = ProjectAnalyzer(python_project)
        profile = analyzer.analyze()
        assert len(profile.source_files) > 0

    def test_collects_test_files(self, python_project):
        analyzer = ProjectAnalyzer(python_project)
        profile = analyzer.analyze()
        assert len(profile.test_files) > 0

    def test_detects_javascript(self, js_project):
        analyzer = ProjectAnalyzer(js_project)
        profile = analyzer.analyze()
        assert profile.language in {"javascript", "typescript"}

    def test_detects_nextjs(self, js_project):
        analyzer = ProjectAnalyzer(js_project)
        profile = analyzer.analyze()
        assert profile.framework == "nextjs"

    def test_detects_jest(self, js_project):
        analyzer = ProjectAnalyzer(js_project)
        profile = analyzer.analyze()
        assert profile.test_framework == "jest"

    def test_profile_to_dict(self, python_project):
        analyzer = ProjectAnalyzer(python_project)
        profile = analyzer.analyze()
        d = profile.to_dict()
        assert "language" in d
        assert "framework" in d
        assert "dependencies" in d
        assert isinstance(d["source_files"], list)


class TestProjectAnalyzerEmpty:
    def test_empty_directory(self, tmp_path):
        analyzer = ProjectAnalyzer(tmp_path)
        profile = analyzer.analyze()
        assert isinstance(profile.language, str)
        assert profile.file_count == 0
