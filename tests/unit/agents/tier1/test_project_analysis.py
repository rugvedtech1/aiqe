"""Unit tests for Project Analysis Agent."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from aiqe.agents.project_analysis.agent import ProjectAnalysisAgent
from aiqe.agents.types import ProjectAnalysisInput, ProjectAnalysisOutput


@pytest.fixture
def python_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test-app"
version = "0.1.0"
dependencies = ["fastapi", "sqlalchemy", "pytest"]
""")
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/users")
def get_users(): pass

@app.post("/users")
def create_user(): pass
""")
    (src / "auth.py").write_text("""
import jwt
def verify_token(token): pass
""")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_app(): pass")
    (tmp_path / "Dockerfile").write_text("FROM python:3.12")
    return tmp_path


@pytest.fixture
def mock_memory():
    memory = MagicMock()
    memory.set = AsyncMock()
    memory.get = AsyncMock(return_value=None)
    return memory


class TestProjectAnalysisAgentClassVars:
    def test_name(self):
        assert ProjectAnalysisAgent.NAME == "project_analysis"

    def test_tier(self):
        assert ProjectAnalysisAgent.TIER == 1

    def test_dependencies(self):
        assert "orchestrator" in ProjectAnalysisAgent.DEPENDENCIES


class TestProjectAnalysisAgentExecution:
    @pytest.mark.asyncio
    async def test_detects_python_project(self, python_project, mock_memory):
        agent = ProjectAnalysisAgent(memory_store=mock_memory)
        input_data = ProjectAnalysisInput(
            workflow_id="wf_001",
            project_path=str(python_project),
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert output.language == "python"

    @pytest.mark.asyncio
    async def test_detects_fastapi_framework(self, python_project, mock_memory):
        agent = ProjectAnalysisAgent(memory_store=mock_memory)
        input_data = ProjectAnalysisInput(
            workflow_id="wf_001",
            project_path=str(python_project),
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.framework == "fastapi"

    @pytest.mark.asyncio
    async def test_detects_docker(self, python_project, mock_memory):
        agent = ProjectAnalysisAgent(memory_store=mock_memory)
        input_data = ProjectAnalysisInput(
            workflow_id="wf_001",
            project_path=str(python_project),
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.has_docker is True

    @pytest.mark.asyncio
    async def test_detects_api_routes(self, python_project, mock_memory):
        agent = ProjectAnalysisAgent(memory_store=mock_memory)
        input_data = ProjectAnalysisInput(
            workflow_id="wf_001",
            project_path=str(python_project),
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert len(output.routes) > 0

    @pytest.mark.asyncio
    async def test_writes_to_memory(self, python_project, mock_memory):
        agent = ProjectAnalysisAgent(memory_store=mock_memory)
        input_data = ProjectAnalysisInput(
            workflow_id="wf_001",
            project_path=str(python_project),
            dry_run=True,
        )
        await agent.run(input_data)
        assert mock_memory.set.call_count >= 3

    @pytest.mark.asyncio
    async def test_invalid_path_returns_error(self, mock_memory):
        agent = ProjectAnalysisAgent(memory_store=mock_memory)
        input_data = ProjectAnalysisInput(
            workflow_id="wf_001",
            project_path="/nonexistent/path",
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert output.success is False

    @pytest.mark.asyncio
    async def test_output_has_reasoning(self, python_project, mock_memory):
        agent = ProjectAnalysisAgent(memory_store=mock_memory)
        input_data = ProjectAnalysisInput(
            workflow_id="wf_001",
            project_path=str(python_project),
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert len(output.reasoning) > 0

    @pytest.mark.asyncio
    async def test_output_has_evidence(self, python_project, mock_memory):
        agent = ProjectAnalysisAgent(memory_store=mock_memory)
        input_data = ProjectAnalysisInput(
            workflow_id="wf_001",
            project_path=str(python_project),
            dry_run=True,
        )
        output = await agent.run(input_data)
        assert len(output.evidence) > 0

    @pytest.mark.asyncio
    async def test_ai_interpretation_called_when_gateway_provided(
        self, python_project, mock_memory
    ):
        mock_gateway = MagicMock()
        from aiqe.gateway.types import AIResponse
        mock_gateway.complete = AsyncMock(return_value=AIResponse(
            content=(
                "DESCRIPTION: A FastAPI REST API project.\n"
                "CRITICAL_AREAS: Authentication | API endpoints | Database\n"
                "RISK_PATTERNS: None detected\n"
                "CONFIDENCE: 0.92\n"
                "REASONING: Based on FastAPI framework with JWT auth."
            ),
            provider="openai",
            model="gpt-4o",
            total_tokens=250,
        ))

        agent = ProjectAnalysisAgent(
            memory_store=mock_memory,
            gateway=mock_gateway,
        )
        input_data = ProjectAnalysisInput(
            workflow_id="wf_001",
            project_path=str(python_project),
            dry_run=False,
        )
        output = await agent.run(input_data)
        assert output.success is True
        assert mock_gateway.complete.call_count == 1
        assert output.confidence >= 0.9
