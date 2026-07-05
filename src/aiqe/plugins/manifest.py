"""
AIQE Plugin Manifest Schema.

Every plugin must ship a manifest describing:
    - What the plugin is (name, version, author)
    - What it does (description, plugin_type)
    - What permissions it needs (required_capabilities)
    - What AIQE version it supports (min_aiqe_version)

The manifest is the plugin's contract with AIQE. The Plugin Loader
reads and validates the manifest BEFORE loading any plugin code.
If the manifest is missing, malformed, or requests unknown capabilities,
the plugin is rejected — no code runs.

Manifest format: TOML file named 'plugin.toml' at the plugin root.

Example plugin.toml:
    [plugin]
    name = "my-playwright-plugin"
    version = "1.0.0"
    description = "Custom Playwright test execution plugin"
    author = "Engineering Team"
    plugin_type = "browser"
    min_aiqe_version = "0.1.0"

    [plugin.capabilities]
    required = [
        "browser.navigate",
        "browser.screenshots",
        "browser.video",
        "filesystem.read_project_files",
        "filesystem.write_temp_files",
    ]

    [plugin.entry_point]
    module = "my_playwright_plugin.plugin"
    class_name = "MyPlaywrightPlugin"
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiqe.plugins.capabilities import Capabilities, Capability
from aiqe.shared.exceptions import PluginManifestError
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

# Valid plugin types — determines which BasePlugin subclass to use
VALID_PLUGIN_TYPES = frozenset({
    "browser",
    "api",
    "database",
    "security",
    "performance",
    "notification",
    "report",
    "storage",
    "ai_provider",
    "custom",
})


@dataclass
class PluginEntryPoint:
    """
    Describes how to import and instantiate the plugin class.

    Attributes:
        module: Python module path (e.g. 'my_plugin.plugin').
        class_name: Name of the plugin class within the module.
    """
    module: str
    class_name: str


@dataclass
class PluginManifest:
    """
    A validated plugin manifest.

    All fields are validated at construction time. A PluginManifest
    instance always represents a valid, loadable plugin declaration.

    Attributes:
        name: Unique plugin identifier (kebab-case).
        version: Semantic version string.
        description: What this plugin does (one paragraph max).
        author: Plugin author or organisation.
        plugin_type: What type of plugin this is.
        min_aiqe_version: Minimum AIQE version required.
        required_capabilities: Validated Capability objects the
                               plugin requests.
        entry_point: How to import and instantiate the plugin.
        metadata: Additional plugin-specific configuration.
        manifest_path: Path to the plugin.toml file (for debugging).
    """
    name: str
    version: str
    description: str
    author: str
    plugin_type: str
    min_aiqe_version: str
    required_capabilities: list[Capability]
    entry_point: PluginEntryPoint
    metadata: dict[str, Any] = field(default_factory=dict)
    manifest_path: Path | None = None

    @property
    def has_restricted_capabilities(self) -> bool:
        """True if any required capability is marked as restricted."""
        return any(c.is_restricted for c in self.required_capabilities)

    @property
    def max_risk_level(self) -> int:
        """Highest risk level among required capabilities."""
        if not self.required_capabilities:
            return 0
        return max(c.risk_level for c in self.required_capabilities)

    @property
    def capability_ids(self) -> list[str]:
        """List of capability IDs for display and logging."""
        return [c.id for c in self.required_capabilities]

    def display_summary(self) -> str:
        """
        Human-readable summary of the plugin and its permissions.

        Shown to users before loading when capability display is enabled.
        """
        lines = [
            f"Plugin: {self.name} v{self.version}",
            f"Author: {self.author}",
            f"Type:   {self.plugin_type}",
            f"        {self.description}",
            "",
            "Requested permissions:",
        ]

        for cap in self.required_capabilities:
            risk_label = (
                "⚠️  RESTRICTED" if cap.is_restricted
                else f"[risk:{cap.risk_level}]"
            )
            lines.append(f"  • {cap.display_name} {risk_label}")
            lines.append(f"    {cap.description}")

        return "\n".join(lines)


class ManifestLoader:
    """
    Loads and validates plugin manifests from TOML files.

    This is the first gate in the plugin loading pipeline.
    No plugin code runs until the manifest is validated.
    """

    def load_from_path(self, manifest_path: Path) -> PluginManifest:
        """
        Load and validate a plugin manifest from a TOML file.

        Args:
            manifest_path: Path to the plugin.toml file.

        Returns:
            Validated PluginManifest.

        Raises:
            PluginManifestError: If the file is missing, malformed,
                                 requests unknown capabilities, or
                                 has invalid field values.
        """
        if not manifest_path.exists():
            msg = (
                f"Plugin manifest not found at '{manifest_path}'. "
                f"Every plugin must include a plugin.toml file."
            )
            raise PluginManifestError(msg)

        try:
            raw = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            msg = f"Plugin manifest at '{manifest_path}' is not valid TOML: {e}"
            raise PluginManifestError(msg) from e

        return self._parse_and_validate(raw, manifest_path)

    def load_from_dict(self, data: dict[str, Any]) -> PluginManifest:
        """
        Load and validate a manifest from a Python dict.

        Used in tests and for in-memory plugin registration.

        Args:
            data: Dict matching the plugin.toml structure.

        Returns:
            Validated PluginManifest.
        """
        return self._parse_and_validate(data, manifest_path=None)

    def _parse_and_validate(
        self,
        raw: dict[str, Any],
        manifest_path: Path | None,
    ) -> PluginManifest:
        """Parse and validate raw manifest data."""
        plugin_section = raw.get("plugin", {})

        # Validate required top-level fields
        required_fields = [
            "name", "version", "description", "author", "plugin_type"
        ]
        missing = [
            f for f in required_fields if not plugin_section.get(f)
        ]
        if missing:
            msg = (
                f"Plugin manifest is missing required fields: {missing}. "
                f"All plugins must declare: {required_fields}."
            )
            raise PluginManifestError(
                msg, plugin_name=plugin_section.get("name")
            )

        # Validate plugin_type
        plugin_type = plugin_section["plugin_type"]
        if plugin_type not in VALID_PLUGIN_TYPES:
            msg = (
                f"Unknown plugin_type '{plugin_type}'. "
                f"Valid types: {sorted(VALID_PLUGIN_TYPES)}"
            )
            raise PluginManifestError(
                msg, plugin_name=plugin_section.get("name")
            )

        # Validate and resolve capabilities
        caps_section = plugin_section.get("capabilities", {})
        required_cap_ids = caps_section.get("required", [])

        valid_caps, unknown_ids = Capabilities.validate_ids(required_cap_ids)

        if unknown_ids:
            msg = (
                f"Plugin '{plugin_section['name']}' declares unknown "
                f"capabilities: {unknown_ids}. "
                f"These capabilities do not exist in AIQE's capability "
                f"registry. Check the plugin manifest for typos."
            )
            raise PluginManifestError(
                msg, plugin_name=plugin_section.get("name")
            )

        # Validate entry point
        entry_section = plugin_section.get("entry_point", {})
        if not entry_section.get("module") or not entry_section.get("class_name"):
            msg = (
                f"Plugin '{plugin_section['name']}' manifest is missing "
                f"[plugin.entry_point] with 'module' and 'class_name'."
            )
            raise PluginManifestError(
                msg, plugin_name=plugin_section.get("name")
            )

        manifest = PluginManifest(
            name=plugin_section["name"],
            version=plugin_section["version"],
            description=plugin_section["description"],
            author=plugin_section["author"],
            plugin_type=plugin_type,
            min_aiqe_version=plugin_section.get("min_aiqe_version", "0.1.0"),
            required_capabilities=valid_caps,
            entry_point=PluginEntryPoint(
                module=entry_section["module"],
                class_name=entry_section["class_name"],
            ),
            metadata=plugin_section.get("metadata", {}),
            manifest_path=manifest_path,
        )

        logger.info(
            "manifest_validated",
            plugin_name=manifest.name,
            plugin_type=manifest.plugin_type,
            capability_count=len(manifest.required_capabilities),
            has_restricted=manifest.has_restricted_capabilities,
            max_risk_level=manifest.max_risk_level,
        )

        return manifest
