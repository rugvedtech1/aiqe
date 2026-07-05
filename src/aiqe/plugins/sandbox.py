"""
AIQE Plugin Sandbox.

Enforces capability permissions at the Python level for v1.
Plugins interact with AIQE resources ONLY through the
PluginContext — a restricted view of AIQE's capabilities
that contains only what the plugin declared in its manifest.

How enforcement works (v1 — in-process):
    The Plugin Loader creates a PluginContext containing only
    the interfaces the plugin declared. The plugin receives
    this context and can only call what's in it. If it tries
    to access something undeclared, it gets AttributeError.

    Example:
        Plugin declares: [browser.navigate, browser.screenshots]
        Plugin receives: PluginContext with .browser.navigate() and
                         .browser.screenshots() only.
        Plugin tries:    context.filesystem.delete_project_files()
        Result:          AttributeError — method does not exist
                         on the restricted PluginContext.

Why not OS-level sandboxing in v1?
    OS-level sandboxing (containers, seccomp, gVisor) adds significant
    operational complexity and is not required for the initial release.
    In-process Python enforcement catches accidental overreach and
    establishes the capability contract. Enterprise v2 adds OS-level
    isolation for production deployments. See ADR-003.

CapabilityViolation events:
    Any attempt to use an undeclared capability that bypasses the
    PluginContext (e.g. by importing os directly) is a security
    concern logged by the AuditHandler but cannot be prevented
    without OS-level sandboxing. This is explicitly documented
    as the v1 limitation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from aiqe.plugins.capabilities import Capabilities, Capability, CapabilityGroup
from aiqe.shared.exceptions import CapabilityDeniedError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class RestrictedFilesystem:
    """
    Filesystem interface scoped to declared capabilities.

    Plugins receive this instead of direct filesystem access.
    Only capabilities declared in the manifest are available.
    """

    def __init__(
        self,
        plugin_name: str,
        granted: set[str],
        workspace_path: Path,
        project_path: Path | None = None,
    ) -> None:
        self._plugin = plugin_name
        self._granted = granted
        self._workspace = workspace_path
        self._project = project_path

    def _check(self, capability_id: str) -> None:
        """Raise CapabilityDeniedError if capability not granted."""
        if capability_id not in self._granted:
            msg = (
                f"Plugin '{self._plugin}' attempted to use capability "
                f"'{capability_id}' which was not declared in its manifest. "
                f"Declared capabilities: {sorted(self._granted)}. "
                f"This is a capability violation (ADR-003)."
            )
            logger.error(
                "capability_violation",
                plugin_name=self._plugin,
                attempted_capability=capability_id,
                granted_capabilities=sorted(self._granted),
            )
            raise CapabilityDeniedError(
                msg,
                plugin_name=self._plugin,
                capability=capability_id,
            )

    def read_project_file(self, relative_path: str) -> str:
        """Read a file from the project directory."""
        self._check(Capabilities.FILESYSTEM_READ_PROJECT_FILES.id)
        if self._project is None:
            raise ValueError("No project path configured for this plugin.")
        full_path = self._project / relative_path
        return full_path.read_text(encoding="utf-8")

    def read_config_file(self, relative_path: str) -> str:
        """Read a configuration file."""
        self._check(Capabilities.FILESYSTEM_READ_CONFIG_FILES.id)
        if self._project is None:
            raise ValueError("No project path configured for this plugin.")
        full_path = self._project / relative_path
        return full_path.read_text(encoding="utf-8")

    def read_temp_file(self, filename: str) -> str:
        """Read a file from the AIQE workspace."""
        self._check(Capabilities.FILESYSTEM_READ_TEMP.id)
        full_path = self._workspace / filename
        return full_path.read_text(encoding="utf-8")

    def write_temp_file(self, filename: str, content: str) -> Path:
        """Write a file to the AIQE workspace."""
        self._check(Capabilities.FILESYSTEM_WRITE_TEMP.id)
        full_path = self._workspace / filename
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return full_path

    def write_project_file(self, relative_path: str, content: str) -> Path:
        """Write a file to the project directory."""
        self._check(Capabilities.FILESYSTEM_WRITE_PROJECT_FILES.id)
        if self._project is None:
            raise ValueError("No project path configured for this plugin.")
        full_path = self._project / relative_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")
        return full_path

    def delete_temp_file(self, filename: str) -> None:
        """Delete a file from the AIQE workspace."""
        self._check(Capabilities.FILESYSTEM_DELETE_TEMP.id)
        full_path = self._workspace / filename
        if full_path.exists():
            full_path.unlink()

    def list_project_files(
        self, pattern: str = "**/*", max_files: int = 500
    ) -> list[Path]:
        """List files in the project directory matching a pattern."""
        self._check(Capabilities.FILESYSTEM_READ_PROJECT_FILES.id)
        if self._project is None:
            return []
        return list(self._project.glob(pattern))[:max_files]


class RestrictedNetwork:
    """
    Network interface scoped to declared capabilities.

    Wraps httpx with capability checks.
    """

    def __init__(self, plugin_name: str, granted: set[str]) -> None:
        self._plugin = plugin_name
        self._granted = granted

    def _check(self, capability_id: str) -> None:
        if capability_id not in self._granted:
            msg = (
                f"Plugin '{self._plugin}' attempted network access "
                f"without '{capability_id}' capability."
            )
            logger.error(
                "capability_violation",
                plugin_name=self._plugin,
                attempted_capability=capability_id,
            )
            raise CapabilityDeniedError(
                msg,
                plugin_name=self._plugin,
                capability=capability_id,
            )

    async def get(self, url: str, **kwargs: Any) -> Any:
        """Make an HTTP GET request."""
        scheme = "https" if url.startswith("https") else "http"
        cap_id = (
            Capabilities.NETWORK_HTTPS.id
            if scheme == "https"
            else Capabilities.NETWORK_HTTP.id
        )
        self._check(cap_id)

        import httpx
        async with httpx.AsyncClient(**kwargs) as client:
            return await client.get(url)

    async def post(self, url: str, **kwargs: Any) -> Any:
        """Make an HTTP POST request."""
        scheme = "https" if url.startswith("https") else "http"
        cap_id = (
            Capabilities.NETWORK_HTTPS.id
            if scheme == "https"
            else Capabilities.NETWORK_HTTP.id
        )
        self._check(cap_id)

        import httpx
        async with httpx.AsyncClient(**kwargs) as client:
            return await client.post(url, **kwargs)


class PluginContext:
    """
    The restricted execution context given to every plugin.

    A PluginContext contains ONLY the interfaces the plugin
    declared in its manifest. Attempting to access undeclared
    functionality raises CapabilityDeniedError.

    Plugins receive this context in their execute() method
    and interact with AIQE ONLY through it.

    Args:
        plugin_name: The plugin's registered name.
        granted_capabilities: Set of capability IDs granted.
        workspace_path: The plugin's isolated workspace directory.
        project_path: The project being analysed (if applicable).
        workflow_id: The current workflow context ID.
    """

    def __init__(
        self,
        plugin_name: str,
        granted_capabilities: set[str],
        workspace_path: Path,
        project_path: Path | None = None,
        workflow_id: str = "",
    ) -> None:
        self._plugin_name = plugin_name
        self._granted = granted_capabilities
        self._workflow_id = workflow_id

        # Build restricted interfaces for granted capability groups
        self.filesystem = RestrictedFilesystem(
            plugin_name=plugin_name,
            granted=granted_capabilities,
            workspace_path=workspace_path,
            project_path=project_path,
        )

        self.network = RestrictedNetwork(
            plugin_name=plugin_name,
            granted=granted_capabilities,
        )

    @property
    def workflow_id(self) -> str:
        """The current workflow context ID."""
        return self._workflow_id

    @property
    def plugin_name(self) -> str:
        """This plugin's registered name."""
        return self._plugin_name

    def has_capability(self, capability_id: str) -> bool:
        """Check if a specific capability was granted."""
        return capability_id in self._granted

    def assert_capability(self, capability_id: str) -> None:
        """
        Assert that a capability is granted, raising if not.

        Plugin authors can call this at the start of methods
        that require a capability, for clear error messages.
        """
        if not self.has_capability(capability_id):
            msg = (
                f"Plugin '{self._plugin_name}' requires capability "
                f"'{capability_id}' but it was not declared in the manifest."
            )
            raise CapabilityDeniedError(
                msg,
                plugin_name=self._plugin_name,
                capability=capability_id,
            )

    def granted_capability_ids(self) -> list[str]:
        """List of all granted capability IDs."""
        return sorted(self._granted)
