"""Unit tests for Retry Manager."""
import pytest
from aiqe.gateway.retry import RetryConfig, RetryManager
from aiqe.shared.exceptions import ProviderError


class TestRetryConfig:
    def test_zero_delay_for_first_attempt(self):
        config = RetryConfig(base_delay_seconds=2.0)
        assert config.delay_for_attempt(0) == 0.0

    def test_positive_delay_for_subsequent_attempts(self):
        config = RetryConfig(base_delay_seconds=1.0, jitter_factor=0.0)
        delay = config.delay_for_attempt(1)
        assert delay > 0

    def test_delay_respects_max(self):
        config = RetryConfig(
            base_delay_seconds=10.0,
            max_delay_seconds=5.0,
            jitter_factor=0.0,
        )
        for attempt in range(10):
            delay = config.delay_for_attempt(attempt)
            assert delay <= 5.5  # Allow small jitter overhead


class TestRetryManager:
    @pytest.mark.asyncio
    async def test_succeeds_on_first_try(self):
        manager = RetryManager(RetryConfig(max_attempts=3))
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await manager.execute_with_retry(operation)
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retries_on_provider_error(self):
        manager = RetryManager(RetryConfig(
            max_attempts=3,
            base_delay_seconds=0.001,
        ))
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ProviderError(
                    "rate limited",
                    provider="openai",
                    status_code=429,
                )
            return "success"

        result = await manager.execute_with_retry(operation)
        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_no_retry_on_400(self):
        manager = RetryManager(RetryConfig(max_attempts=3))
        call_count = 0

        async def operation():
            nonlocal call_count
            call_count += 1
            raise ProviderError(
                "bad request",
                provider="openai",
                status_code=400,
            )

        with pytest.raises(ProviderError):
            await manager.execute_with_retry(operation)

        assert call_count == 1  # No retry for 400

    @pytest.mark.asyncio
    async def test_raises_after_all_attempts(self):
        manager = RetryManager(RetryConfig(
            max_attempts=2,
            base_delay_seconds=0.001,
        ))

        async def always_fails():
            raise ProviderError(
                "rate limited",
                provider="openai",
                status_code=429,
            )

        with pytest.raises(ProviderError):
            await manager.execute_with_retry(always_fails)
