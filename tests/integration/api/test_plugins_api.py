"""Integration tests for plugin API endpoints."""
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


class TestPluginsCapabilitiesAPI:
    @pytest.mark.asyncio
    async def test_list_capabilities_returns_all(self, client):
        response = await client.get("/api/v1/plugins/capabilities")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 20
        assert len(data["capabilities"]) == data["total"]

    @pytest.mark.asyncio
    async def test_list_capabilities_filter_by_group(self, client):
        response = await client.get(
            "/api/v1/plugins/capabilities",
            params={"group": "browser"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] > 0
        for cap in data["capabilities"]:
            assert cap["group"] == "browser"

    @pytest.mark.asyncio
    async def test_list_capabilities_restricted_only(self, client):
        response = await client.get(
            "/api/v1/plugins/capabilities",
            params={"restricted_only": True},
        )
        assert response.status_code == 200
        data = response.json()
        for cap in data["capabilities"]:
            assert cap["is_restricted"] is True

    @pytest.mark.asyncio
    async def test_list_capabilities_invalid_group(self, client):
        response = await client.get(
            "/api/v1/plugins/capabilities",
            params={"group": "invalid_group"},
        )
        assert response.status_code == 422


class TestPluginsListAPI:
    @pytest.mark.asyncio
    async def test_list_plugins_empty(self, client):
        response = await client.get("/api/v1/plugins")
        assert response.status_code == 200
        data = response.json()
        assert "plugins" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_nonexistent_plugin(self, client):
        response = await client.get("/api/v1/plugins/nonexistent-plugin")
        assert response.status_code == 404
        data = response.json()
        assert data["detail"]["error"] == "plugin_not_found"


class TestValidateManifestAPI:
    VALID_MANIFEST = {
        "plugin": {
            "name": "api-test-plugin",
            "version": "1.0.0",
            "description": "A test plugin.",
            "author": "Test",
            "plugin_type": "browser",
            "min_aiqe_version": "0.1.0",
            "capabilities": {
                "required": [
                    "browser.navigate",
                    "browser.screenshots",
                ]
            },
            "entry_point": {
                "module": "test.module",
                "class_name": "TestPlugin",
            },
        }
    }

    @pytest.mark.asyncio
    async def test_validate_valid_manifest(self, client):
        response = await client.post(
            "/api/v1/plugins/validate",
            json={"manifest": self.VALID_MANIFEST},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["plugin_name"] == "api-test-plugin"
        assert data["capability_count"] == 2
        assert data["has_restricted"] is False

    @pytest.mark.asyncio
    async def test_validate_invalid_manifest_unknown_capability(self, client):
        invalid = {
            "plugin": {
                **self.VALID_MANIFEST["plugin"],
                "capabilities": {
                    "required": ["nonexistent.capability"]
                },
            }
        }
        response = await client.post(
            "/api/v1/plugins/validate",
            json={"manifest": invalid},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is False
        assert len(data["errors"]) > 0

    @pytest.mark.asyncio
    async def test_validate_restricted_capability_adds_warning(self, client):
        restricted = {
            "plugin": {
                **self.VALID_MANIFEST["plugin"],
                "capabilities": {
                    "required": ["system.execute_shell"]
                },
            }
        }
        response = await client.post(
            "/api/v1/plugins/validate",
            json={"manifest": restricted},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_valid"] is True
        assert data["has_restricted"] is True
        assert len(data["warnings"]) > 0
