"""Tests for Phase 4: enhanced system prompts for coding graph."""

from __future__ import annotations

import tempfile
from pathlib import Path

from autoswarm_workers.prompts import (
    build_implement_prompt,
    build_plan_prompt,
    build_review_prompt,
)


class TestBuildPlanPrompt:
    """build_plan_prompt returns a valid prompt string with repo context."""

    def test_returns_string(self) -> None:
        result = build_plan_prompt("Add a login page")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_includes_json_format_instruction(self) -> None:
        result = build_plan_prompt("Add a login page")
        assert "JSON" in result
        assert "steps" in result

    def test_includes_repo_listing_when_path_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "main.py").write_text("print('hello')")
            (Path(tmpdir) / "README.md").write_text("# My Project\nHello world.")

            result = build_plan_prompt("Add feature", repo_path=tmpdir)
            assert "main.py" in result
            assert "My Project" in result

    def test_handles_missing_repo_path(self) -> None:
        result = build_plan_prompt("Add feature", repo_path=None)
        assert isinstance(result, str)
        assert "JSON" in result

    def test_handles_nonexistent_repo_path(self) -> None:
        result = build_plan_prompt("Add feature", repo_path="/nonexistent/path")
        assert isinstance(result, str)

    def test_includes_skill_context_when_provided(self) -> None:
        result = build_plan_prompt("Add feature", skill_ctx="You are a Python expert.")
        assert "Python expert" in result

    def test_includes_claude_md_when_present(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "CLAUDE.md").write_text("# Rules\nAlways use type hints.")

            result = build_plan_prompt("Add feature", repo_path=tmpdir)
            assert "type hints" in result

    def test_detects_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.py").write_text("pass")
            (Path(tmpdir) / "utils.py").write_text("pass")

            result = build_plan_prompt("Add feature", repo_path=tmpdir)
            assert "Python" in result


class TestBuildImplementPrompt:
    """build_implement_prompt returns strict JSON instructions."""

    def test_returns_string(self) -> None:
        result = build_implement_prompt("Add login form", 1)
        assert isinstance(result, str)

    def test_includes_json_format_instructions(self) -> None:
        result = build_implement_prompt("Add login form", 1)
        assert "JSON" in result
        assert "files" in result
        assert "path" in result
        assert "content" in result

    def test_includes_no_markdown_instruction(self) -> None:
        result = build_implement_prompt("Add login form", 1)
        assert "Do NOT return markdown" in result

    def test_handles_missing_paths(self) -> None:
        result = build_implement_prompt("Add feature", 1, repo_path=None, worktree_path=None)
        assert isinstance(result, str)

    def test_includes_skill_context(self) -> None:
        result = build_implement_prompt("Add feature", 1, skill_ctx="Expert coder.")
        assert "Expert coder" in result


class TestBuildReviewPrompt:
    """build_review_prompt returns enhanced review criteria."""

    def test_returns_string(self) -> None:
        result = build_review_prompt("Changed main.py")
        assert isinstance(result, str)

    def test_includes_review_criteria(self) -> None:
        result = build_review_prompt("Changed main.py")
        assert "Security" in result or "security" in result
        assert "Correctness" in result or "correctness" in result

    def test_includes_json_format(self) -> None:
        result = build_review_prompt("Changed main.py")
        assert "JSON" in result
        assert "approve" in result
        assert "revise" in result

    def test_includes_skill_context(self) -> None:
        result = build_review_prompt("Changes", skill_ctx="Security specialist.")
        assert "Security specialist" in result
