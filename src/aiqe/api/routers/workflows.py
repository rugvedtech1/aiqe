"""
AIQE FastAPI — Workflow Endpoints.

POST   /workflows              — create and start a workflow
GET    /workflows              — list workflows (paginated)
GET    /workflows/{id}         — get a specific workflow
DELETE /workflows/{id}         — cancel a workflow
GET    /workflows/{id}/bugs    — list bugs from a workflow
GET    /workflows/{id}/audit   — get the audit trail
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status

from aiqe.api.dependencies import (
    AuthDep,
    CorrelationIDDep,
    RepositoryBundleDep,
    WorkflowEngineDep,
)
from aiqe.api.schemas import (
    BugListResponse,
    BugResponse,
    CreateWorkflowRequest,
    WorkflowListResponse,
    WorkflowResponse,
)
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])


def _workflow_to_response(wf: dict[str, Any]) -> WorkflowResponse:
    """Convert a raw workflow dict to a WorkflowResponse schema."""
    from aiqe.api.schemas import AgentRecordSchema

    agent_records = {}
    for name, rec in wf.get("agent_records", {}).items():
        agent_records[name] = AgentRecordSchema(
            status=rec.get("status", "pending"),
            duration_seconds=rec.get("duration_seconds", 0.0),
            error=rec.get("error"),
            skip_reason=rec.get("skip_reason"),
            blocked_by=rec.get("blocked_by"),
            ai_tokens_used=rec.get("ai_tokens_used", 0),
        )

    return WorkflowResponse(
        id=wf.get("id", ""),
        status=wf.get("status", "pending"),
        trigger=wf.get("trigger", "manual"),
        repository=wf.get("repository", ""),
        branch=wf.get("branch", ""),
        pr_number=wf.get("pr_number"),
        bugs_count=wf.get("bugs_count", 0),
        agents_completed=wf.get("agents_completed", 0),
        agents_skipped=wf.get("agents_skipped", 0),
        agent_records=agent_records,
        error=wf.get("error"),
        workspace_path=wf.get("workspace_path", ""),
        started_at=wf.get("started_at"),
        completed_at=wf.get("completed_at"),
        duration_seconds=wf.get("duration_seconds"),
        created_at=wf.get("created_at", ""),
    )


@router.post(
    "",
    response_model=WorkflowResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create and start a workflow",
    description=(
        "Creates an isolated WorkflowContext and starts the "
        "AIQE quality engineering workflow asynchronously. "
        "Returns the workflow ID immediately. "
        "Poll GET /workflows/{id} to check progress."
    ),
)
async def create_workflow(
    request: CreateWorkflowRequest,
    background_tasks: BackgroundTasks,
    engine: WorkflowEngineDep,
    bundle: RepositoryBundleDep,
    correlation_id: CorrelationIDDep,
    auth: AuthDep,
) -> WorkflowResponse:
    """Create and start a new AIQE workflow."""
    from pathlib import Path
    from aiqe.agents.registry_setup import register_all_agents

    register_all_agents()

    context = await engine.create_context(
        trigger=request.trigger.value,
        repository=request.repository,
        branch=request.branch,
        pr_number=request.pr_number,
    )

    # Persist the initial context
    context_dict = context.to_dict()
    await bundle.workflows.save(context_dict)

    logger.info(
        "workflow_created_via_api",
        workflow_id=context.id,
        trigger=request.trigger.value,
        repository=request.repository,
        correlation_id=correlation_id,
    )

    # Run workflow in background so API returns immediately
    if not request.dry_run:
        background_tasks.add_task(
            _run_workflow_background,
            context=context,
            engine=engine,
            bundle=bundle,
        )

    return _workflow_to_response(context_dict)


async def _run_workflow_background(
    context: Any,
    engine: Any,
    bundle: Any,
) -> None:
    """Execute a workflow in the background and persist results."""
    try:
        completed_context = await engine.run(context=context)
        await bundle.workflows.save(completed_context.to_dict())

        # Persist bugs
        for bug in completed_context.bugs:
            await bundle.bugs.save({
                **bug,
                "workflow_id": completed_context.id,
                "repository": completed_context.repository,
            })

        # Persist audit log
        if completed_context.audit_log:
            await bundle.audit.append_batch(
                completed_context.id,
                completed_context.audit_log,
            )

    except Exception as e:
        logger.error(
            "background_workflow_failed",
            workflow_id=context.id,
            error=str(e),
        )


@router.get(
    "",
    response_model=WorkflowListResponse,
    summary="List workflows",
    description=(
        "Returns a paginated list of workflows. "
        "Filter by repository or status."
    ),
)
async def list_workflows(
    bundle: RepositoryBundleDep,
    auth: AuthDep,
    repository: Optional[str] = Query(
        default=None,
        description="Filter by repository (owner/repo format).",
    ),
    active_only: bool = Query(
        default=False,
        description="Return only active (running/checkpointed) workflows.",
    ),
    limit: int = Query(
        default=20,
        ge=1,
        le=100,
        description="Maximum number of workflows to return.",
    ),
) -> WorkflowListResponse:
    """List workflow executions."""
    if active_only:
        workflows = await bundle.workflows.find_active()
    elif repository:
        workflows = await bundle.workflows.find_by_repository(
            repository, limit=limit
        )
    else:
        workflows = await bundle.workflows.find_active()

    return WorkflowListResponse(
        workflows=[_workflow_to_response(wf) for wf in workflows],
        total=len(workflows),
    )


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    summary="Get a specific workflow",
    description="Returns the full details of a workflow by ID.",
)
async def get_workflow(
    workflow_id: str,
    bundle: RepositoryBundleDep,
    auth: AuthDep,
) -> WorkflowResponse:
    """Get a specific workflow by ID."""
    wf = await bundle.workflows.find_by_id(workflow_id)

    if wf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "workflow_not_found",
                "message": f"Workflow '{workflow_id}' not found.",
                "workflow_id": workflow_id,
            },
        )

    return _workflow_to_response(wf)


@router.get(
    "/{workflow_id}/bugs",
    response_model=BugListResponse,
    summary="List bugs from a workflow",
    description=(
        "Returns all bugs found during a workflow execution, "
        "ordered by severity (Critical first). "
        "Includes root cause analysis and evidence (ADR-011)."
    ),
)
async def list_workflow_bugs(
    workflow_id: str,
    bundle: RepositoryBundleDep,
    auth: AuthDep,
    severity: Optional[str] = Query(
        default=None,
        description="Filter by severity: Critical, High, Medium, Low, Informational.",
    ),
) -> BugListResponse:
    """List bugs discovered during a workflow execution."""
    wf = await bundle.workflows.find_by_id(workflow_id)
    if wf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "workflow_not_found", "workflow_id": workflow_id},
        )

    if severity:
        bugs_raw = await bundle.bugs.find_by_severity(
            severity=severity,
            repository=wf.get("repository"),
        )
        bugs_raw = [b for b in bugs_raw if b.get("workflow_id") == workflow_id]
    else:
        bugs_raw = await bundle.bugs.find_by_workflow(workflow_id)

    counts = await bundle.bugs.count_by_workflow(workflow_id)

    bugs = [
        BugResponse(
            id=b.get("id", ""),
            severity=b.get("severity", ""),
            confidence=b.get("confidence", 0.0),
            title=b.get("title", ""),
            root_cause=b.get("root_cause", ""),
            evidence=[
                {"kind": e.get("kind", ""), "content": e.get("content", ""),
                 "source": e.get("source", ""), "relevance": e.get("relevance", "")}
                for e in b.get("evidence", [])
            ],
            affected_feature=b.get("affected_feature", ""),
            affected_files=b.get("affected_files", []),
            dependency_chain=b.get("dependency_chain", []),
            suggested_fix=b.get("suggested_fix", ""),
            fix_confidence=b.get("fix_confidence", 0.0),
            is_downstream=b.get("is_downstream", False),
            root_bug_id=b.get("root_bug_id"),
            related_tests=b.get("related_tests", []),
            workflow_id=workflow_id,
            repository=b.get("repository", ""),
        )
        for b in bugs_raw
    ]

    return BugListResponse(bugs=bugs, total=len(bugs), by_severity=counts)


@router.get(
    "/{workflow_id}/audit",
    summary="Get workflow audit trail",
    description=(
        "Returns the complete audit trail for a workflow. "
        "Includes every agent execution, AI call, tool invocation, "
        "and system event. See ADR-012."
    ),
)
async def get_workflow_audit(
    workflow_id: str,
    bundle: RepositoryBundleDep,
    auth: AuthDep,
    event_type: Optional[str] = Query(
        default=None,
        description="Filter by event type (e.g. agent_started, bug_found).",
    ),
    limit: int = Query(
        default=500,
        ge=1,
        le=5000,
        description="Maximum audit entries to return.",
    ),
) -> dict[str, Any]:
    """Get the complete audit trail for a workflow."""
    wf = await bundle.workflows.find_by_id(workflow_id)
    if wf is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "workflow_not_found", "workflow_id": workflow_id},
        )

    entries = await bundle.audit.find_by_workflow(
        workflow_id=workflow_id,
        event_type=event_type,
        limit=limit,
    )

    return {
        "workflow_id": workflow_id,
        "total_entries": len(entries),
        "entries": entries,
    }


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Cancel or delete a workflow",
    description=(
        "Cancels a running workflow or deletes a completed one. "
        "This is irreversible."
    ),
)
async def delete_workflow(
    workflow_id: str,
    bundle: RepositoryBundleDep,
    auth: AuthDep,
) -> None:
    """Cancel or delete a workflow."""
    deleted = await bundle.workflows.delete(workflow_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "workflow_not_found", "workflow_id": workflow_id},
        )
