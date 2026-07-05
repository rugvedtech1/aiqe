"""
AIQE API Key Manager.

Manages multiple API keys per provider with automatic rotation.
Agents never access API keys directly — they go through the
gateway, which uses this manager to retrieve valid keys.

Key rotation strategy:
    Round-robin by default. When a key fails with a rate limit
    error (429) or authentication error (401), the manager marks
    it as temporarily failed and moves to the next key.
    After a cooldown period, failed keys are retried.

Security:
    Keys are stored as SecretStr from Pydantic — they never
    appear in repr(), logs, or error messages unless explicitly
    extracted with .get_secret_value().
    The Key Manager never logs key values. It logs key indices only.

Why multiple keys per provider?
    High-volume workflows can exhaust a single API key's rate limit.
    Multiple keys allow the gateway to continue working while one
    key is cooling down. Enterprise deployments with many concurrent
    workflows benefit significantly from this.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from pydantic import SecretStr

from aiqe.shared.exceptions import AllProvidersExhaustedError, GatewayError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

# How long a failed key is excluded from rotation before retrying
_KEY_COOLDOWN_SECONDS = 60.0


@dataclass
class KeyState:
    """
    Runtime state for a single API key.

    Attributes:
        index: Position in the key list (0-based).
        request_count: Total requests made with this key.
        error_count: Total errors encountered with this key.
        last_used: When this key was last used (monotonic time).
        failed_at: When this key last failed (monotonic time).
        is_cooling_down: Whether this key is in cooldown.
    """
    index: int
    request_count: int = 0
    error_count: int = 0
    last_used: float = 0.0
    failed_at: float | None = None

    @property
    def is_cooling_down(self) -> bool:
        """True if this key failed recently and should be skipped."""
        if self.failed_at is None:
            return False
        return (time.monotonic() - self.failed_at) < _KEY_COOLDOWN_SECONDS

    def mark_used(self) -> None:
        """Record that this key was just used."""
        self.request_count += 1
        self.last_used = time.monotonic()

    def mark_failed(self) -> None:
        """Record that this key just failed. Starts cooldown."""
        self.error_count += 1
        self.failed_at = time.monotonic()

    def mark_recovered(self) -> None:
        """Record that this key worked after a failure."""
        self.failed_at = None


class ProviderKeyPool:
    """
    Manages the key pool for a single AI provider.

    Maintains a list of API keys and rotates through them
    using round-robin, skipping keys that are cooling down.

    Args:
        provider_name: Name of the provider (e.g. "openai").
        keys: List of SecretStr API keys for this provider.
    """

    def __init__(
        self,
        provider_name: str,
        keys: list[SecretStr],
    ) -> None:
        self._provider = provider_name
        self._keys = keys
        self._states = [KeyState(index=i) for i in range(len(keys))]
        self._current_index = 0
        self._lock = asyncio.Lock()

    async def get_key(self) -> tuple[str, int]:
        """
        Get the next available API key using round-robin rotation.

        Skips keys that are currently cooling down. If all keys
        are cooling down, waits briefly and then raises.

        Returns:
            Tuple of (key_value, key_index).

        Raises:
            AllProvidersExhaustedError: If all keys are unavailable.
        """
        async with self._lock:
            available = [
                i for i, state in enumerate(self._states)
                if not state.is_cooling_down
            ]

            if not available:
                cooldown_ends = [
                    s.failed_at + _KEY_COOLDOWN_SECONDS
                    for s in self._states
                    if s.failed_at is not None
                ]
                soonest = min(cooldown_ends) if cooldown_ends else 0
                wait_seconds = max(0, soonest - time.monotonic())

                msg = (
                    f"All {len(self._keys)} API keys for provider "
                    f"'{self._provider}' are cooling down. "
                    f"Earliest recovery in {wait_seconds:.1f}s."
                )
                raise AllProvidersExhaustedError(msg)

            # Round-robin among available keys
            # Find the available key with the lowest request count
            # (least-used among available = better distribution)
            chosen_index = min(
                available,
                key=lambda i: self._states[i].request_count,
            )

            self._states[chosen_index].mark_used()
            key_value = self._keys[chosen_index].get_secret_value()

            logger.debug(
                "api_key_selected",
                provider=self._provider,
                key_index=chosen_index,
                available_keys=len(available),
            )

            return key_value, chosen_index

    async def mark_key_failed(
        self, key_index: int, error_type: str
    ) -> None:
        """
        Mark a key as failed and start its cooldown.

        Args:
            key_index: Index of the failed key.
            error_type: Type of error (rate_limit, auth_error, etc.)
        """
        async with self._lock:
            if 0 <= key_index < len(self._states):
                self._states[key_index].mark_failed()
                logger.warning(
                    "api_key_marked_failed",
                    provider=self._provider,
                    key_index=key_index,
                    error_type=error_type,
                    cooldown_seconds=_KEY_COOLDOWN_SECONDS,
                )

    async def mark_key_recovered(self, key_index: int) -> None:
        """Mark a previously failed key as recovered."""
        async with self._lock:
            if 0 <= key_index < len(self._states):
                self._states[key_index].mark_recovered()
                logger.info(
                    "api_key_recovered",
                    provider=self._provider,
                    key_index=key_index,
                )

    @property
    def available_key_count(self) -> int:
        """Number of keys not currently cooling down."""
        return sum(
            1 for s in self._states if not s.is_cooling_down
        )

    @property
    def total_key_count(self) -> int:
        """Total number of configured keys."""
        return len(self._keys)

    def stats(self) -> dict[str, Any]:
        """Key pool statistics for monitoring."""
        return {
            "provider": self._provider,
            "total_keys": self.total_key_count,
            "available_keys": self.available_key_count,
            "key_states": [
                {
                    "index": s.index,
                    "request_count": s.request_count,
                    "error_count": s.error_count,
                    "is_cooling_down": s.is_cooling_down,
                }
                for s in self._states
            ],
        }


class APIKeyManager:
    """
    Central manager for all provider API key pools.

    The single entry point for API key access in AIQE.
    Agents and provider adapters never import SecretStr or
    access config directly — they call this manager.

    Args:
        key_pools: Dict mapping provider name to ProviderKeyPool.
    """

    def __init__(
        self, key_pools: dict[str, ProviderKeyPool] | None = None
    ) -> None:
        self._pools: dict[str, ProviderKeyPool] = key_pools or {}

    def register_provider(
        self,
        provider_name: str,
        keys: list[SecretStr],
    ) -> None:
        """
        Register API keys for a provider.

        Args:
            provider_name: Provider identifier.
            keys: List of SecretStr API keys.
        """
        if not keys:
            logger.warning(
                "no_keys_registered",
                provider=provider_name,
            )
            return

        self._pools[provider_name] = ProviderKeyPool(
            provider_name=provider_name,
            keys=keys,
        )
        logger.info(
            "provider_keys_registered",
            provider=provider_name,
            key_count=len(keys),
        )

    async def get_key(
        self, provider_name: str
    ) -> tuple[str, int]:
        """
        Get an API key for the specified provider.

        Args:
            provider_name: The provider to get a key for.

        Returns:
            Tuple of (key_value, key_index).

        Raises:
            GatewayError: If the provider has no registered keys.
            AllProvidersExhaustedError: If all keys are cooling down.
        """
        pool = self._pools.get(provider_name)
        if pool is None:
            msg = (
                f"No API keys registered for provider '{provider_name}'. "
                f"Registered providers: {list(self._pools.keys())}. "
                f"Add keys to your .env file."
            )
            raise GatewayError(msg)

        return await pool.get_key()

    async def mark_key_failed(
        self,
        provider_name: str,
        key_index: int,
        error_type: str = "unknown",
    ) -> None:
        """Mark a key as failed in the appropriate pool."""
        pool = self._pools.get(provider_name)
        if pool:
            await pool.mark_key_failed(key_index, error_type)

    async def mark_key_recovered(
        self, provider_name: str, key_index: int
    ) -> None:
        """Mark a key as recovered in the appropriate pool."""
        pool = self._pools.get(provider_name)
        if pool:
            await pool.mark_key_recovered(key_index)

    def has_provider(self, provider_name: str) -> bool:
        """True if the provider has at least one registered key."""
        pool = self._pools.get(provider_name)
        return pool is not None and pool.available_key_count > 0

    def available_providers(self) -> list[str]:
        """List of providers with at least one available key."""
        return [
            name for name, pool in self._pools.items()
            if pool.available_key_count > 0
        ]

    def stats(self) -> dict[str, Any]:
        """Statistics across all provider key pools."""
        return {
            provider: pool.stats()
            for provider, pool in self._pools.items()
        }

    @classmethod
    def from_settings(cls) -> APIKeyManager:
        """
        Create an APIKeyManager from AIQE configuration.

        Reads all provider API keys from settings and registers them.
        Called once at application startup by the gateway factory.

        Returns:
            Configured APIKeyManager with all provider keys registered.
        """
        from aiqe.shared.config import get_settings
        settings = get_settings()
        gw = settings.gateway

        manager = cls()

        # Register each provider's keys
        if gw.openai_keys:
            manager.register_provider("openai", list(gw.openai_keys))

        if gw.anthropic_keys:
            manager.register_provider("anthropic", list(gw.anthropic_keys))

        if gw.gemini_keys:
            manager.register_provider("gemini", list(gw.gemini_keys))

        if gw.groq_keys:
            manager.register_provider("groq", list(gw.groq_keys))

        if gw.openrouter_keys:
            manager.register_provider("openrouter", list(gw.openrouter_keys))

        if gw.azure_openai_key:
            manager.register_provider(
                "azure", [gw.azure_openai_key]
            )

        # Ollama needs no key — register with a placeholder
        # so the router knows it's available
        from aiqe.shared.config import AIProvider
        if gw.default_provider == AIProvider.OLLAMA:
            from pydantic import SecretStr
            manager.register_provider(
                "ollama", [SecretStr("ollama-no-key")]
            )

        logger.info(
            "api_key_manager_initialized",
            registered_providers=list(manager._pools.keys()),
        )

        return manager
