"""
AIQE Retry Manager.

Implements exponential backoff with jitter for AI provider
requests. Handles provider failover — if all keys for one
provider fail, the retry manager switches to the next available
provider automatically.

Retry strategy:
    1. Try current provider with current key.
    2. If rate limited (429): mark key failed, try next key same provider.
    3. If all keys for provider are cooling down: switch to next provider.
    4. If all providers exhausted: raise AllProvidersExhaustedError.
    5. Between retries: exponential backoff with jitter.

What is NOT retried:
    - 400 Bad Request (prompt is malformed — retrying won't help)
    - 401 Auth errors (key is invalid — retrying won't help, mark failed)

This implements the Retry Manager from ADR-005 Phase 1.
"""

from __future__ import annotations

import asyncio
import random
from typing import Any, Awaitable, Callable, TypeVar

from aiqe.shared.exceptions import AllProvidersExhaustedError, ProviderError
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import Timer

logger = get_logger(__name__)

T = TypeVar("T")

# Status codes that should NOT be retried
_NO_RETRY_STATUS_CODES = {400, 401, 403, 404, 422}


class RetryConfig:
    """
    Configuration for retry behaviour.

    Attributes:
        max_attempts: Maximum total attempts (including first try).
        base_delay_seconds: Initial backoff delay.
        max_delay_seconds: Maximum backoff delay cap.
        exponential_base: Backoff growth factor.
        jitter_factor: Fraction of delay to randomise (0.0-1.0).
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay_seconds: float = 1.0,
        max_delay_seconds: float = 60.0,
        exponential_base: float = 2.0,
        jitter_factor: float = 0.1,
    ) -> None:
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.max_delay_seconds = max_delay_seconds
        self.exponential_base = exponential_base
        self.jitter_factor = jitter_factor

    def delay_for_attempt(self, attempt: int) -> float:
        """
        Calculate the delay before the given retry attempt.

        Args:
            attempt: 0-indexed attempt number (0 = no delay for first try).

        Returns:
            Delay in seconds with jitter applied.
        """
        if attempt == 0:
            return 0.0

        base = self.base_delay_seconds * (
            self.exponential_base ** (attempt - 1)
        )
        delay = min(base, self.max_delay_seconds)
        jitter = delay * self.jitter_factor * (2 * random.random() - 1)
        return max(0.0, delay + jitter)


class RetryManager:
    """
    Executes AI Gateway calls with retry and provider failover.

    Args:
        config: Retry configuration. Uses sensible defaults if not provided.
    """

    def __init__(self, config: RetryConfig | None = None) -> None:
        self._config = config or RetryConfig()

    async def execute_with_retry(
        self,
        operation: Callable[[], Awaitable[T]],
        operation_name: str = "ai_request",
        workflow_id: str = "",
    ) -> T:
        """
        Execute an async operation with retry logic.

        Args:
            operation: Async callable to execute and retry.
            operation_name: Name for logging purposes.
            workflow_id: Workflow context for audit logging.

        Returns:
            The result of the successful operation call.

        Raises:
            The last exception if all retry attempts are exhausted.
        """
        last_error: Exception | None = None

        for attempt in range(self._config.max_attempts):
            delay = self._config.delay_for_attempt(attempt)

            if delay > 0:
                logger.info(
                    "retry_waiting",
                    operation=operation_name,
                    attempt=attempt + 1,
                    max_attempts=self._config.max_attempts,
                    delay_seconds=round(delay, 2),
                    workflow_id=workflow_id,
                )
                await asyncio.sleep(delay)

            try:
                with Timer() as timer:
                    result = await operation()

                if attempt > 0:
                    logger.info(
                        "retry_succeeded",
                        operation=operation_name,
                        attempt=attempt + 1,
                        duration_seconds=timer.elapsed_seconds,
                        workflow_id=workflow_id,
                    )

                return result

            except ProviderError as e:
                last_error = e

                # Do not retry client errors that won't change
                if e.status_code in _NO_RETRY_STATUS_CODES:
                    logger.error(
                        "retry_not_applicable",
                        operation=operation_name,
                        status_code=e.status_code,
                        provider=e.provider,
                        workflow_id=workflow_id,
                    )
                    raise

                logger.warning(
                    "provider_error_will_retry",
                    operation=operation_name,
                    attempt=attempt + 1,
                    max_attempts=self._config.max_attempts,
                    provider=e.provider,
                    status_code=e.status_code,
                    error=e.message,
                    workflow_id=workflow_id,
                )

            except AllProvidersExhaustedError:
                # All keys cooling down — wait longer then try again
                last_error = AllProvidersExhaustedError(
                    "All providers exhausted"
                )
                logger.error(
                    "all_providers_exhausted",
                    operation=operation_name,
                    attempt=attempt + 1,
                    workflow_id=workflow_id,
                )
                if attempt < self._config.max_attempts - 1:
                    await asyncio.sleep(
                        min(30.0, self._config.max_delay_seconds)
                    )

            except Exception as e:
                last_error = e
                logger.error(
                    "unexpected_error_will_retry",
                    operation=operation_name,
                    attempt=attempt + 1,
                    error_type=type(e).__name__,
                    error=str(e),
                    workflow_id=workflow_id,
                )

        logger.error(
            "all_retries_exhausted",
            operation=operation_name,
            total_attempts=self._config.max_attempts,
            workflow_id=workflow_id,
            last_error=str(last_error),
        )

        if last_error:
            raise last_error

        raise GatewayError(
            f"Operation '{operation_name}' failed after "
            f"{self._config.max_attempts} attempts with no error recorded."
        )


from aiqe.shared.exceptions import GatewayError
