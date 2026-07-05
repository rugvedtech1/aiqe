"""
AIQE Plugin Capability System.

Every capability a plugin can request is defined here as a typed
constant. Plugins declare capabilities in their manifest. The
Plugin Loader grants only declared capabilities.

Design principles (ADR-003):
    - Principle of Least Privilege: plugins receive the minimum
      permissions required to perform their job. Nothing more.
    - Explicit over implicit: every capability must be declared.
      Undeclared capabilities are denied at the Python level.
    - Fine-grained over coarse: "Read Project Files" is granted,
      not "filesystem:read". This prevents a plugin that needs
      to read config files from also reading log files.
    - Auditable: every capability grant is logged.

Capability groups:
    FILESYSTEM  — file read/write operations
    BROWSER     — Playwright browser control
    GIT         — repository and PR operations
    NETWORK     — HTTP and third-party API calls
    SECRETS     — access to configured credentials
    SYSTEM      — process and environment access
    DATABASE    — data read/write operations
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final


class CapabilityGroup(str, Enum):
    """Top-level capability groups."""
    FILESYSTEM = "filesystem"
    BROWSER = "browser"
    GIT = "git"
    NETWORK = "network"
    SECRETS = "secrets"
    SYSTEM = "system"
    DATABASE = "database"


@dataclass(frozen=True)
class Capability:
    """
    A single, fine-grained plugin capability.

    Attributes:
        id: Unique identifier used in manifests and logs.
        group: Which capability group this belongs to.
        display_name: Human-readable name shown to users.
        description: What this capability allows.
        is_restricted: If True, requires explicit user approval
                       even in non-interactive modes.
        risk_level: 1=low, 2=medium, 3=high, 4=critical.
    """
    id: str
    group: CapabilityGroup
    display_name: str
    description: str
    is_restricted: bool = False
    risk_level: int = 1

    def __str__(self) -> str:
        return self.id

    def __hash__(self) -> int:
        return hash(self.id)


class Capabilities:
    """
    Registry of all valid AIQE plugin capabilities.

    Usage:
        from aiqe.plugins.capabilities import Capabilities

        # In a plugin manifest:
        required_capabilities = [
            Capabilities.FILESYSTEM_READ_PROJECT_FILES,
            Capabilities.BROWSER_NAVIGATE,
            Capabilities.BROWSER_SCREENSHOTS,
        ]
    """

    # ==================================================
    # FILESYSTEM CAPABILITIES
    # ==================================================

    FILESYSTEM_READ_PROJECT_FILES = Capability(
        id="filesystem.read_project_files",
        group=CapabilityGroup.FILESYSTEM,
        display_name="Read Project Files",
        description="Read source code files in the scanned project directory.",
        risk_level=1,
    )

    FILESYSTEM_READ_CONFIG_FILES = Capability(
        id="filesystem.read_config_files",
        group=CapabilityGroup.FILESYSTEM,
        display_name="Read Configuration Files",
        description="Read configuration files (.env.example, pyproject.toml, etc.).",
        risk_level=1,
    )

    FILESYSTEM_READ_LOGS = Capability(
        id="filesystem.read_logs",
        group=CapabilityGroup.FILESYSTEM,
        display_name="Read Log Files",
        description="Read log files produced by the application under test.",
        risk_level=1,
    )

    FILESYSTEM_READ_TEMP = Capability(
        id="filesystem.read_temp_files",
        group=CapabilityGroup.FILESYSTEM,
        display_name="Read Temporary Files",
        description="Read files in the AIQE temporary workspace directory.",
        risk_level=1,
    )

    FILESYSTEM_WRITE_PROJECT_FILES = Capability(
        id="filesystem.write_project_files",
        group=CapabilityGroup.FILESYSTEM,
        display_name="Write Project Files",
        description=(
            "Write files to the scanned project directory. "
            "AIQE v1 never auto-modifies production code (ADR-009) — "
            "this capability is for generating test files only."
        ),
        risk_level=3,
    )

    FILESYSTEM_WRITE_TEMP = Capability(
        id="filesystem.write_temp_files",
        group=CapabilityGroup.FILESYSTEM,
        display_name="Write Temporary Files",
        description="Write files to the AIQE temporary workspace directory.",
        risk_level=1,
    )

    FILESYSTEM_DELETE_TEMP = Capability(
        id="filesystem.delete_temp_files",
        group=CapabilityGroup.FILESYSTEM,
        display_name="Delete Temporary Files",
        description="Delete files from the AIQE temporary workspace directory.",
        risk_level=2,
    )

    FILESYSTEM_DELETE_PROJECT_FILES = Capability(
        id="filesystem.delete_project_files",
        group=CapabilityGroup.FILESYSTEM,
        display_name="Delete Project Files",
        description="Delete files from the scanned project directory.",
        is_restricted=True,
        risk_level=4,
    )

    # ==================================================
    # BROWSER CAPABILITIES
    # ==================================================

    BROWSER_NAVIGATE = Capability(
        id="browser.navigate",
        group=CapabilityGroup.BROWSER,
        display_name="Browser Navigation",
        description="Navigate to URLs in a controlled browser instance.",
        risk_level=2,
    )

    BROWSER_CLICK = Capability(
        id="browser.click",
        group=CapabilityGroup.BROWSER,
        display_name="Browser Click",
        description="Click on elements in the browser.",
        risk_level=2,
    )

    BROWSER_FILL_FORMS = Capability(
        id="browser.fill_forms",
        group=CapabilityGroup.BROWSER,
        display_name="Fill Forms",
        description="Fill in form fields in the browser.",
        risk_level=2,
    )

    BROWSER_UPLOAD_FILES = Capability(
        id="browser.upload_files",
        group=CapabilityGroup.BROWSER,
        display_name="Upload Files",
        description="Upload files through the browser.",
        risk_level=3,
    )

    BROWSER_DOWNLOAD_FILES = Capability(
        id="browser.download_files",
        group=CapabilityGroup.BROWSER,
        display_name="Download Files",
        description="Download files through the browser.",
        risk_level=2,
    )

    BROWSER_SCREENSHOTS = Capability(
        id="browser.screenshots",
        group=CapabilityGroup.BROWSER,
        display_name="Capture Screenshots",
        description="Capture screenshots during browser test execution.",
        risk_level=1,
    )

    BROWSER_VIDEO = Capability(
        id="browser.video",
        group=CapabilityGroup.BROWSER,
        display_name="Record Video",
        description="Record video of browser test execution sessions.",
        risk_level=1,
    )

    BROWSER_EXECUTE_JS = Capability(
        id="browser.execute_javascript",
        group=CapabilityGroup.BROWSER,
        display_name="Execute JavaScript",
        description="Execute JavaScript in the browser context.",
        is_restricted=True,
        risk_level=4,
    )

    # ==================================================
    # GIT CAPABILITIES
    # ==================================================

    GIT_READ_REPOSITORY = Capability(
        id="git.read_repository",
        group=CapabilityGroup.GIT,
        display_name="Read Repository",
        description="Read git repository history, branches, and metadata.",
        risk_level=1,
    )

    GIT_CLONE = Capability(
        id="git.clone_repository",
        group=CapabilityGroup.GIT,
        display_name="Clone Repository",
        description="Clone a git repository to a temporary directory.",
        risk_level=2,
    )

    GIT_CREATE_BRANCH = Capability(
        id="git.create_branch",
        group=CapabilityGroup.GIT,
        display_name="Create Branch",
        description="Create a new git branch.",
        risk_level=3,
    )

    GIT_COMMIT = Capability(
        id="git.commit_changes",
        group=CapabilityGroup.GIT,
        display_name="Commit Changes",
        description="Commit file changes to git.",
        is_restricted=True,
        risk_level=4,
    )

    GIT_CREATE_PR = Capability(
        id="git.create_pull_request",
        group=CapabilityGroup.GIT,
        display_name="Create Pull Request",
        description="Create a Pull Request on GitHub or GitLab.",
        is_restricted=True,
        risk_level=4,
    )

    GIT_COMMENT_PR = Capability(
        id="git.comment_pull_request",
        group=CapabilityGroup.GIT,
        display_name="Comment on Pull Request",
        description="Post comments on Pull Requests.",
        risk_level=2,
    )

    # ==================================================
    # NETWORK CAPABILITIES
    # ==================================================

    NETWORK_HTTP = Capability(
        id="network.http",
        group=CapabilityGroup.NETWORK,
        display_name="HTTP Requests",
        description="Make outbound HTTP requests.",
        risk_level=2,
    )

    NETWORK_HTTPS = Capability(
        id="network.https",
        group=CapabilityGroup.NETWORK,
        display_name="HTTPS Requests",
        description="Make outbound HTTPS requests.",
        risk_level=2,
    )

    NETWORK_GITHUB_API = Capability(
        id="network.github_api",
        group=CapabilityGroup.NETWORK,
        display_name="GitHub API",
        description="Make requests to the GitHub REST/GraphQL API.",
        risk_level=2,
    )

    NETWORK_GITLAB_API = Capability(
        id="network.gitlab_api",
        group=CapabilityGroup.NETWORK,
        display_name="GitLab API",
        description="Make requests to the GitLab REST API.",
        risk_level=2,
    )

    NETWORK_JIRA_API = Capability(
        id="network.jira_api",
        group=CapabilityGroup.NETWORK,
        display_name="Jira API",
        description="Make requests to the Jira REST API.",
        risk_level=2,
    )

    NETWORK_SLACK_API = Capability(
        id="network.slack_api",
        group=CapabilityGroup.NETWORK,
        display_name="Slack API",
        description="Send messages and notifications via the Slack API.",
        risk_level=2,
    )

    NETWORK_INTERNAL_API = Capability(
        id="network.internal_api",
        group=CapabilityGroup.NETWORK,
        display_name="Internal Company API",
        description="Make requests to internal company APIs.",
        risk_level=3,
    )

    # ==================================================
    # SECRETS CAPABILITIES
    # ==================================================

    SECRETS_OPENAI_KEY = Capability(
        id="secrets.openai_api_key",
        group=CapabilityGroup.SECRETS,
        display_name="Read OpenAI API Key",
        description="Access the configured OpenAI API key.",
        is_restricted=True,
        risk_level=4,
    )

    SECRETS_ANTHROPIC_KEY = Capability(
        id="secrets.anthropic_api_key",
        group=CapabilityGroup.SECRETS,
        display_name="Read Anthropic API Key",
        description="Access the configured Anthropic API key.",
        is_restricted=True,
        risk_level=4,
    )

    SECRETS_DATABASE_CREDENTIALS = Capability(
        id="secrets.database_credentials",
        group=CapabilityGroup.SECRETS,
        display_name="Read Database Credentials",
        description="Access the configured database connection credentials.",
        is_restricted=True,
        risk_level=4,
    )

    SECRETS_GITHUB_TOKEN = Capability(
        id="secrets.github_token",
        group=CapabilityGroup.SECRETS,
        display_name="Read GitHub Token",
        description="Access the configured GitHub personal access token.",
        is_restricted=True,
        risk_level=4,
    )

    # ==================================================
    # SYSTEM CAPABILITIES
    # ==================================================

    SYSTEM_SHELL = Capability(
        id="system.execute_shell",
        group=CapabilityGroup.SYSTEM,
        display_name="Execute Shell Commands",
        description="Execute arbitrary shell commands on the host system.",
        is_restricted=True,
        risk_level=4,
    )

    SYSTEM_DOCKER = Capability(
        id="system.docker",
        group=CapabilityGroup.SYSTEM,
        display_name="Start Docker Containers",
        description="Start and manage Docker containers.",
        is_restricted=True,
        risk_level=4,
    )

    SYSTEM_ENV_VARS = Capability(
        id="system.environment_variables",
        group=CapabilityGroup.SYSTEM,
        display_name="Access Environment Variables",
        description="Read environment variables from the host process.",
        risk_level=3,
    )

    SYSTEM_SPAWN_PROCESS = Capability(
        id="system.spawn_process",
        group=CapabilityGroup.SYSTEM,
        display_name="Spawn Processes",
        description="Spawn child processes on the host system.",
        is_restricted=True,
        risk_level=4,
    )

    # ==================================================
    # DATABASE CAPABILITIES
    # ==================================================

    DATABASE_READ = Capability(
        id="database.read",
        group=CapabilityGroup.DATABASE,
        display_name="Read Database Data",
        description="Execute SELECT queries against the target database.",
        risk_level=2,
    )

    DATABASE_INSERT = Capability(
        id="database.insert",
        group=CapabilityGroup.DATABASE,
        display_name="Insert Database Data",
        description="Execute INSERT statements against the target database.",
        risk_level=3,
    )

    DATABASE_UPDATE = Capability(
        id="database.update",
        group=CapabilityGroup.DATABASE,
        display_name="Update Database Data",
        description="Execute UPDATE statements against the target database.",
        risk_level=3,
    )

    DATABASE_DELETE = Capability(
        id="database.delete",
        group=CapabilityGroup.DATABASE,
        display_name="Delete Database Data",
        description="Execute DELETE statements against the target database.",
        is_restricted=True,
        risk_level=4,
    )

    DATABASE_MIGRATE = Capability(
        id="database.run_migrations",
        group=CapabilityGroup.DATABASE,
        display_name="Run Migrations",
        description="Execute database migrations against the target database.",
        is_restricted=True,
        risk_level=4,
    )

    # ==================================================
    # CAPABILITY REGISTRY HELPERS
    # ==================================================

    @classmethod
    def all(cls) -> list[Capability]:
        """Return all defined capabilities."""
        return [
            v for v in cls.__dict__.values()
            if isinstance(v, Capability)
        ]

    @classmethod
    def by_id(cls, capability_id: str) -> Capability | None:
        """Look up a capability by its ID string."""
        for cap in cls.all():
            if cap.id == capability_id:
                return cap
        return None

    @classmethod
    def restricted(cls) -> list[Capability]:
        """Return all capabilities that require explicit user approval."""
        return [c for c in cls.all() if c.is_restricted]

    @classmethod
    def by_group(cls, group: CapabilityGroup) -> list[Capability]:
        """Return all capabilities in a specific group."""
        return [c for c in cls.all() if c.group == group]

    @classmethod
    def validate_ids(cls, capability_ids: list[str]) -> tuple[
        list[Capability], list[str]
    ]:
        """
        Validate a list of capability ID strings.

        Args:
            capability_ids: List of capability ID strings from a manifest.

        Returns:
            Tuple of (valid_capabilities, unknown_ids).
            unknown_ids contains any IDs not found in the registry.
        """
        valid = []
        unknown = []
        for cap_id in capability_ids:
            cap = cls.by_id(cap_id)
            if cap is not None:
                valid.append(cap)
            else:
                unknown.append(cap_id)
        return valid, unknown


# Pre-built capability sets for common plugin types
# Plugin authors can use these as a starting point.

PLAYWRIGHT_PLUGIN_CAPABILITIES: Final[list[Capability]] = [
    Capabilities.BROWSER_NAVIGATE,
    Capabilities.BROWSER_CLICK,
    Capabilities.BROWSER_FILL_FORMS,
    Capabilities.BROWSER_SCREENSHOTS,
    Capabilities.BROWSER_VIDEO,
    Capabilities.FILESYSTEM_READ_PROJECT_FILES,
    Capabilities.FILESYSTEM_WRITE_TEMP,
]

GITHUB_PLUGIN_CAPABILITIES: Final[list[Capability]] = [
    Capabilities.GIT_READ_REPOSITORY,
    Capabilities.GIT_COMMENT_PR,
    Capabilities.NETWORK_GITHUB_API,
]

SLACK_PLUGIN_CAPABILITIES: Final[list[Capability]] = [
    Capabilities.NETWORK_SLACK_API,
]

SECURITY_SCAN_PLUGIN_CAPABILITIES: Final[list[Capability]] = [
    Capabilities.FILESYSTEM_READ_PROJECT_FILES,
    Capabilities.FILESYSTEM_READ_CONFIG_FILES,
    Capabilities.NETWORK_HTTPS,
]
