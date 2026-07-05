"""Integration tests for health endpoints."""
import pytest
from httpx import AsyncClient, ASGITransport
from aiqe.api.app import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


class TestHealthEndpoints:
    @pytest.mark.asyncio
    async def test_root_returns_api_info(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "AIQE API"
        assert "docs" in data
        assert "health" in data

    @pytest.mark.asyncio
    async def test_health_returns_healthy(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0-alpha"
        assert "uptime_seconds" in data
        assert data["uptime_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_health_has_security_headers(self, client):
        response = await client.get("/health")
        assert "x-content-type-options" in response.headers
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "x-frame-options" in response.headers
        assert response.headers["x-frame-options"] == "DENY"

    @pytest.mark.asyncio
    async def test_health_has_correlation_id(self, client):
        response = await client.get("/health")
        assert "x-correlation-id" in response.headers

    @pytest.mark.asyncio
    async def test_correlation_id_echoed_from_request(self, client):
        custom_id = "test-correlation-12345"
        response = await client.get(
            "/health",
            headers={"X-Correlation-ID": custom_id},
        )
        assert response.headers.get("x-correlation-id") == custom_id
