"""Explicit HITL policy for built-in tools (selva_permissions.tool_policy).

Every side-effecting built-in tool must resolve to ASK under the default
matrix; every read-only tool must keep resolving to ALLOW (except the
handful that were already ASK before the policy table existed, which are
pinned below so that list can only change on purpose).
"""

from __future__ import annotations

import pytest

from selva_permissions.classifier import ActionClassifier
from selva_permissions.engine import PermissionEngine
from selva_permissions.matrix import DEFAULT_PERMISSION_MATRIX
from selva_permissions.tool_policy import (
    BUILTIN_TOOL_POLICY,
    GATED_SIDE_EFFECTS,
    SideEffect,
)
from selva_permissions.types import ActionCategory, PermissionLevel

_classifier = ActionClassifier()
_engine = PermissionEngine()

_GATED = sorted(n for n, p in BUILTIN_TOOL_POLICY.items() if p.side_effect in GATED_SIDE_EFFECTS)
_READ_ONLY = sorted(
    n for n, p in BUILTIN_TOOL_POLICY.items() if p.side_effect == SideEffect.READ_ONLY
)

# Read-only tools that resolve to ASK only because a fallback substring
# matched before the policy table existed ("crm", "credit" -> "edit",
# "deploy"). Kept ASK on purpose (no relaxation rides with a gating change);
# relaxing any of them is an owner decision.
_READ_ONLY_KEPT_ASK = {
    "deploy_preflight",
    "deploy_status",
    "dhanam_credit_ledger_query",
    "phyndcrm_campaign_authorization_preview",
    "phyndcrm_campaign_authorizations_pending",
    "phyndcrm_tenant_config_get",
}


def _level(tool_name: str, params: dict | None = None) -> PermissionLevel:
    return _engine.evaluate(_classifier.classify(tool_name, params)).level


@pytest.mark.parametrize("tool_name", _GATED)
def test_side_effecting_builtin_tool_requires_approval(tool_name: str) -> None:
    assert _level(tool_name) in (PermissionLevel.ASK, PermissionLevel.ASK_DUAL)


@pytest.mark.parametrize("tool_name", _READ_ONLY)
def test_read_only_builtin_tool_is_allowed(tool_name: str) -> None:
    expected = PermissionLevel.ASK if tool_name in _READ_ONLY_KEPT_ASK else PermissionLevel.ALLOW
    assert _level(tool_name) == expected


@pytest.mark.parametrize(
    "tool_name",
    [
        # The concrete examples from the 2026-10-17 finding.
        "spei_transfer_initiate",
        "cfdi_stamp",
        "bluesky_post",
        "x_post",
        "linkedin_post",
        "mastodon_post",
        "reddit_post",
        "sms_send",
        "telegram_send_message",
        "discord_send_message",
        "whatsapp_send_template",
        "send_notification",
        "webhook_send",
        "dhanam_subscription_update",
        "update_lead_status",
        "enclii_restart",
        "enclii_scale",
        "argocd_sync_app",
        "kustomize_set_image",
        "config_set_configmap_value",
        "selva_vault_delete",
        "selva_vault_rotate",
        "janua_oauth_client_create",
        "janua_oauth_client_delete",
        "janua_oauth_client_rotate_secret",
        "janua_oauth_client_update",
        "porkbun_create_dns_record",
        "porkbun_delete_dns_record",
        "porkbun_delete_url_forwarding",
        "porkbun_update_nameservers",
        "r2_bucket_delete",
        "file_delete",
        "start_background_process",
        "read_credential_file",
        "selva_vault_retrieve",
        "generate_quote",
        "factory_manifest_publish",
    ],
)
def test_finding_examples_require_approval(tool_name: str) -> None:
    assert _level(tool_name) == PermissionLevel.ASK


@pytest.mark.parametrize(
    "tool_name",
    # Tools the unattended research/credit-autopilot paths rely on.
    ["web_search", "web_fetch", "web_scrape", "web_extract", "law_search", "dof_monitor"],
)
def test_research_reads_never_prompt(tool_name: str) -> None:
    assert _level(tool_name) == PermissionLevel.ALLOW


def test_no_gated_tool_maps_to_an_allow_category() -> None:
    allow_categories = {c for c, lvl in DEFAULT_PERMISSION_MATRIX.items() if lvl == "allow"}
    offenders = [n for n in _GATED if BUILTIN_TOOL_POLICY[n].category in allow_categories]
    assert offenders == []


def test_policy_does_not_contradict_generic_map() -> None:
    # Names present in both tables must agree, so lookup order is irrelevant.
    both = set(ActionClassifier.TOOL_CATEGORY_MAP) & set(BUILTIN_TOOL_POLICY)
    conflicts = {
        n: (ActionClassifier.TOOL_CATEGORY_MAP[n], BUILTIN_TOOL_POLICY[n].category)
        for n in both
        if ActionClassifier.TOOL_CATEGORY_MAP[n] != BUILTIN_TOOL_POLICY[n].category
    }
    assert conflicts == {}


def test_external_write_defaults_to_ask() -> None:
    assert DEFAULT_PERMISSION_MATRIX[ActionCategory.EXTERNAL_WRITE] == PermissionLevel.ASK


class TestHttpParamsAware:
    @pytest.mark.parametrize("method", [None, "GET", "get", "HEAD", "OPTIONS"])
    def test_http_read_methods_are_api_call(self, method: str | None) -> None:
        params = {} if method is None else {"method": method}
        assert _classifier.classify("http_request", params) == ActionCategory.API_CALL

    @pytest.mark.parametrize("method", ["POST", "put", "PATCH", "DELETE"])
    def test_http_write_methods_require_approval(self, method: str) -> None:
        category = _classifier.classify("http_request", {"method": method})
        assert category == ActionCategory.EXTERNAL_WRITE
        assert _engine.evaluate(category).level == PermissionLevel.ASK

    def test_http_without_params_keeps_historical_api_call(self) -> None:
        assert _classifier.classify("http_request") == ActionCategory.API_CALL

    @pytest.mark.parametrize(
        "query",
        ["{ viewer { login } }", "query Q { a }", "# note\nquery { a }"],
    )
    def test_graphql_queries_are_reads(self, query: str) -> None:
        assert _classifier.classify("graphql_query", {"query": query}) == ActionCategory.API_CALL

    @pytest.mark.parametrize(
        "query",
        ["mutation { del(id: 1) }", "  # c\n\n  Mutation M { x }", "subscription { s }"],
    )
    def test_graphql_mutations_require_approval(self, query: str) -> None:
        category = _classifier.classify("graphql_query", {"query": query})
        assert category == ActionCategory.EXTERNAL_WRITE
