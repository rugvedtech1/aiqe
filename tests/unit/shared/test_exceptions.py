"""Unit tests for AIQE exception hierarchy."""
import pytest
from aiqe.shared.exceptions import (
    AIQEError,
    AgentNotFoundError,
    CapabilityDeniedError,
    ConfigurationError,
    PluginManifestError,
    RecordNotFoundError,
    ValidationError,
    WorkflowContextError,
)


class TestAIQEError:
    def test_basic_construction(self):
        error = AIQEError("something went wrong")
        assert str(error) == "something went wrong"
        assert error.message == "something went wrong"
        assert error.context == {}
        assert error.workflow_id is None

    def test_with_context_and_workflow_id(self):
        error = AIQEError(
            "failure",
            context={"stage": "analysis"},
            workflow_id="wf_123",
        )
        assert error.context == {"stage": "analysis"}
        assert error.workflow_id == "wf_123"

    def test_is_exception(self):
        with pytest.raises(AIQEError):
            raise AIQEError("test")


class TestExceptionHierarchy:
    def test_config_error_is_aiqe_error(self):
        assert issubclass(ConfigurationError, AIQEError)

    def test_workflow_context_error_is_aiqe_error(self):
        assert issubclass(WorkflowContextError, AIQEError)

    def test_agent_not_found_is_agent_error(self):
        from aiqe.shared.exceptions import AgentError
        assert issubclass(AgentNotFoundError, AgentError)

    def test_capability_denied_carries_capability(self):
        error = CapabilityDeniedError(
            "denied",
            plugin_name="playwright-plugin",
            capability="system:execute_shell",
        )
        assert error.capability == "system:execute_shell"
        assert error.plugin_name == "playwright-plugin"

    def test_record_not_found_carries_entity_info(self):
        error = RecordNotFoundError(
            "not found",
            entity_type="WorkflowContext",
            entity_id="wf_123",
        )
        assert error.entity_type == "WorkflowContext"
        assert error.entity_id == "wf_123"

    def test_validation_error_carries_field(self):
        error = ValidationError("invalid", field="log_level", invalid_value="VERBOSE")
        assert error.field == "log_level"
        assert error.invalid_value == "VERBOSE"
