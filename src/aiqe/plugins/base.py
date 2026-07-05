"""
AIQE BasePlugin Abstract Class.

Every AIQE plugin inherits from BasePlugin. This class defines
the contract every plugin must fulfill:

    1. Declare NAME, VERSION, PLUGIN_TYPE class variables.
    2. Implement execute() — the plugin's main logic.
    3. Optionally implement health_check() — verify plugin is ready.
    4. Optionally implement teardown() — clean up after execution.

Plugins are isolated from AIQE internals. They receive:
    - A PluginContext with ONLY their declared capabilities.
    - A typed input dict with task-specific parameters.

Plugins produce:
    - A typed output dict with results.
    - They never modify AIQE internal state directly.

Template Method pattern (same as BaseAgent):
    run() handles lifecycle (logging, timing, error handling).
    execute() contains the plugin's actual logic.
"""

from __future__ import annotations

import abc
from typing import Any, ClassVar

from aiqe.plugins.sandbox import PluginContext
from aiqe.shared.exceptions import PluginError
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import Timer

logger = get_logger(__name__)


class BasePlugin(abc.ABC):
    """
    Abstract base class for all AIQE plugins.

    Class variables every subclass must declare:
        NAME: str         — unique plugin identifier
        VERSION: str      — semantic version
        PLUGIN_TYPE: str  — must match a valid plugin type

    Methods every subclass must implement:
        execute()         — the plugin's main logic
    """

    NAME: ClassVar[str] = ""
    VERSION: ClassVar[str] = "0.0.0"
    PLUGIN_TYPE: ClassVar[str] = "custom"

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if abc.ABC in cls.__bases__:
            return
        if getattr(cls, "__abstractmethods__", None):
            return
        if not cls.NAME:
            raise TypeError(
                f"Plugin class {cls.__name__} must declare a non-empty NAME."
            )

    async def run(
        self,
        context: PluginContext,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Execute this plugin with full lifecycle management.

        Handles logging, timing, and error wrapping automatically.
        Plugin authors implement execute(), not this method.

        Args:
            context: Restricted capability context for this plugin.
            input_data: Task-specific input parameters.

        Returns:
            Plugin output dict.
        """
        plugin_logger = get_logger(self.__class__.__module__)

        plugin_logger.info(
            "plugin_started",
            plugin_name=self.NAME,
            plugin_type=self.PLUGIN_TYPE,
            workflow_id=context.workflow_id,
            granted_capabilities=context.granted_capability_ids(),
        )

        with Timer() as timer:
            try:
                output = await self.execute(context, input_data)
                output.setdefault("success", True)
                output.setdefault("duration_seconds", timer.elapsed_seconds)

                plugin_logger.info(
                    "plugin_completed",
                    plugin_name=self.NAME,
                    workflow_id=context.workflow_id,
                    duration_seconds=timer.elapsed_seconds,
                    success=output.get("success"),
                )
                return output

            except PluginError:
                raise
            except Exception as e:
                plugin_logger.error(
                    "plugin_failed",
                    plugin_name=self.NAME,
                    workflow_id=context.workflow_id,
                    error_type=type(e).__name__,
                    error=str(e),
                    duration_seconds=timer.elapsed_seconds,
                )
                raise PluginError(
                    f"Plugin '{self.NAME}' failed: {e}",
                    plugin_name=self.NAME,
                ) from e

    @abc.abstractmethod
    async def execute(
        self,
        context: PluginContext,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Implement the plugin's actual logic here.

        Args:
            context: Restricted PluginContext with declared capabilities.
            input_data: Task-specific parameters.

        Returns:
            Dict with at minimum: {"success": bool, "result": ...}
        """

    async def health_check(self) -> bool:
        """
        Verify the plugin is healthy and ready to execute.

        Override to check that external dependencies (browsers,
        APIs, etc.) are available before the plugin is used.

        Returns:
            True if the plugin is ready, False otherwise.
        """
        return True

    async def teardown(self) -> None:
        """
        Clean up after plugin execution.

        Override to close connections, release resources, etc.
        Called after execute() regardless of success or failure.
        """

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name={self.NAME!r}, "
            f"version={self.VERSION!r}, "
            f"type={self.PLUGIN_TYPE!r})"
        )
