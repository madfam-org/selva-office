"""Built-in tools for AutoSwarm agents."""

from __future__ import annotations

from ..base import BaseTool

# Wave 4 additions
from ..execute_code import ExecuteCodeTool
from ..extra_tools import DelegateTaskTool, ReadCredentialFileTool, WebExtractTool
from ..extra_tools import WebSearchTool as WebSearchToolV2
from ..media_tools import GenerateImageTool, TextToSpeechTool
from ..process_registry import (
    KillBackgroundProcessTool,
    ListBackgroundProcessesTool,
    StartBackgroundProcessTool,
)
from .artifact import ListArtifactsTool, RetrieveArtifactTool, SaveArtifactTool
from .code import BashExecTool, PythonExecTool
from .communication import CreateReportTool, SendNotificationTool
from .data import CsvReadTool, DataTransformTool, JsonParseTool
from .deploy import DeployStatusTool, DeployTool
from .environment import EnvInfoTool, PackageInstallTool
from .files import FileDeleteTool, FileListTool, FileReadTool, FileSearchTool, FileWriteTool
from .git import GitBranchTool, GitCommitTool, GitDiffTool, GitPushTool
from .image_analysis import ImageAnalysisTool
from .slack import SlackMessageTool
from .stt import SpeechToTextTool
from .web import WebFetchTool, WebScrapeTool, WebSearchTool


def get_builtin_tools() -> list[BaseTool]:
    """Return all built-in tool instances."""
    return [
        # File ops
        FileReadTool(),
        FileWriteTool(),
        FileListTool(),
        FileDeleteTool(),
        FileSearchTool(),
        # Code (original)
        PythonExecTool(),
        BashExecTool(),
        # Wave 4: execute_code sandbox (approval-gated)
        ExecuteCodeTool(),
        # Wave 4: process registry
        StartBackgroundProcessTool(),
        ListBackgroundProcessesTool(),
        KillBackgroundProcessTool(),
        # Git
        GitCommitTool(),
        GitPushTool(),
        GitDiffTool(),
        GitBranchTool(),
        # Web (original)
        WebSearchTool(),
        WebFetchTool(),
        WebScrapeTool(),
        # Wave 4: enhanced web tools
        WebSearchToolV2(),
        WebExtractTool(),
        # Data
        JsonParseTool(),
        CsvReadTool(),
        DataTransformTool(),
        # Communication
        SendNotificationTool(),
        CreateReportTool(),
        SlackMessageTool(),
        # Environment
        EnvInfoTool(),
        PackageInstallTool(),
        # Deployment
        DeployTool(),
        DeployStatusTool(),
        # Artifacts
        SaveArtifactTool(),
        RetrieveArtifactTool(),
        ListArtifactsTool(),
        # Image analysis (original) + Generation (Wave 4)
        ImageAnalysisTool(),
        GenerateImageTool(),
        TextToSpeechTool(),
        # Voice: speech-to-text
        SpeechToTextTool(),
        # Wave 4: delegation + credentials
        DelegateTaskTool(),
        ReadCredentialFileTool(),
    ]
