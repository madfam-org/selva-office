import hashlib
import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, HttpUrl

from ..auth import require_role
from ..config import get_settings
from ..memory_store.db import memory_store
from ..tasks.acp_tasks import run_acp_workflow_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/acp", tags=["acp"])


class InitiateACPRequest(BaseModel):
    target_url: HttpUrl
    description: str


class QAOracleWebhook(BaseModel):
    run_id: str
    status: str
    logs: str


def run_acp_workflow_background(target_url: str):
    """
    Background task to actually orchestrate the ACP cycle.
    In a real implementation, this would trigger the LangGraph Phase I Analyst workflow
    which in turn calls the EncliiAdapter.
    """
    logger.info(f"Starting ACP dirty analyst workflow for {target_url}")
    # from selva_workflows.acp_analyst import run_analyst
    # run_analyst(target_url)


@router.post("/initiate")
async def initiate_acp(
    request: InitiateACPRequest, user: dict = Depends(require_role("enterprise-cleanroom"))
) -> dict[str, Any]:
    """
    Initiates the Autonomous Cleanroom Protocol (ACP).
    Requires 'enterprise-cleanroom' Janua RBAC role.
    """
    logger.info(f"User {user.get('sub')} initiated ACP for {request.target_url}")
    # Dispatch to Celery worker
    task = run_acp_workflow_task.delay(str(request.target_url))
    return {
        "status": "accepted",
        "message": "ACP Pipeline Phase I: Analyst initiated.",
        "task_id": task.id,
        "target_url": str(request.target_url),
    }


@router.get("/payloads/{run_id}")
async def get_acp_payload(run_id: str) -> dict[str, Any]:
    """
    Secure endpoint providing the sanitized Phase II PRD to the Clean Swarm.
    Acts as the Airgap storage intermediary pulling from Redis.
    """
    # Pseudocode for Redis retrieval
    # redis = request.app.state.redis
    # payload = await redis.get(f"acp:prd:{run_id}")
    logger.info(f"Clean Swarm requested payload for {run_id}")

    memory_store.insert_transcript(
        run_id=run_id,
        agent_role="acp-clean-swarm",
        role="system",
        content="Requested sanitized payload via secure airgap bridge.",
    )
    return {"status": "success", "run_id": run_id, "prd": "Sanitized PRD SPEC from Redis Proxy"}


@router.post("/webhook/qa-oracle")
async def qa_oracle_webhook(
    request: Request, payload: QAOracleWebhook, x_enclii_signature: str = Header(None)
) -> dict[str, Any]:
    """
    Phase IV webhook entry. The Enclii QA pod posts results here.
    Validates Enclii HMAC webhook signature.
    """
    settings = get_settings()

    # Enforce webhook security via HMAC SHA256 if secret is set
    if settings.enclii_webhook_secret:
        if not x_enclii_signature:
            raise HTTPException(status_code=401, detail="Missing X-Enclii-Signature header")

        body = await request.body()
        expected_mac = hmac.new(
            settings.enclii_webhook_secret.encode(), body, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(expected_mac, x_enclii_signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    memory_store.insert_transcript(
        run_id=payload.run_id,
        agent_role="acp-qa-oracle",
        role="assistant",
        content=f"Phase IV validation returned status: {payload.status}",
    )

    if payload.status == "success":
        logger.info(f"[ACP Run {payload.run_id}] QA Passed. Initiating teardown.")
        return {"action": "teardown_initiated"}
    else:
        logger.warning(f"[ACP Run {payload.run_id}] QA Failed. Cycling Phase III.")
        return {"action": "re_triggering_phase_iii"}
