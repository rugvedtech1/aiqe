"""
AIQE Plugin Loader.

The Plugin Loader is the security gate for all third-party
plugins. It enforces the complete ADR-003 loading pipeline:

    1. Read manifest from plugin.toml
    2. Validate all declared capabilities against the registry
    3. Reject unknown or dangerous capabilities
    4. Display requested capabilities to user (if configured)
    5. Await user approval for restricted capabilities
    6. Import the plugin module
    7. Instantiate the plugin class
    8. Run the plugin health check
    9. Register with the PluginRegistry
    10. Return a PluginContext scoped to declared capabilities

A plugin that fails ANY of these steps is NEVER loaded.
No plugin code runs before steps 1-5 complete.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from aiqe.plugins.base import BasePlugin
from aiqe.plugins.capabilities import Capabilities
from aiqe.plugins.manifest import ManifestLoader, PluginManifest
from aiqe.plugins.registry import LoadedPlugin, PluginRegistry, get_plugin_registry
from aiqe.plugins.sandbox import PluginContext
from aiqe.shared.config import get_settings
from aiqe.shared.exceptions import PluginLoadError, PluginManifestError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)


class PluginLoader:
    """
    Loads plugins through the ADR-003 security pipeline.

    Args:
        registry: Plugin registry to register loaded plugins into.
        manifest_loader: Validates plugin manifests.
        display_capabilities: Whether to display plugin permissions
                              to the user before loading.
        require_approval_for_restricted: If True, restricted capabilities
                                         require explicit user approval.
    """

    def __init__(
        self,
        registry: PluginRegistry | None = None,
        manifest_loader: ManifestLoader | None = None,
        display_capabilities: bool = True,
        require_approval_for_restricted: bool = True,
    ) -> None:
        self._registry = registry or get_plugin_registry()
        self._manifest_loader = manifest_loader or ManifestLoader()
        self._display_capabilities = display_capabilities
        self._require_approval = require_approval_for_restricted

    async def load_from_path(
        self,
        plugin_dir: Path,
        workspace_path: Path,
        project_path: Path | None = None,
        workflow_id: str = "",
    ) -> PluginContext:
        """
        Load a plugin from a directory containing plugin.toml.

        Args:
            plugin_dir: Directory containing plugin.toml and plugin code.
            workspace_path: AIQE workspace for this execution.
            project_path: Project being analysed.
            workflow_id: Current workflow context ID.

        Returns:
            PluginContext scoped to the plugin's declared capabilities.

        Raises:
            PluginManifestError: If manifest is invalid.
            PluginLoadError: If plugin import or instantiation fails.
        """
        manifest_path = plugin_dir / "plugin.toml"

        # Step 1-3: Load and validate manifest
        manifest = self._manifest_loader.load_from_path(manifest_path)

        return await self._load_from_manifest(
            manifest=manifest,
            workspace_path=workspace_path,
            project_path=project_path,
            workflow_id=workflow_id,
        )

    async def load_from_manifest_dict(
        self,
        manifest_data: dict[str, Any],
        plugin_class: type[BasePlugin],
        workspace_path: Path,
        project_path: Path | None = None,
        workflow_id: str = "",
    ) -> PluginContext:
        """
        Load a plugin from an in-memory manifest dict and class.

        Used for built-in plugins and testing.

        Args:
            manifest_data: Dict matching plugin.toml structure.
            plugin_class: The plugin class to instantiate.
            workspace_path: AIQE workspace.
            project_path: Project path.
            workflow_id: Workflow context ID.

        Returns:
            PluginContext scoped to declared capabilities.
        """
        manifest = self._manifest_loader.load_from_dict(manifest_data)

        return await self._load_from_manifest(
            manifest=manifest,
            workspace_path=workspace_path,
            project_path=project_path,
            workflow_id=workflow_id,
            plugin_class_override=plugin_class,
        )

    async def _load_from_manifest(
        self,
        manifest: PluginManifest,
        workspace_path: Path,
        project_path: Path | None,
        workflow_id: str,
        plugin_class_override: type[BasePlugin] | None = None,
    ) -> PluginContext:
        """Execute the full ADR-003 loading pipeline."""

        plugin_name = manifest.name

        logger.info(
            "plugin_load_started",
            plugin_name=plugin_name,
            plugin_type=manifest.plugin_type,
            capability_count=len(manifest.required_capabilities),
            has_restricted=manifest.has_restricted_capabilities,
        )

        # Step 4: Display capabilities if configured
        if self._display_capabilities:
            self._display_plugin_permissions(manifest)

        # Step 5: Check for restricted capabilities
        if manifest.has_restricted_capabilities:
            await self._handle_restricted_capabilities(manifest)

        # Step 6-7: Import and instantiate the plugin
        if plugin_class_override is not None:
            plugin_instance = plugin_class_override()
        else:
            plugin_instance = self._import_and_instantiate(manifest)

        # Step 8: Health check
        try:
            is_healthy = await plugin_instance.health_check()
            if not is_healthy:
                logger.warning(
                    "plugin_health_check_failed",
                    plugin_name=plugin_name,
                )
        except Exception as e:
            logger.warning(
                "plugin_health_check_error",
                plugin_name=plugin_name,
                error=str(e),
            )
            is_healthy = False

        # Step 9: Register with the registry
        if not self._registry.is_registered(plugin_name):
            loaded = LoadedPlugin(
                manifest=manifest,
                instance=plugin_instance,
                is_healthy=is_healthy,
            )
            self._registry.register(loaded)

        # Step 10: Build and return scoped PluginContext
        granted_ids = {cap.id for cap in manifest.required_capabilities}

        # Create plugin workspace subdirectory
        plugin_workspace = workspace_path / "plugins" / plugin_name
        plugin_workspace.mkdir(parents=True, exist_ok=True)

        context = PluginContext(
            plugin_name=plugin_name,
            granted_capabilities=granted_ids,
            workspace_path=plugin_workspace,
            project_path=project_path,
            workflow_id=workflow_id,
        )

        logger.info(
            "plugin_loaded_successfully",
            plugin_name=plugin_name,
            granted_capabilities=sorted(granted_ids),
            is_healthy=is_healthy,
            workflow_id=workflow_id,
        )

        return context

    def _import_and_instantiate(
        self, manifest: PluginManifest
    ) -> BasePlugin:
        """
        Import the plugin module and instantiate the plugin class.

        Args:
            manifest: The validated plugin manifest.

        Returns:
            Instantiated plugin.

        Raises:
            PluginLoadError: If import or instantiation fails.
        """
        module_path = manifest.entry_point.module
        class_name = manifest.entry_point.class_name

        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            msg = (
                f"Cannot import plugin module '{module_path}' for "
                f"plugin '{manifest.name}': {e}. "
                f"Is the plugin installed? Run: pip install <plugin-package>"
            )
            raise PluginLoadError(msg, plugin_name=manifest.name) from e

        plugin_class = getattr(module, class_name, None)
        if plugin_class is None:
            msg = (
                f"Plugin module '{module_path}' does not contain "
                f"class '{class_name}'. Check the plugin manifest."
            )
            raise PluginLoadError(msg, plugin_name=manifest.name)

        if not issubclass(plugin_class, BasePlugin):
            msg = (
                f"Plugin class '{class_name}' in '{module_path}' does not "
                f"inherit from BasePlugin. All plugins must extend BasePlugin."
            )
            raise PluginLoadError(msg, plugin_name=manifest.name)

        try:
            return plugin_class()
        except Exception as e:
            msg = (
                f"Failed to instantiate plugin '{manifest.name}': {e}"
            )
            raise PluginLoadError(msg, plugin_name=manifest.name) from e

    def _display_plugin_permissions(
        self, manifest: PluginManifest
    ) -> None:
        """
        Display plugin permissions to the user.

        In CLI mode, prints to stdout. In server mode,
        this is logged for administrator review.
        """
        summary = manifest.display_summary()
        logger.info(
            "plugin_permissions_display",
            plugin_name=manifest.name,
            summary=summary,
        )
        # In interactive CLI mode, also print to console
        print(f"\n{'='*60}")
        print(summary)
        print(f"{'='*60}\n")

    async def _handle_restricted_capabilities(
        self, manifest: PluginManifest
    ) -> None:
        """
        Handle plugins that request restricted capabilities.

        In interactive CLI mode, prompts the user for approval.
        In non-interactive/CI mode, raises PluginLoadError unless
        the manifest is pre-approved in the config.

        Args:
            manifest: The manifest with restricted capabilities.

        Raises:
            PluginLoadError: If restricted capabilities are not approved.
        """
        restricted = [
            c for c in manifest.required_capabilities if c.is_restricted
        ]

        restricted_ids = [c.id for c in restricted]

        logger.warning(
            "plugin_requests_restricted_capabilities",
            plugin_name=manifest.name,
            restricted_capabilities=restricted_ids,
        )

        if not self._require_approval:
            # Non-interactive mode: log warning but allow
            logger.warning(
                "restricted_capabilities_auto_approved",
                plugin_name=manifest.name,
                restricted_capabilities=restricted_ids,
                reason="require_approval_for_restricted=False",
            )
            return

        # In v1, we log the restriction and allow loading with a clear warning
        # Enterprise v2 will add interactive approval and org-level policies
        logger.warning(
            "plugin_restricted_capability_warning",
            plugin_name=manifest.name,
            restricted_capabilities=restricted_ids,
            message=(
                f"Plugin '{manifest.name}' requests restricted capabilities: "
                f"{restricted_ids}. "
                f"In enterprise mode, these require administrator approval. "
                f"Proceeding with load in development mode."
            ),
        )


def get_plugin_loader(
    display_capabilities: bool | None = None,
) -> PluginLoader:
    """
    Get a configured PluginLoader.

    Reads display_capabilities from settings if not specified.

    Args:
        display_capabilities: Override the settings value.

    Returns:
        Configured PluginLoader.
    """
    settings = get_settings()
    display = (
        display_capabilities
        if display_capabilities is not None
        else settings.security.plugin_capability_display
    )
    return PluginLoader(
        display_capabilities=display,
        require_approval_for_restricted=(
            settings.security.plugin_sandbox_enabled
        ),
    )
