"""Signature + from-address builders for the three outbound voice modes.

The selected voice mode determines two things about every outbound email:

1. The `From:` header (display name + address).
2. The footer signature appended to the HTML body.

The builders here are pure — the voice-mode gate in ``email_tools.py``
resolves which builder to call. When ``voice_mode`` is ``None`` (tenant
has not finished onboarding) no builder runs and the send is rejected
upstream.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OutboundIdentity:
    """Resolved ``From:`` + signature for a single outbound send."""

    from_address: str
    html_signature: str


def _user_direct(
    *,
    user_name: str,
    user_email: str,
) -> OutboundIdentity:
    """Send from the user, no AI disclosure, no agent branding."""
    display = user_name.strip() or user_email
    return OutboundIdentity(
        from_address=f"{display} <{user_email}>",
        html_signature=(
            f"<p style=\"margin-top:24px;font-size:12px;color:#555\">"
            f"Best,<br>{display}</p>"
        ),
    )


def _dyad_selva_plus_user(
    *,
    user_name: str,
    user_email: str,
    selva_from: str,
) -> OutboundIdentity:
    """Co-branded — display name says "Selva on behalf of <user>"."""
    display = user_name.strip() or user_email
    return OutboundIdentity(
        from_address=f"Selva on behalf of {display} <{selva_from}>",
        html_signature=(
            f"<p style=\"margin-top:24px;font-size:12px;color:#555\">"
            f"Sent by Selva on behalf of {display}.<br>"
            f"Reply-to: {user_email}</p>"
        ),
    )


def _agent_identified(
    *,
    agent_slug: str,
    agent_display_name: str,
    org_name: str,
) -> OutboundIdentity:
    """Sent from the agent's own selva.town address, fully disclosed."""
    return OutboundIdentity(
        from_address=f"{agent_display_name} <{agent_slug}@selva.town>",
        html_signature=(
            f"<p style=\"margin-top:24px;font-size:12px;color:#555\">"
            f"— {agent_display_name}, a Selva agent acting for {org_name}.<br>"
            f"<a href=\"https://selva.town/agents/{agent_slug}\">"
            f"What is a Selva agent?</a></p>"
        ),
    )


def build_identity(
    *,
    voice_mode: str,
    user_name: str,
    user_email: str,
    selva_from: str,
    agent_slug: str | None = None,
    agent_display_name: str | None = None,
    org_name: str = "",
) -> OutboundIdentity:
    """Resolve the identity block for a given mode.

    Raises ``ValueError`` for an unknown mode or missing agent data in
    ``agent_identified`` — both are programming errors that should
    surface rather than silently degrade to a safer mode.
    """
    if voice_mode == "user_direct":
        return _user_direct(user_name=user_name, user_email=user_email)
    if voice_mode == "dyad_selva_plus_user":
        return _dyad_selva_plus_user(
            user_name=user_name,
            user_email=user_email,
            selva_from=selva_from,
        )
    if voice_mode == "agent_identified":
        if not agent_slug or not agent_display_name:
            raise ValueError(
                "agent_identified mode requires agent_slug and agent_display_name"
            )
        return _agent_identified(
            agent_slug=agent_slug,
            agent_display_name=agent_display_name,
            org_name=org_name,
        )
    raise ValueError(f"Unknown voice_mode: {voice_mode}")
