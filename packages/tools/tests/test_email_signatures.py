"""Unit tests for the per-mode From + signature builder.

The builder is a pure function — kept separate from the gate tests so a
regression in signature composition surfaces cleanly.
"""

from __future__ import annotations

import pytest

from autoswarm_tools.builtins._email_signatures import build_identity


def test_user_direct_uses_user_mailbox() -> None:
    ident = build_identity(
        voice_mode="user_direct",
        user_name="Ada Lovelace",
        user_email="ada@example.com",
        selva_from="noreply@selva.town",
    )
    assert ident.from_address == "Ada Lovelace <ada@example.com>"
    assert "Ada Lovelace" in ident.html_signature
    # user_direct must NOT surface any Selva-branded disclosure.
    assert "Selva" not in ident.html_signature


def test_dyad_cobrands_with_user() -> None:
    ident = build_identity(
        voice_mode="dyad_selva_plus_user",
        user_name="Ada",
        user_email="ada@example.com",
        selva_from="hola@selva.town",
    )
    assert ident.from_address.startswith("Selva on behalf of Ada")
    assert "hola@selva.town" in ident.from_address
    assert "ada@example.com" in ident.html_signature


def test_agent_identified_uses_agent_slug() -> None:
    ident = build_identity(
        voice_mode="agent_identified",
        user_name="Ada",
        user_email="ada@example.com",
        selva_from="noreply@selva.town",
        agent_slug="nexo",
        agent_display_name="Nexo",
        org_name="MADFAM",
    )
    assert "nexo@selva.town" in ident.from_address
    assert "Nexo" in ident.from_address
    assert "MADFAM" in ident.html_signature
    assert "Selva agent" in ident.html_signature


def test_agent_identified_requires_agent_data() -> None:
    with pytest.raises(ValueError):
        build_identity(
            voice_mode="agent_identified",
            user_name="Ada",
            user_email="ada@example.com",
            selva_from="noreply@selva.town",
        )


def test_unknown_mode_raises() -> None:
    with pytest.raises(ValueError, match="Unknown voice_mode"):
        build_identity(
            voice_mode="impossible",
            user_name="Ada",
            user_email="ada@example.com",
            selva_from="noreply@selva.town",
        )


def test_missing_display_name_falls_back_to_email() -> None:
    ident = build_identity(
        voice_mode="user_direct",
        user_name="",
        user_email="ada@example.com",
        selva_from="noreply@selva.town",
    )
    assert ident.from_address == "ada@example.com <ada@example.com>"
