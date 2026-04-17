"""Tests for the SPF/DKIM/DMARC alignment preflight + cache."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from autoswarm_tools.builtins import _spf_check


def _make_answer(text: str) -> MagicMock:
    mock = MagicMock()
    mock.strings = [text.encode("utf-8")]
    return mock


def test_alignment_passes_when_all_records_present() -> None:
    _spf_check._CACHE.clear()

    def _resolve(name: str, rtype: str, lifetime: float = 5.0):  # type: ignore[no-untyped-def]
        if name == "selva.town":
            return [_make_answer("v=spf1 include:resend.com -all")]
        if name == "resend._domainkey.selva.town":
            return [_make_answer("v=DKIM1; k=rsa; p=abc")]
        if name == "_dmarc.selva.town":
            return [_make_answer("v=DMARC1; p=reject")]
        raise Exception("no record")

    mock_module = MagicMock()
    mock_module.resolver.resolve = _resolve

    with patch.dict("sys.modules", {"dns.resolver": mock_module.resolver, "dns": mock_module}):
        result = _spf_check.check_alignment("selva.town")
    assert result.aligned
    assert result.status == "pass"


def test_alignment_fails_on_missing_dmarc() -> None:
    _spf_check._CACHE.clear()

    def _resolve(name: str, rtype: str, lifetime: float = 5.0):  # type: ignore[no-untyped-def]
        if name == "selva.town":
            return [_make_answer("v=spf1 include:resend.com -all")]
        if name == "resend._domainkey.selva.town":
            return [_make_answer("v=DKIM1; p=abc")]
        raise Exception("no record")

    mock_module = MagicMock()
    mock_module.resolver.resolve = _resolve

    with patch.dict("sys.modules", {"dns.resolver": mock_module.resolver, "dns": mock_module}):
        result = _spf_check.check_alignment("selva.town")
    assert not result.aligned
    assert result.status == "fail"
    assert "DMARC" in result.reason


def test_cache_returns_same_object_within_ttl() -> None:
    _spf_check._CACHE.clear()
    sentinel = _spf_check.SpfResult(
        domain="cached.example",
        spf_ok=True,
        dkim_ok=True,
        dmarc_ok=True,
        status="pass",
        reason="cached",
    )
    _spf_check._CACHE["cached.example"] = (time.time() + 600, sentinel)
    result = _spf_check.check_alignment("cached.example")
    assert result is sentinel
