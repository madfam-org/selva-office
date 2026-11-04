from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _env_value(manifest: str, name: str) -> str | None:
    match = re.search(rf"- name: {name}\n\s+value: (\S+)\n", manifest)
    return match.group(1) if match else None


def test_admin_requests_the_janua_client_that_is_registered() -> None:
    admin = (ROOT / "infra/k8s/production/admin.yaml").read_text()
    client = (ROOT / "infra/janua/selva-office.oauth-client.yaml").read_text()

    live = re.search(r"^# Live production client_id: (\S+)", client, re.MULTILINE)
    assert live, "oauth-client manifest must name the live Janua client_id"
    assert _env_value(admin, "JANUA_CLIENT_ID") == live.group(1)
    assert "- https://admin.selva.town/api/auth/callback\n" in client


def test_nexus_api_keeps_selva_office_as_token_audience() -> None:
    configmap = (ROOT / "infra/k8s/production/configmap.yaml").read_text()

    assert 'JANUA_CLIENT_ID: "selva-office"' in configmap


def test_staging_admin_does_not_inherit_the_production_client() -> None:
    patch = (ROOT / "infra/k8s/overlays/staging/patch-admin.yaml").read_text()

    assert _env_value(patch, "JANUA_CLIENT_ID") == "selva-office-staging"
