"""
AIQE Checkpoint Manager.

Implements stage-level checkpointing for long-running workflows.
If an AI provider fails or the process is interrupted, the workflow
can resume from the last saved checkpoint instead of restarting
from scratch. See ADR-001 and ADR-006.

Checkpoint stages (in execution order):
    project_analysis
    dependency_intelligence
    test_strategy
    test_case_generation
    automation_generation
    browser_execution
    api_validation
    security_testing
    performance_testing
    database_validation
    bug_analysis
    report_generation

Design:
    Checkpoints are stored as JSON files in the workflow's isolated
    workspace directory. Each checkpoint contains the complete
    serialized state of the completed stage so it can be restored
    without re-running the stage.

    In enterprise mode, checkpoints will be stored in Postgres
    via the repository layer (ADR-002). The CheckpointManager
    abstracts over this — callers never know where checkpoints live.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aiqe.shared.exceptions import CheckpointError
from aiqe.shared.logging import get_logger
from aiqe.shared.utils import utcnow, _new_id

logger = get_logger(__name__)

# The ordered list of workflow stages. Used to determine which
# stages have already completed when resuming from a checkpoint.
WORKFLOW_STAGES = [
    "project_analysis",
    "dependency_intelligence",
    "test_strategy",
    "test_case_generation",
    "automation_generation",
    "browser_execution",
    "api_validation",
    "security_testing",
    "performance_testing",
    "database_validation",
    "bug_analysis",
    "report_generation",
]


@dataclass
class Checkpoint:
    """
    A saved snapshot of a completed workflow stage.

    Attributes:
        id: Unique identifier for this checkpoint.
        workflow_id: The workflow this checkpoint belongs to.
        stage: The stage name (from WORKFLOW_STAGES).
        state: The serialized stage output — whatever the agent returned.
        saved_at: When this checkpoint was created.
        stage_index: Position of this stage in WORKFLOW_STAGES (for ordering).
    """
    id: str
    workflow_id: str
    stage: str
    state: dict[str, Any]
    saved_at: datetime
    stage_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "stage": self.stage,
            "state": self.state,
            "saved_at": self.saved_at.isoformat(),
            "stage_index": self.stage_index,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Checkpoint:
        return cls(
            id=data["id"],
            workflow_id=data["workflow_id"],
            stage=data["stage"],
            state=data["state"],
            saved_at=datetime.fromisoformat(data["saved_at"]),
            stage_index=data["stage_index"],
        )


class CheckpointManager:
    """
    Manages checkpoint save and restore for workflow stages.

    Each WorkflowContext gets its own CheckpointManager pointing
    to its isolated workspace directory. Checkpoints from one
    workflow are never visible to another workflow's manager.

    Args:
        workflow_id: The workflow this manager belongs to.
        workspace_path: The workflow's isolated workspace directory.
    """

    def __init__(self, workflow_id: str, workspace_path: Path) -> None:
        self._workflow_id = workflow_id
        self._checkpoint_dir = workspace_path / "checkpoints"
        self._checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, Checkpoint] = {}

    async def save(self, stage: str, state: dict[str, Any]) -> Checkpoint:
        """
        Save a checkpoint for a completed stage.

        Args:
            stage: The completed stage name (must be in WORKFLOW_STAGES).
            state: The serialized output of the completed stage.

        Returns:
            The saved Checkpoint object.

        Raises:
            CheckpointError: If the stage name is invalid or save fails.
        """
        if stage not in WORKFLOW_STAGES:
            msg = (
                f"Unknown checkpoint stage '{stage}'. "
                f"Valid stages: {WORKFLOW_STAGES}"
            )
            raise CheckpointError(msg, workflow_id=self._workflow_id)

        checkpoint = Checkpoint(
            id=_new_id(),
            workflow_id=self._workflow_id,
            stage=stage,
            state=state,
            saved_at=utcnow(),
            stage_index=WORKFLOW_STAGES.index(stage),
        )

        checkpoint_path = self._checkpoint_dir / f"{stage}.json"
        try:
            checkpoint_path.write_text(
                json.dumps(checkpoint.to_dict(), indent=2),
                encoding="utf-8",
            )
            self._cache[stage] = checkpoint
            logger.info(
                "checkpoint_saved",
                workflow_id=self._workflow_id,
                stage=stage,
                checkpoint_id=checkpoint.id,
                path=str(checkpoint_path),
            )
            return checkpoint
        except OSError as e:
            msg = f"Failed to save checkpoint for stage '{stage}': {e}"
            logger.error(
                "checkpoint_save_failed",
                workflow_id=self._workflow_id,
                stage=stage,
                error=str(e),
            )
            raise CheckpointError(msg, workflow_id=self._workflow_id) from e

    async def restore(self, stage: str) -> Checkpoint | None:
        """
        Restore a checkpoint for a specific stage.

        Args:
            stage: The stage name to restore.

        Returns:
            The Checkpoint if it exists, None if no checkpoint was saved.

        Raises:
            CheckpointError: If the checkpoint file is corrupted.
        """
        if stage in self._cache:
            return self._cache[stage]

        checkpoint_path = self._checkpoint_dir / f"{stage}.json"
        if not checkpoint_path.exists():
            return None

        try:
            data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            checkpoint = Checkpoint.from_dict(data)
            self._cache[stage] = checkpoint
            logger.info(
                "checkpoint_restored",
                workflow_id=self._workflow_id,
                stage=stage,
                checkpoint_id=checkpoint.id,
            )
            return checkpoint
        except (json.JSONDecodeError, KeyError) as e:
            msg = (
                f"Checkpoint file for stage '{stage}' in workflow "
                f"{self._workflow_id} is corrupted: {e}"
            )
            logger.error(
                "checkpoint_corrupted",
                workflow_id=self._workflow_id,
                stage=stage,
                error=str(e),
            )
            raise CheckpointError(msg, workflow_id=self._workflow_id) from e

    async def get_completed_stages(self) -> list[str]:
        """
        Return a list of all stages that have saved checkpoints,
        in execution order.

        Used when resuming a workflow to determine which stages
        can be skipped.

        Returns:
            Ordered list of completed stage names.
        """
        completed = []
        for stage in WORKFLOW_STAGES:
            checkpoint_path = self._checkpoint_dir / f"{stage}.json"
            if checkpoint_path.exists():
                completed.append(stage)
        return completed

    async def get_resume_stage(self) -> str | None:
        """
        Find the next stage to run when resuming from a checkpoint.

        Returns:
            The name of the first stage without a checkpoint,
            or None if all stages are complete.
        """
        completed = await self.get_completed_stages()
        for stage in WORKFLOW_STAGES:
            if stage not in completed:
                return stage
        return None

    async def clear(self) -> None:
        """
        Delete all checkpoints for this workflow.

        Called after a workflow completes successfully to clean up
        checkpoint files (the audit log is preserved separately).
        """
        for checkpoint_path in self._checkpoint_dir.glob("*.json"):
            try:
                checkpoint_path.unlink()
            except OSError as e:
                logger.warning(
                    "checkpoint_delete_failed",
                    workflow_id=self._workflow_id,
                    path=str(checkpoint_path),
                    error=str(e),
                )
        self._cache.clear()
        logger.info(
            "checkpoints_cleared",
            workflow_id=self._workflow_id,
        )
