"""The workers startup path must never log the Redis password.

Regression for the startup event ``Connected to Redis at redis://:<pw>@...``
that exposed the shared platform Redis credential to anyone with log access.
"""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Imported at collection time on purpose: importing the module runs
# configure_logging(), which replaces the root handlers (and with them
# caplog's) -- doing it inside a test would hide that test's records.
import selva_workers.__main__ as mod
from selva_workers.config import Settings

# Obviously fake test value -- never a real credential.
PW = "Fake-Pa55word-xyz"
URL = f"redis://:{PW}@redis.data.svc.cluster.local:6379/8"


class _StopAfterConnectLogError(Exception):
    """Raised by the first post-connect step to end main() in the test."""


def _settings() -> Settings:
    return Settings(_env_file=None, redis_url=URL)


def _stub_signal_handler(loop: asyncio.AbstractEventLoop):
    original = loop.add_signal_handler
    loop.add_signal_handler = lambda *a, **kw: None  # type: ignore[method-assign]

    def _restore() -> None:
        loop.add_signal_handler = original  # type: ignore[method-assign]

    return _restore


def _all_log_text(caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]) -> str:
    """Record messages AND whatever the configured JSON handler rendered."""
    captured = capsys.readouterr()
    records = "\n".join(r.getMessage() for r in caplog.records)
    return "\n".join([records, captured.out, captured.err])


@pytest.mark.asyncio
async def test_connected_log_line_masks_password(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    pool = MagicMock()
    pool.ping = AsyncMock(return_value=True)
    restore = _stub_signal_handler(asyncio.get_event_loop())
    try:
        with (
            caplog.at_level(logging.INFO),
            patch("selva_workers.__main__.get_settings", return_value=_settings()),
            patch("selva_workers.__main__.get_redis_pool", return_value=pool),
            patch(
                "selva_workers.__main__._cleanup_stale_worktrees",
                new_callable=AsyncMock,
                side_effect=_StopAfterConnectLogError,
            ),
        ):
            with pytest.raises(_StopAfterConnectLogError):
                await mod.main()
    finally:
        restore()

    text = _all_log_text(caplog, capsys)
    assert PW not in text
    assert "Connected to Redis at redis://:***@redis.data.svc.cluster.local:6379/8" in text


@pytest.mark.asyncio
async def test_connect_failure_log_line_masks_password(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    pool = MagicMock()
    pool.ping = AsyncMock(return_value=False)
    restore = _stub_signal_handler(asyncio.get_event_loop())
    try:
        with (
            caplog.at_level(logging.INFO),
            patch("selva_workers.__main__.get_settings", return_value=_settings()),
            patch("selva_workers.__main__.get_redis_pool", return_value=pool),
        ):
            with pytest.raises(SystemExit):
                await mod.main()
    finally:
        restore()

    text = _all_log_text(caplog, capsys)
    assert PW not in text
    assert "Cannot connect to Redis at redis://:***@" in text


def test_invalid_redis_url_error_does_not_echo_password() -> None:
    """The validator used to echo url[:20] (a partial password) and pydantic
    appended ``input_value={...}`` with every raw env value."""
    bad = f"http://:{PW}@redis.data.svc.cluster.local:6379/8"
    with pytest.raises(ValueError) as exc:
        Settings(_env_file=None, redis_url=bad)
    message = str(exc.value)
    assert "REDIS_URL must start with" in message
    assert "got: http://:***@redis.data.svc.cluster.local:6379/8" in message
    assert PW not in message
    assert PW[:4] not in message
