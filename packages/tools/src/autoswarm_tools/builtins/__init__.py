"""Built-in tools for AutoSwarm agents."""

from __future__ import annotations

from ..base import BaseTool
from .artifact import ListArtifactsTool, RetrieveArtifactTool, SaveArtifactTool
from .code import BashExecTool, PythonExecTool
from .communication import CreateReportTool, SendNotificationTool
from .data import CsvReadTool, DataTransformTool, JsonParseTool
from .deploy import DeployStatusTool, DeployTool
from .environment import EnvInfoTool, PackageInstallTool
from .files import FileDeleteTool, FileListTool, FileReadTool, FileSearchTool, FileWriteTool
from .git import GitBranchTool, GitCommitTool, GitDiffTool, GitPushTool
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
        # Code
        PythonExecTool(),
        BashExecTool(),
        # Git
        GitCommitTool(),
        GitPushTool(),
        GitDiffTool(),
        GitBranchTool(),
        # Web
        WebSearchTool(),
        WebFetchTool(),
        WebScrapeTool(),
        # Data
        JsonParseTool(),
        CsvReadTool(),
        DataTransformTool(),
        # Communication
        SendNotificationTool(),
        CreateReportTool(),
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
    ]
