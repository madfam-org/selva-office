from fastapi import APIRouter, Request, HTTPException
from typing import Dict, Any
import logging
from ..tasks.acp_tasks import run_acp_workflow_task

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/gateway", tags=["Gateway"])

@router.post("/telegram/webhook")
async def telegram_webhook(request: Request) -> Dict[str, Any]:
    """
    Simulates Hermes Agent's multi-channel capability.
    Receives Telegram messages and routes slash commands directly to internal tasks.
    """
    payload = await request.json()
    message = payload.get("message", {})
    text = message.get("text", "")
    
    if text.startswith("/initiate_acp"):
        parts = text.split(" ")
        if len(parts) > 1:
            target_url = parts[1]
            # Formally trigger the Celery task without requiring Dashboard UI access
            task = run_acp_workflow_task.delay(target_url)
            logger.info(f"Gateway triggered ACP for {target_url} from Telegram (Task {task.id})")
            return {"status": "success", "action": "acp_triggered"}
            
    return {"status": "ignored"}

@router.post("/discord/webhook")
async def discord_webhook(request: Request) -> Dict[str, Any]:
    """
    Simulates Hermes Agent's multi-channel capability for Discord.
    """
    payload = await request.json()
    content = payload.get("content", "")
    
    if content.startswith("/status"):
        # Could query EdgeMemoryDB here and return recent transcripts
        return {"status": "success", "message": "All Clean Swarms operational."}
        
    return {"status": "ignored"}
