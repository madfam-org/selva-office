"""Tests for the SpeechToTextTool."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

from autoswarm_tools.builtins import get_builtin_tools
from autoswarm_tools.builtins.stt import SpeechToTextTool


class TestSpeechToTextToolMetadata:
    def test_name(self) -> None:
        tool = SpeechToTextTool()
        assert tool.name == "speech_to_text"

    def test_description(self) -> None:
        tool = SpeechToTextTool()
        assert "transcribe" in tool.description.lower()
        assert "whisper" in tool.description.lower()

    def test_parameters_schema_is_valid(self) -> None:
        tool = SpeechToTextTool()
        schema = tool.parameters_schema()
        assert schema["type"] == "object"
        assert "audio_path" in schema["properties"]
        assert "language" in schema["properties"]
        assert "model" in schema["properties"]
        assert "audio_path" in schema["required"]

    def test_openai_spec_format(self) -> None:
        tool = SpeechToTextTool()
        spec = tool.to_openai_spec()
        assert spec["type"] == "function"
        assert spec["function"]["name"] == "speech_to_text"
        assert "parameters" in spec["function"]
        assert "description" in spec["function"]


class TestSpeechToTextToolExecution:
    @pytest.mark.asyncio
    async def test_transcribe_success(self) -> None:
        tool = SpeechToTextTool()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "hello world"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("builtins.open", mock_open(read_data=b"fake audio data")),
            patch("os.path.exists", return_value=True),
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        ):
            result = await tool.execute(audio_path="/tmp/test.wav")

        assert result.success
        assert result.output == "hello world"
        assert result.data["text"] == "hello world"
        assert result.data["language"] == "en"

    @pytest.mark.asyncio
    async def test_transcribe_with_custom_language(self) -> None:
        tool = SpeechToTextTool()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "hola mundo"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("builtins.open", mock_open(read_data=b"audio")),
            patch("os.path.exists", return_value=True),
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        ):
            result = await tool.execute(audio_path="/tmp/test.mp3", language="es")

        assert result.success
        assert result.data["language"] == "es"
        assert result.data["text"] == "hola mundo"

    @pytest.mark.asyncio
    async def test_transcribe_no_api_key(self) -> None:
        tool = SpeechToTextTool()
        with patch.dict("os.environ", {}, clear=True):
            result = await tool.execute(audio_path="/tmp/test.wav")
        assert not result.success
        assert "OPENAI_API_KEY" in (result.error or "")

    @pytest.mark.asyncio
    async def test_transcribe_file_not_found(self) -> None:
        tool = SpeechToTextTool()
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            result = await tool.execute(audio_path="/tmp/nonexistent_audio.wav")
        assert not result.success
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_transcribe_api_error(self) -> None:
        tool = SpeechToTextTool()
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(side_effect=Exception("API timeout"))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("builtins.open", mock_open(read_data=b"audio")),
            patch("os.path.exists", return_value=True),
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        ):
            result = await tool.execute(audio_path="/tmp/test.wav")

        assert not result.success
        assert "API timeout" in (result.error or "")

    @pytest.mark.asyncio
    async def test_content_type_detection(self) -> None:
        """Verify correct content type is inferred from file extension."""
        tool = SpeechToTextTool()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"text": "test"}
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with (
            patch("httpx.AsyncClient", return_value=mock_client),
            patch("builtins.open", mock_open(read_data=b"audio")),
            patch("os.path.exists", return_value=True),
            patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}),
        ):
            result = await tool.execute(audio_path="/tmp/test.webm")

        assert result.success
        # Verify the POST was called with webm content type in the files arg
        call_kwargs = mock_client.post.call_args
        files_arg = call_kwargs.kwargs.get("files") or call_kwargs[1].get("files")
        assert files_arg is not None
        file_tuple = files_arg["file"]
        assert file_tuple[2] == "audio/webm"


class TestSpeechToTextToolRegistration:
    def test_appears_in_builtin_tools(self) -> None:
        tools = get_builtin_tools()
        tool_names = [t.name for t in tools]
        assert "speech_to_text" in tool_names

    def test_builtin_instance_type(self) -> None:
        tools = get_builtin_tools()
        stt_tools = [t for t in tools if t.name == "speech_to_text"]
        assert len(stt_tools) == 1
        assert isinstance(stt_tools[0], SpeechToTextTool)
