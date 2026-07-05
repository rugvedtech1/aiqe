"""Unit tests for API Key Manager."""
import pytest
from pydantic import SecretStr
from aiqe.gateway.keys import APIKeyManager, ProviderKeyPool
from aiqe.shared.exceptions import AllProvidersExhaustedError, GatewayError


@pytest.fixture
def key_pool():
    return ProviderKeyPool(
        provider_name="openai",
        keys=[
            SecretStr("key-1-secret"),
            SecretStr("key-2-secret"),
            SecretStr("key-3-secret"),
        ],
    )


@pytest.fixture
def key_manager():
    manager = APIKeyManager()
    manager.register_provider("openai", [
        SecretStr("key-1"),
        SecretStr("key-2"),
    ])
    manager.register_provider("anthropic", [
        SecretStr("ant-key-1"),
    ])
    return manager


class TestProviderKeyPool:
    @pytest.mark.asyncio
    async def test_get_key_returns_value_and_index(self, key_pool):
        key, index = await key_pool.get_key()
        assert isinstance(key, str)
        assert isinstance(index, int)
        assert 0 <= index < 3

    @pytest.mark.asyncio
    async def test_failed_key_is_skipped(self, key_pool):
        # Mark key 0 as failed
        await key_pool.mark_key_failed(0, "rate_limit")
        # Should get key 1 or 2, not key 0
        for _ in range(10):
            _, index = await key_pool.get_key()
            assert index != 0

    @pytest.mark.asyncio
    async def test_all_keys_failed_raises(self, key_pool):
        for i in range(3):
            await key_pool.mark_key_failed(i, "rate_limit")
        with pytest.raises(AllProvidersExhaustedError):
            await key_pool.get_key()

    @pytest.mark.asyncio
    async def test_recovered_key_available_again(self, key_pool):
        await key_pool.mark_key_failed(0, "rate_limit")
        await key_pool.mark_key_recovered(0)
        key_pool._states[0].failed_at = None  # Force reset for test
        assert key_pool.available_key_count == 3

    def test_stats(self, key_pool):
        stats = key_pool.stats()
        assert stats["total_keys"] == 3
        assert stats["provider"] == "openai"


class TestAPIKeyManager:
    @pytest.mark.asyncio
    async def test_get_key_for_registered_provider(self, key_manager):
        key, index = await key_manager.get_key("openai")
        assert isinstance(key, str)
        assert "key" in key.lower()

    @pytest.mark.asyncio
    async def test_get_key_unregistered_provider_raises(self, key_manager):
        with pytest.raises(GatewayError, match="No API keys"):
            await key_manager.get_key("gemini")

    def test_has_provider(self, key_manager):
        assert key_manager.has_provider("openai")
        assert key_manager.has_provider("anthropic")
        assert not key_manager.has_provider("gemini")

    def test_available_providers(self, key_manager):
        providers = key_manager.available_providers()
        assert "openai" in providers
        assert "anthropic" in providers

    def test_stats(self, key_manager):
        stats = key_manager.stats()
        assert "openai" in stats
        assert "anthropic" in stats
