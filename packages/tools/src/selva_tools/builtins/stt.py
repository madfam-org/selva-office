"""Speech-to-text transcription tool using OpenAI Whisper API."""

from __future__ import annotations

import logging
import os
from typing import Any

from ..base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class SpeechToTextTool(BaseTool):
    """Transcribe audio to text using the OpenAI Whisper API."""

    name = "speech_to_text"
    description = (
        "Transcribe audio to text using OpenAI's Whisper model. "
        "Accepts a local file path to an audio file and returns the transcription."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "audio_path": {
                    "type": "string",
                    "description": "Path to the audio file to transcribe",
                },
                "language": {
                    "type": "string",
                    "default": "en",
                    "description": "ISO-639-1 language code (e.g. 'en', 'es', 'fr')",
                },
                "model": {
                    "type": "string",
                    "enum": ["whisper-1"],
                    "default": "whisper-1",
                    "description": "Whisper model to use",
                },
            },
            "required": ["audio_path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        audio_path: str = kwargs.get("audio_path", "")
        language: str = kwargs.get("language", "en")
        model: str = kwargs.get("model", "whisper-1")

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return ToolResult(success=False, error="OPENAI_API_KEY not set.")

        if not os.path.exists(audio_path):
            return ToolResult(success=False, error=f"Audio file not found: {audio_path}")

        try:
            import httpx

            # Determine content type from extension
            ext = os.path.splitext(audio_path)[1].lower()
            content_type_map = {
                ".wav": "audio/wav",
                ".mp3": "audio/mpeg",
                ".webm": "audio/webm",
                ".ogg": "audio/ogg",
                ".flac": "audio/flac",
                ".m4a": "audio/mp4",
            }
            content_type = content_type_map.get(ext, "audio/wav")
            filename = os.path.basename(audio_path)

            with open(audio_path, "rb") as f:
                audio_bytes = f.read()

            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    files={"file": (filename, audio_bytes, content_type)},
                    data={"model": model, "language": language},
                )
                resp.raise_for_status()
                data = resp.json()
                text = data.get("text", "")

            return ToolResult(
                output=text,
                data={"text": text, "language": language, "model": model},
            )
        except Exception as exc:
            logger.error("speech_to_text failed: %s", exc)
            return ToolResult(success=False, error=str(exc))
