"""Git operation tools: commit, push, diff, branch."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult
from ..sandbox import ToolSandbox


class GitCommitTool(BaseTool):
    name = "git_commit"
    description = "Stage files and create a git commit"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Commit message"},
                "files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files to stage (empty = all modified)",
                    "default": [],
                },
                "repo_path": {"type": "string", "default": "."},
            },
            "required": ["message"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        message = kwargs.get("message", "")
        files = kwargs.get("files", [])
        repo_path = kwargs.get("repo_path", ".")
        sandbox = ToolSandbox()

        if files:
            add_cmd = f"git -C {repo_path} add {' '.join(files)}"
        else:
            add_cmd = f"git -C {repo_path} add -A"

        result = await sandbox.run_command(
            f'{add_cmd} && git -C {repo_path} commit -m "{message}"',
            timeout=30.0,
        )
        if result["success"]:
            return ToolResult(output=result["stdout"])
        return ToolResult(success=False, error=result["stderr"])


class GitPushTool(BaseTool):
    name = "git_push"
    description = "Push commits to the remote repository"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "default": ""},
                "repo_path": {"type": "string", "default": "."},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        branch = kwargs.get("branch", "")
        repo_path = kwargs.get("repo_path", ".")
        sandbox = ToolSandbox()
        cmd = f"git -C {repo_path} push"
        if branch:
            cmd += f" origin {branch}"
        result = await sandbox.run_command(cmd, timeout=60.0)
        if result["success"]:
            return ToolResult(output=result["stdout"])
        return ToolResult(success=False, error=result["stderr"])


class GitDiffTool(BaseTool):
    name = "git_diff"
    description = "Show the current git diff (staged and unstaged changes)"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "staged": {"type": "boolean", "default": False},
                "repo_path": {"type": "string", "default": "."},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        staged = kwargs.get("staged", False)
        repo_path = kwargs.get("repo_path", ".")
        sandbox = ToolSandbox()
        cmd = f"git -C {repo_path} diff"
        if staged:
            cmd += " --staged"
        result = await sandbox.run_command(cmd, timeout=15.0)
        return ToolResult(output=result["stdout"])


class GitBranchTool(BaseTool):
    name = "git_branch"
    description = "Create, list, or switch git branches"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "create", "checkout"],
                    "default": "list",
                },
                "name": {"type": "string", "description": "Branch name", "default": ""},
                "repo_path": {"type": "string", "default": "."},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "list")
        name = kwargs.get("name", "")
        repo_path = kwargs.get("repo_path", ".")
        sandbox = ToolSandbox()

        if action == "list":
            cmd = f"git -C {repo_path} branch -a"
        elif action == "create":
            cmd = f"git -C {repo_path} checkout -b {name}"
        elif action == "checkout":
            cmd = f"git -C {repo_path} checkout {name}"
        else:
            return ToolResult(success=False, error=f"Unknown action: {action}")

        result = await sandbox.run_command(cmd, timeout=15.0)
        if result["success"]:
            return ToolResult(output=result["stdout"])
        return ToolResult(success=False, error=result["stderr"])
