"""Integration tests for workflow API endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from httpx import AsyncClient, ASGITransport
from aiqe.api.app import create_app
from aiqe.api.dependencies import get_repository_bundle, get_workflow_engine


@pytest.fixture
def mock_bundle():
    bundle = MagicMock()
    bundle.workflows.save = AsyncMock()
    bundle.workflows.find_by_id = AsyncMock(return_value=None)
    bundle.workflows.find_active = AsyncMock(return_value=[])
    bundle.bugs.find_by_workflow = AsyncMock(return_value=[])
    bundle.bugs.count_by_workflow = AsyncMock(return_value={})
    bundle.audit.find_by_workflow = AsyncMock(return_value=[])
    bundle.audit.append_batch = AsyncMock()
    return bundle


@pytest.fixture
def mock_engine(tmp_path):
    from aiqe.workflow.context import WorkflowContext
    from aiqe.workflow.events import WorkflowStatus

    context = WorkflowContext(
        trigger="manual",
        repository="owner/repo",
        branch="main",
    )
    context.workspace_path = tmp_path / context.id
    context.workspace_path.mkdir(parents=True)

    engine = MagicMock()
    engine.create_context = AsyncMock(return_value=context)
    engine.run = AsyncMock(return_value=context)
    return engine


@pytest.fixture
def app(mock_bundle, mock_engine):
    application = create_app()
    application.dependency_overrides[get_repository_bundle] = (
        lambda: mock_bundle
    )
    application.dependency_overrides[get_workflow_engine] = (
        lambda: mock_engine
    )
    return application


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


class TestWorkflowsAPI:
    @pytest.mark.asyncio
    async def test_create_workflow_returns_202(self, client, tmp_path):
        response = await client.post(
            "/api/v1/workflows",
            json={
                "project_path": str(tmp_path),
                "trigger": "manual",
                "repository": "owner/repo",
                "branch": "main",
                "dry_run": True,
            },
        )
        assert response.status_code == 202
        data = response.json()
        assert "id" in data
        assert data["trigger"] == "manual"

    @pytest.mark.asyncio
    async def test_create_workflow_invalid_path(self, client):
        response = await client.post(
            "/api/v1/workflows",
            json={
                "project_path": "/nonexistent/path/xyz",
                "trigger": "manual",
            },
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_workflow_not_found(self, client):
        response = await client.get(
            "/api/v1/workflows/nonexistent-id"
        )
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "workflow_not_found"

    @pytest.mark.asyncio
    async def test_list_workflows_empty(self, client):
        response = await client.get("/api/v1/workflows")
        assert response.status_code == 200
        data = response.json()
        assert data["workflows"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_list_workflow_bugs_not_found(self, client):
        response = await client.get(
            "/api/v1/workflows/nonexistent-id/bugs"
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_workflow_not_found(self, client, mock_bundle):
        mock_bundle.workflows.delete = AsyncMock(return_value=False)
        response = await client.delete(
            "/api/v1/workflows/nonexistent-id"
        )
        assert response.status_code == 404
