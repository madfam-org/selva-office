"""Tests for built-in tools."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from selva_tools.builtins.data import CsvReadTool, JsonParseTool
from selva_tools.builtins.files import FileListTool, FileReadTool, FileWriteTool


class TestFileReadTool:
    @pytest.mark.asyncio
    async def test_read_file(self) -> None:
        tool = FileReadTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello\nworld\n")
            f.flush()
            result = await tool.execute(path=f.name)
        assert result.success
        assert "hello" in result.output
        Path(f.name).unlink()

    @pytest.mark.asyncio
    async def test_read_nonexistent(self) -> None:
        tool = FileReadTool()
        result = await tool.execute(path="/nonexistent/path/file.txt")
        assert not result.success

    @pytest.mark.asyncio
    async def test_read_max_lines(self) -> None:
        tool = FileReadTool()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("\n".join(f"line{i}" for i in range(100)))
            f.flush()
            result = await tool.execute(path=f.name, max_lines=5)
        assert result.success
        assert result.output.count("\n") <= 4
        Path(f.name).unlink()


class TestFileWriteTool:
    @pytest.mark.asyncio
    async def test_write_file(self) -> None:
        tool = FileWriteTool()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = str(Path(tmpdir) / "test.txt")
            result = await tool.execute(path=path, content="hello world")
            assert result.success
            assert Path(path).read_text() == "hello world"


class TestFileListTool:
    @pytest.mark.asyncio
    async def test_list_files(self) -> None:
        tool = FileListTool()
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "a.py").write_text("x")
            (Path(tmpdir) / "b.txt").write_text("y")
            result = await tool.execute(path=tmpdir, pattern="*.py")
            assert result.success
            assert "a.py" in result.output
            assert "b.txt" not in result.output


class TestJsonParseTool:
    @pytest.mark.asyncio
    async def test_parse_json(self) -> None:
        tool = JsonParseTool()
        result = await tool.execute(json_string='{"name": "test", "value": 42}')
        assert result.success
        assert "test" in result.output

    @pytest.mark.asyncio
    async def test_parse_with_key(self) -> None:
        tool = JsonParseTool()
        result = await tool.execute(
            json_string='{"data": {"items": [{"name": "first"}]}}',
            key="data.items.0.name",
        )
        assert result.success
        assert result.output == "first"

    @pytest.mark.asyncio
    async def test_parse_invalid(self) -> None:
        tool = JsonParseTool()
        result = await tool.execute(json_string="not json")
        assert not result.success


class TestCsvReadTool:
    @pytest.mark.asyncio
    async def test_read_csv(self) -> None:
        tool = CsvReadTool()
        csv_content = "name,age\nAlice,30\nBob,25\n"
        result = await tool.execute(content=csv_content)
        assert result.success
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["name"] == "Alice"
