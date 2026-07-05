"""Unit tests for Capabilities registry."""
import pytest
from aiqe.plugins.capabilities import (
    Capabilities,
    Capability,
    CapabilityGroup,
    PLAYWRIGHT_PLUGIN_CAPABILITIES,
    GITHUB_PLUGIN_CAPABILITIES,
    SLACK_PLUGIN_CAPABILITIES,
)


class TestCapabilities:
    def test_all_returns_non_empty_list(self):
        caps = Capabilities.all()
        assert len(caps) > 20
        assert all(isinstance(c, Capability) for c in caps)

    def test_by_id_finds_existing(self):
        cap = Capabilities.by_id("browser.navigate")
        assert cap is not None
        assert cap.display_name == "Browser Navigation"

    def test_by_id_returns_none_for_unknown(self):
        cap = Capabilities.by_id("nonexistent.capability")
        assert cap is None

    def test_restricted_are_high_risk(self):
        restricted = Capabilities.restricted()
        assert all(c.is_restricted for c in restricted)
        assert all(c.risk_level >= 3 for c in restricted)

    def test_by_group_filesystem(self):
        fs_caps = Capabilities.by_group(CapabilityGroup.FILESYSTEM)
        assert len(fs_caps) > 0
        assert all(c.group == CapabilityGroup.FILESYSTEM for c in fs_caps)

    def test_validate_ids_valid(self):
        valid, unknown = Capabilities.validate_ids([
            "browser.navigate",
            "browser.screenshots",
            "filesystem.read_project_files",
        ])
        assert len(valid) == 3
        assert unknown == []

    def test_validate_ids_unknown(self):
        valid, unknown = Capabilities.validate_ids([
            "browser.navigate",
            "nonexistent.capability",
            "another.unknown",
        ])
        assert len(valid) == 1
        assert "nonexistent.capability" in unknown
        assert "another.unknown" in unknown

    def test_all_ids_are_unique(self):
        caps = Capabilities.all()
        ids = [c.id for c in caps]
        assert len(ids) == len(set(ids)), "Duplicate capability IDs found"

    def test_playwright_preset_is_safe(self):
        """Playwright preset should not include restricted capabilities."""
        unsafe = [
            c for c in PLAYWRIGHT_PLUGIN_CAPABILITIES
            if c.is_restricted
        ]
        assert len(unsafe) == 0, (
            f"Playwright preset contains restricted capabilities: "
            f"{[c.id for c in unsafe]}"
        )

    def test_slack_preset_network_only(self):
        """Slack preset should only include Slack network capability."""
        assert len(SLACK_PLUGIN_CAPABILITIES) == 1
        assert SLACK_PLUGIN_CAPABILITIES[0].id == "network.slack_api"

    def test_github_preset_no_database(self):
        """GitHub preset should not include database capabilities."""
        db_caps = [
            c for c in GITHUB_PLUGIN_CAPABILITIES
            if c.group == CapabilityGroup.DATABASE
        ]
        assert len(db_caps) == 0
