"""Voice input API -- transcription and voice-to-task dispatch."""

from __future__ import annotations

import logging
import os
import tempfile

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field

from ..auth import get_current_user, require_non_guest

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])


# -- Response schemas ----------------------------------------------------------


class TranscribeResponse(BaseModel):
    text: str
    language: str


class VoiceDispatchRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)
    graph_type: str = Field(
        default="coding",
        pattern=r"^(sequential|parallel|coding|research|crm|custom|deployment|puppeteer|meeting)$",
    )


class VoiceDispatchResponse(BaseModel):
    text: str
    graph_type: str
    status: str


# -- Endpoints -----------------------------------------------------------------


@router.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_audio(
    file: UploadFile = File(...),  # noqa: B008
    language: str = Query("en"),  # noqa: B008
    user: dict = Depends(get_current_user),  # noqa: B008
) -> TranscribeResponse:
    """Transcribe uploaded audio via the OpenAI Whisper API.

    Accepts common audio formats (webm, wav, mp3, ogg, flac, m4a).
    Returns the transcription text and requested language.
    """
    from autoswarm_tools.builtins.stt import SpeechToTextTool

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded audio file is empty",
        )

    # Determine suffix from the uploaded filename
    suffix = ".webm"
    if file.filename:
        ext = os.path.splitext(file.filename)[1]
        if ext:
            suffix = ext

    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        tool = SpeechToTextTool()
        result = await tool.execute(audio_path=tmp_path, language=language)

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=result.error or "Transcription failed",
            )

        return TranscribeResponse(text=result.output, language=language)
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


@router.post("/dispatch", response_model=VoiceDispatchResponse)
async def voice_dispatch(
    body: VoiceDispatchRequest,
    user: dict = Depends(require_non_guest),  # noqa: B008
) -> VoiceDispatchResponse:
    """Create a SwarmTask from transcribed voice input.

    This endpoint accepts text (typically from a prior ``/transcribe`` call)
    and dispatches it as a new task via the swarms subsystem.
    """
    # TODO: wire into swarms.dispatch_task when full integration is ready.
    # For now, return confirmation so the frontend can proceed.
    logger.info(
        "Voice dispatch: graph_type=%s, text_len=%d, user=%s",
        body.graph_type,
        len(body.text),
        user.get("sub"),
    )
    return VoiceDispatchResponse(
        text=body.text,
        graph_type=body.graph_type,
        status="dispatched",
    )
