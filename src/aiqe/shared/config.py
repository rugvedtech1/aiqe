"""
AIQE Configuration Management.

All configuration for AIQE is defined here using Pydantic Settings.
Configuration is loaded from environment variables and .env files.

Why Pydantic Settings?
    - Validates all config values at startup with clear error messages
    - Type-safe: every config value has a declared type
    - Supports .env files for local development
    - Supports environment variable overrides for CI/CD and Docker
    - Fails fast: if required config is missing, AIQE exits immediately
      with a helpful error rather than failing obscurely at runtime

Design decisions:
    - Sensitive values (API keys, passwords) use SecretStr so they
      never appear in repr() output, logs, or error messages
    - Configuration is divided into nested settings classes so each
      module can receive only the configuration it needs (dependency
      inversion — modules don't import the whole config object)
    - Default values are conservative: security features ON,
      verbose logging OFF in production, sandboxing ENABLED

Usage:
    from aiqe.shared.config import get_settings

    settings = get_settings()
    print(settings.database.mode)         # "sqlite"
    print(settings.gateway.default_provider)  # "openai"
    # API keys are SecretStr — access value explicitly:
    key = settings.gateway.openai_keys[0].get_secret_value()
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ==================================================
# ENUMERATIONS
# These prevent typos in config values — if you pass
# "Sqlite" instead of "sqlite", Pydantic rejects it.
# ==================================================


class Environment(str, Enum):
    """AIQE deployment environment."""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class LogLevel(str, Enum):
    """Valid log levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class DatabaseMode(str, Enum):
    """Database backend selection. See ADR-002."""
    SQLITE = "sqlite"
    POSTGRES = "postgres"


class AIProvider(str, Enum):
    """Supported AI providers. See ADR-005."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROQ = "groq"
    OPENROUTER = "openrouter"
    AZURE = "azure"
    OLLAMA = "ollama"


# ==================================================
# NESTED SETTINGS CLASSES
# Each class handles one domain of configuration.
# ==================================================


class CoreSettings(BaseSettings):
    """Core AIQE settings."""

    model_config = SettingsConfigDict(
        env_prefix="AIQE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = Field(
        default=Environment.DEVELOPMENT,
        description="Deployment environment.",
    )
    log_level: LogLevel = Field(
        default=LogLevel.INFO,
        description="Minimum log level to emit.",
    )
    workspace_dir: Path = Field(
        default=Path(".aiqe"),
        description="Directory for workflow contexts, checkpoints, and artifacts.",
    )
    enterprise_mode: bool = Field(
        default=False,
        description="Enable enterprise features (multi-node, org policies).",
    )
    max_concurrent_workflows: int = Field(
        default=5,
        ge=1,
        le=100,
        description="Maximum number of workflows that may run simultaneously.",
    )
    checkpoint_enabled: bool = Field(
        default=True,
        description="Enable workflow checkpointing for crash recovery.",
    )
    audit_log_enabled: bool = Field(
        default=True,
        description="Enable the structured audit trail. See ADR-012.",
    )

    @field_validator("workspace_dir", mode="before")
    @classmethod
    def expand_workspace_path(cls, v: str | Path) -> Path:
        """Expand ~ and environment variables in workspace path."""
        return Path(v).expanduser().resolve()


class DatabaseSettings(BaseSettings):
    """Database configuration. See ADR-002."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mode: DatabaseMode = Field(
        default=DatabaseMode.SQLITE,
        alias="AIQE_DATABASE_MODE",
        description="Database backend: sqlite (local) or postgres (enterprise).",
    )
    sqlite_path: Path = Field(
        default=Path(".aiqe/aiqe.db"),
        alias="AIQE_SQLITE_PATH",
        description="Path to SQLite database file.",
    )

    # PostgreSQL settings (required when mode=postgres)
    postgres_host: str = Field(
        default="localhost",
        alias="POSTGRES_HOST",
    )
    postgres_port: int = Field(
        default=5432,
        alias="POSTGRES_PORT",
        ge=1,
        le=65535,
    )
    postgres_db: str = Field(
        default="aiqe",
        alias="POSTGRES_DB",
    )
    postgres_user: str = Field(
        default="",
        alias="POSTGRES_USER",
    )
    postgres_password: SecretStr = Field(
        default=SecretStr(""),
        alias="POSTGRES_PASSWORD",
    )

    @model_validator(mode="after")
    def validate_postgres_config(self) -> DatabaseSettings:
        """Ensure Postgres settings are provided when mode is postgres."""
        if self.mode == DatabaseMode.POSTGRES:
            missing = []
            if not self.postgres_user:
                missing.append("POSTGRES_USER")
            if not self.postgres_password.get_secret_value():
                missing.append("POSTGRES_PASSWORD")
            if missing:
                msg = (
                    f"AIQE_DATABASE_MODE=postgres requires: "
                    f"{', '.join(missing)}"
                )
                raise ValueError(msg)
        return self

    @property
    def connection_url(self) -> str:
        """
        Build the database connection URL from configured settings.

        Returns async-compatible URLs:
        - SQLite: sqlite+aiosqlite:///path/to/aiqe.db
        - Postgres: postgresql+asyncpg://user:pass@host:port/db

        The password is retrieved from SecretStr and never logged.
        """
        if self.mode == DatabaseMode.SQLITE:
            return f"sqlite+aiosqlite:///{self.sqlite_path}"
        password = self.postgres_password.get_secret_value()
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


class GatewaySettings(BaseSettings):
    """AI Gateway configuration. See ADR-005."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    default_provider: AIProvider = Field(
        default=AIProvider.OPENAI,
        alias="AIQE_DEFAULT_PROVIDER",
    )
    default_model: str = Field(
        default="gpt-4o",
        alias="AIQE_DEFAULT_MODEL",
    )
    max_tokens: int = Field(
        default=4096,
        alias="AIQE_MAX_TOKENS",
        ge=1,
        le=128000,
    )
    temperature: float = Field(
        default=0.1,
        alias="AIQE_TEMPERATURE",
        ge=0.0,
        le=2.0,
    )

    # Multi-key support — up to 3 keys per provider for rotation
    openai_keys: list[SecretStr] = Field(
        default_factory=list,
        description="OpenAI API keys for rotation.",
    )
    anthropic_keys: list[SecretStr] = Field(
        default_factory=list,
        description="Anthropic API keys for rotation.",
    )
    gemini_keys: list[SecretStr] = Field(
        default_factory=list,
        description="Google Gemini API keys for rotation.",
    )
    groq_keys: list[SecretStr] = Field(
        default_factory=list,
        description="Groq API keys for rotation.",
    )
    openrouter_keys: list[SecretStr] = Field(
        default_factory=list,
        description="OpenRouter API keys for rotation.",
    )

    # Azure OpenAI
    azure_openai_key: SecretStr | None = Field(
        default=None,
        alias="AZURE_OPENAI_API_KEY",
    )
    azure_openai_endpoint: str | None = Field(
        default=None,
        alias="AZURE_OPENAI_ENDPOINT",
    )
    azure_openai_api_version: str = Field(
        default="2024-02-01",
        alias="AZURE_OPENAI_API_VERSION",
    )

    # Ollama (local models)
    ollama_base_url: str = Field(
        default="http://localhost:11434",
        alias="OLLAMA_BASE_URL",
    )

    @model_validator(mode="after")
    def validate_at_least_one_provider(self) -> GatewaySettings:
        """
        Ensure at least one AI provider is configured.

        AIQE cannot function without an AI provider. This check runs
        at startup so the failure is immediate and clear, not discovered
        at the first agent execution attempt.
        """
        has_key = any([
            self.openai_keys,
            self.anthropic_keys,
            self.gemini_keys,
            self.groq_keys,
            self.openrouter_keys,
            self.azure_openai_key,
            # Ollama needs no key
            self.default_provider == AIProvider.OLLAMA,
        ])
        if not has_key:
            msg = (
                "At least one AI provider API key must be configured. "
                "Set OPENAI_API_KEY_1, ANTHROPIC_API_KEY_1, or another "
                "provider key in your .env file. See .env.example."
            )
            raise ValueError(msg)
        return self


class SecuritySettings(BaseSettings):
    """Security configuration. See ADR-003, ADR-011."""

    model_config = SettingsConfigDict(
        env_prefix="AIQE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    encryption_key: SecretStr | None = Field(
        default=None,
        alias="AIQE_ENCRYPTION_KEY",
        description=(
            "Fernet encryption key for sensitive stored values. "
            "Generate with: python -c "
            "'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        ),
    )
    plugin_sandbox_enabled: bool = Field(
        default=True,
        description="Enforce plugin capability sandboxing. See ADR-003.",
    )
    plugin_capability_display: bool = Field(
        default=True,
        description="Show plugin permissions to user before loading.",
    )


class NotificationSettings(BaseSettings):
    """Notification channel configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    slack_bot_token: SecretStr | None = Field(
        default=None,
        alias="SLACK_BOT_TOKEN",
    )
    slack_channel_id: str | None = Field(
        default=None,
        alias="SLACK_CHANNEL_ID",
    )
    teams_webhook_url: SecretStr | None = Field(
        default=None,
        alias="TEAMS_WEBHOOK_URL",
    )
    github_token: SecretStr | None = Field(
        default=None,
        alias="GITHUB_TOKEN",
    )
    github_webhook_secret: SecretStr | None = Field(
        default=None,
        alias="GITHUB_WEBHOOK_SECRET",
    )


class AIQESettings(BaseSettings):
    """
    Root settings class that composes all AIQE configuration sections.

    This is the only settings object that application code needs to
    import. Each section is available as an attribute:

        settings = get_settings()
        settings.core.log_level
        settings.database.connection_url
        settings.gateway.default_provider
        settings.security.plugin_sandbox_enabled
        settings.notifications.slack_bot_token
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    core: CoreSettings = Field(default_factory=CoreSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    gateway: GatewaySettings = Field(default_factory=GatewaySettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    notifications: NotificationSettings = Field(
        default_factory=NotificationSettings
    )


@lru_cache(maxsize=1)
def get_settings() -> AIQESettings:
    """
    Get the AIQE settings singleton.

    Uses lru_cache so settings are loaded and validated exactly once
    at first access, then reused. This means validation errors surface
    at startup, not mid-execution.

    In tests, call get_settings.cache_clear() to reset between tests
    that need different configurations.

    Returns:
        Validated AIQESettings instance.

    Raises:
        ConfigurationError: If required settings are missing or invalid.
    """
    from aiqe.shared.exceptions import ConfigurationError

    try:
        return AIQESettings()
    except Exception as e:
        msg = f"AIQE configuration is invalid: {e}"
        raise ConfigurationError(msg) from e
