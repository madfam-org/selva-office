"""File operation tools: read, write, list, delete, search."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..base import BaseTool, ToolResult


class FileReadTool(BaseTool):
    name = "file_read"
    description = "Read the contents of a file at the given path"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to read"},
                "max_lines": {
                    "type": "integer",
                    "description": "Max lines to read (0 = all)",
                    "default": 0,
                },
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", "")
        max_lines = kwargs.get("max_lines", 0)
        try:
            content = Path(path).read_text(encoding="utf-8")
            if max_lines > 0:
                lines = content.splitlines()[:max_lines]
                content = "\n".join(lines)
            return ToolResult(output=content)
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class FileWriteTool(BaseTool):
    name = "file_write"
    description = "Write content to a file, creating directories as needed"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"},
                "append": {
                    "type": "boolean",
                    "description": "Append instead of overwrite",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", "")
        content = kwargs.get("content", "")
        append = kwargs.get("append", False)
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            mode = "a" if append else "w"
            p.write_text(content, encoding="utf-8") if not append else p.open(mode).write(content)
            return ToolResult(output=f"Written {len(content)} chars to {path}")
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class FileListTool(BaseTool):
    name = "file_list"
    description = "List files in a directory, optionally with a glob pattern"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path"},
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (e.g. '*.py')",
                    "default": "*",
                },
                "recursive": {"type": "boolean", "default": False},
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", ".")
        pattern = kwargs.get("pattern", "*")
        recursive = kwargs.get("recursive", False)
        try:
            p = Path(path)
            if recursive:
                files = sorted(str(f) for f in p.rglob(pattern) if f.is_file())
            else:
                files = sorted(str(f) for f in p.glob(pattern) if f.is_file())
            return ToolResult(output="\n".join(files), data={"files": files})
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class FileDeleteTool(BaseTool):
    name = "file_delete"
    description = "Delete a file at the given path"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to delete"},
            },
            "required": ["path"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", "")
        try:
            os.remove(path)
            return ToolResult(output=f"Deleted {path}")
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))


class FileSearchTool(BaseTool):
    name = "file_search"
    description = "Search for a pattern in files within a directory"

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to search"},
                "pattern": {"type": "string", "description": "Text pattern to search for"},
                "glob": {
                    "type": "string",
                    "description": "File glob filter (e.g. '*.py')",
                    "default": "*",
                },
            },
            "required": ["path", "pattern"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        path = kwargs.get("path", ".")
        pattern = kwargs.get("pattern", "")
        glob = kwargs.get("glob", "*")
        try:
            matches: list[str] = []
            for fpath in Path(path).rglob(glob):
                if not fpath.is_file():
                    continue
                try:
                    text = fpath.read_text(encoding="utf-8", errors="ignore")
                    for i, line in enumerate(text.splitlines(), 1):
                        if pattern in line:
                            matches.append(f"{fpath}:{i}: {line.strip()}")
                except Exception:
                    continue
                if len(matches) >= 100:
                    break
            return ToolResult(
                output="\n".join(matches) if matches else "No matches found",
                data={"match_count": len(matches)},
            )
        except Exception as exc:
            return ToolResult(success=False, error=str(exc))
