"""Code execution tools: Python and Bash."""

from __future__ import annotations

from typing import Any

from ..base import BaseTool, ToolResult
from ..sandbox import ToolSandbox


class PythonExecTool(BaseTool):
    name = "python_exec"
    description = "Execute Python code in a sandboxed environment and return the result"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {"type": "string", "description": "Python code to execute"},
            },
            "required": ["code"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        code = kwargs.get("code", "")
        sandbox = ToolSandbox()
        try:
            result = await sandbox.run_command(
                f"python3 -c {_shell_quote(code)}",
                timeout=30.0,
            )
            if result["success"]:
                return ToolResult(output=result["stdout"], data=result)
            return ToolResult(
                success=False,
                output=result["stdout"],
                error=result["stderr"],
            )
        finally:
            sandbox.cleanup()


class BashExecTool(BaseTool):
    name = "bash_exec"
    description = "Execute a bash command and return stdout/stderr"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Bash command to execute"},
                "timeout": {
                    "type": "number",
                    "description": "Timeout in seconds",
                    "default": 30.0,
                },
            },
            "required": ["command"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command", "")
        timeout = kwargs.get("timeout", 30.0)
        sandbox = ToolSandbox()
        try:
            result = await sandbox.run_command(command, timeout=timeout)
            if result["success"]:
                return ToolResult(output=result["stdout"], data=result)
            return ToolResult(
                success=False,
                output=result["stdout"],
                error=result["stderr"],
            )
        finally:
            sandbox.cleanup()


def _shell_quote(s: str) -> str:
    """Quote a string for safe shell use."""
    import shlex

    return shlex.quote(s)
