"""Tests for the checkpointer factory."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langgraph.checkpoint.memory import MemorySaver


class TestCreateCheckpointer:
    """create_checkpointer returns the right saver based on config."""

    def test_returns_memory_saver_when_no_database_url(self) -> None:
        with patch(
            "selva_workers.checkpointer.get_settings",
            return_value=MagicMock(database_url=None),
        ):
            from selva_workers.checkpointer import create_checkpointer

            saver = create_checkpointer()
            assert isinstance(saver, MemorySaver)

    def test_returns_memory_saver_when_database_url_empty(self) -> None:
        with patch(
            "selva_workers.checkpointer.get_settings",
            return_value=MagicMock(database_url=""),
        ):
            from selva_workers.checkpointer import create_checkpointer

            saver = create_checkpointer()
            assert isinstance(saver, MemorySaver)

    def test_returns_postgres_saver_when_database_url_set(self) -> None:
        mock_saver = MagicMock()
        mock_saver_cls = MagicMock()
        mock_saver_cls.from_conn_string.return_value = mock_saver

        with (
            patch(
                "selva_workers.checkpointer.get_settings",
                return_value=MagicMock(database_url="postgresql+asyncpg://user:pass@localhost/db"),
            ),
            patch.dict(
                "sys.modules",
                {"langgraph.checkpoint.postgres": MagicMock(PostgresSaver=mock_saver_cls)},
            ),
        ):
            from selva_workers.checkpointer import create_checkpointer

            saver = create_checkpointer()
            assert saver is mock_saver
            mock_saver_cls.from_conn_string.assert_called_once_with(
                "postgresql://user:pass@localhost/db"
            )
            mock_saver.setup.assert_called_once()

    def test_falls_back_to_memory_on_postgres_error(self) -> None:
        with (
            patch(
                "selva_workers.checkpointer.get_settings",
                return_value=MagicMock(database_url="postgresql+asyncpg://user:pass@localhost/db"),
            ),
            patch.dict(
                "sys.modules",
                {"langgraph.checkpoint.postgres": None},
            ),
        ):
            from selva_workers.checkpointer import create_checkpointer

            saver = create_checkpointer()
            assert isinstance(saver, MemorySaver)
