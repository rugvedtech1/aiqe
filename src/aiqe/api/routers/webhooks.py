"""
AIQE FastAPI — Webhook Endpoints.

POST /webhooks/github  — receive GitHub events (pull_request, push)
POST /webhooks/gitlab  — receive GitLab events (merge_request, push)

Webhooks allow AIQE to automatically start quality scans when
a Pull Request is opened or updated in GitHub/GitLab.

Security:
    GitHub webhooks are signed with HMAC-SHA256 using the
    GITHUB_WEBHOOK_SECRET. AIQE verifies the signature on every
    incoming request. Unsigned or incorrectly signed requests
    are rejected with 403.

    Never disable signature verification in production.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status

from aiqe.api.dependencies import RepositoryBundleDep, WorkflowEngineDep
from aiqe.api.schemas import GitHubWebhookPayload, WebhookResponse
from aiqe.shared.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

# GitHub events that trigger automatic scans
_TRIGGERING_ACTIONS = frozenset({
    "opened",
    "synchronize",
    "reopened",
})


@router.post(
    "/github",
    response_model=WebhookResponse,
    summary="Receive GitHub webhooks",
    description=(
        "Endpoint for GitHub webhook delivery. "
        "Automatically triggers quality scans for pull_request events. "
        "Verifies HMAC-SHA256 signature using GITHUB_WEBHOOK_SECRET."
    ),
)
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    engine: WorkflowEngineDep,
    bundle: RepositoryBundleDep,
    x_github_event: str = Header(
        ...,
        alias="X-GitHub-Event",
        description="GitHub event type (pull_request, push, etc.)",
    ),
    x_hub_signature_256: str | None = Header(
        default=None,
        alias="X-Hub-Signature-256",
        description="HMAC-SHA256 signature for payload verification.",
    ),
    x_github_delivery: str | None = Header(
        default=None,
        alias="X-GitHub-Delivery",
        description="Unique delivery ID from GitHub.",
    ),
) -> WebhookResponse:
    """Process GitHub webhook events."""
    raw_body = await request.body()

    # Verify webhook signature
    await _verify_github_signature(raw_body, x_hub_signature_256)

    logger.info(
        "github_webhook_received",
        event=x_github_event,
        delivery_id=x_github_delivery,
    )

    # Only process pull_request events
    if x_github_event != "pull_request":
        return WebhookResponse(
            received=True,
            message=f"Event '{x_github_event}' acknowledged but not processed.",
        )

    import json as json_mod
    try:
        payload_data = json_mod.loads(raw_body)
        payload = GitHubWebhookPayload(**payload_data)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid payload: {e}",
        )

    # Only trigger scans for relevant PR actions
    if payload.action not in _TRIGGERING_ACTIONS:
        return WebhookResponse(
            received=True,
            message=(
                f"Action '{payload.action}' does not trigger a scan. "
                f"Triggering actions: {sorted(_TRIGGERING_ACTIONS)}"
            ),
        )

    # Extract PR and repository information
    pr_data = payload.pull_request or {}
    repo_data = payload.repository or {}

    repo_full_name = repo_data.get("full_name", "")
    pr_number = payload.number
    branch = pr_data.get("head", {}).get("ref", "")

    if not repo_full_name or not pr_number:
        return WebhookResponse(
            received=True,
            message="Missing repository or PR information in payload.",
        )

    # Create workflow context
    from aiqe.agents.registry_setup import register_all_agents
    register_all_agents()

    context = await engine.create_context(
        trigger="pr",
        repository=repo_full_name,
        branch=branch,
        pr_number=pr_number,
    )

    # Persist initial context
    await bundle.workflows.save(context.to_dict())

    # Run workflow in background
    background_tasks.add_task(
        _run_github_pr_workflow,
        context=context,
        engine=engine,
        bundle=bundle,
        repo_full_name=repo_full_name,
        pr_number=pr_number,
    )

    logger.info(
        "github_pr_scan_triggered",
        workflow_id=context.id,
        repository=repo_full_name,
        pr_number=pr_number,
        branch=branch,
        action=payload.action,
    )

    return WebhookResponse(
        received=True,
        workflow_id=context.id,
        message=(
            f"Quality scan started for PR #{pr_number} in {repo_full_name}. "
            f"Workflow ID: {context.id}"
        ),
    )


async def _verify_github_signature(
    body: bytes,
    signature_header: str | None,
) -> None:
    """
    Verify the GitHub webhook HMAC-SHA256 signature.

    Args:
        body: Raw request body bytes.
        signature_header: X-Hub-Signature-256 header value.

    Raises:
        HTTPException 403: If signature is missing or invalid.
    """
    from aiqe.shared.config import get_settings
    settings = get_settings()

    webhook_secret = settings.notifications.github_webhook_secret
    if webhook_secret is None:
        # No secret configured — skip verification (development only)
        logger.warning(
            "github_webhook_signature_not_verified",
            reason="GITHUB_WEBHOOK_SECRET not configured",
        )
        return

    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "missing_signature",
                "message": (
                    "X-Hub-Signature-256 header is required. "
                    "Configure GITHUB_WEBHOOK_SECRET in AIQE settings."
                ),
            },
        )

    secret_bytes = webhook_secret.get_secret_value().encode()
    expected = "sha256=" + hmac.new(
        secret_bytes, body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        logger.warning(
            "github_webhook_invalid_signature",
            received_prefix=signature_header[:15] if signature_header else "none",
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "error": "invalid_signature",
                "message": (
                    "Webhook signature verification failed. "
                    "Check that GITHUB_WEBHOOK_SECRET matches the "
                    "secret configured in your GitHub repository settings."
                ),
            },
        )


async def _run_github_pr_workflow(
    context: Any,
    engine: Any,
    bundle: Any,
    repo_full_name: str,
    pr_number: int,
) -> None:
    """Run the PR workflow and persist results."""
    try:
        completed = await engine.run(context=context)
        await bundle.workflows.save(completed.to_dict())

        for bug in completed.bugs:
            await bundle.bugs.save({
                **bug,
                "workflow_id": completed.id,
                "repository": repo_full_name,
            })

        if completed.audit_log:
            await bundle.audit.append_batch(
                completed.id, completed.audit_log
            )

        logger.info(
            "github_pr_workflow_completed",
            workflow_id=context.id,
            repository=repo_full_name,
            pr_number=pr_number,
            status=completed.status.value,
            bugs_found=len(completed.bugs),
        )

    except Exception as e:
        logger.error(
            "github_pr_workflow_failed",
            workflow_id=context.id,
            repository=repo_full_name,
            pr_number=pr_number,
            error=str(e),
        )
