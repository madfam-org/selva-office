"""Explicit HITL policy for every built-in Selva tool.

Before this table existed, a built-in tool whose name matched no entry in
``ActionClassifier.TOOL_CATEGORY_MAP`` and no fallback substring fell
through to ``API_CALL`` -- which the default matrix resolves to ALLOW.
That silently let money-moving (``spei_transfer_initiate``), fiscal
(``cfdi_stamp``), social-post (``bluesky_post``), outbound-send
(``sms_send``), infra-mutating (``enclii_scale``) and secret-mutating
(``selva_vault_rotate``) tools run without a human approval at the graph
HITL layer. The substring heuristics also produced accidents in the other
direction (``dhanam_credit_ledger_query`` is FILE_WRITE because "credit"
contains "edit"; ``write_kubernetes_secret`` is FILE_WRITE because it
contains "write", so any skill that grants ``file_write`` auto-allowed it).

Each entry records two things:

* ``side_effect`` -- what the tool does to the world (documentation and
  test oracle; see ``docs/TOOL_HITL_INVENTORY.md``).
* ``category`` -- the ``ActionCategory`` the classifier returns. Every
  side-effecting class maps to a category whose default level is ASK;
  read-only tools map to ``FILE_READ`` / ``INFRASTRUCTURE_MONITOR`` /
  ``API_CALL`` (all ALLOW) so they keep running unattended.

Rules for editing:

* A new built-in tool MUST get an entry here (``tests/unit`` enforces it).
* Never map a side-effecting tool to an ALLOW category. If a tool needs a
  softer gate, use a playbook or a tool-level escalation, not this table.
* Tools that were already ASK before this table stay ASK (no relaxations
  ride along with a gating change). Read-only tools that are ASK only by a
  substring accident are listed in the inventory as relax candidates for
  the owner to rule on.
"""

from __future__ import annotations

from enum import StrEnum
from typing import NamedTuple

from .types import ActionCategory


class SideEffect(StrEnum):
    """What a tool does to the world, from least to most consequential."""

    READ_ONLY = "read-only"
    DRAFT_LOCAL = "draft-local"
    OUTBOUND_SEND = "outbound-send"
    SOCIAL_POST = "social-post"
    MONEY_MOVING = "money-moving"
    FISCAL = "fiscal"
    INFRA_MUTATING = "infra-mutating"
    SECRET_OR_IDENTITY = "secret-or-identity-mutating"
    DESTRUCTIVE = "destructive"
    EXTERNAL_WRITE = "external-write"


#: Side-effect classes that must never resolve to ALLOW by default.
GATED_SIDE_EFFECTS: frozenset[SideEffect] = frozenset(
    {
        SideEffect.OUTBOUND_SEND,
        SideEffect.SOCIAL_POST,
        SideEffect.MONEY_MOVING,
        SideEffect.FISCAL,
        SideEffect.INFRA_MUTATING,
        SideEffect.SECRET_OR_IDENTITY,
        SideEffect.DESTRUCTIVE,
        SideEffect.EXTERNAL_WRITE,
    }
)


class ToolPolicy(NamedTuple):
    side_effect: SideEffect
    category: ActionCategory


_S = SideEffect
_C = ActionCategory

# Shorthands for the common shapes.
_READ = ToolPolicy(_S.READ_ONLY, _C.API_CALL)
_READ_FILE = ToolPolicy(_S.READ_ONLY, _C.FILE_READ)
_READ_INFRA = ToolPolicy(_S.READ_ONLY, _C.INFRASTRUCTURE_MONITOR)
_DRAFT = ToolPolicy(_S.DRAFT_LOCAL, _C.API_CALL)
# Direct messages to people (email, SMS, chat, voice, calendar invites).
# EMAIL_SEND is the existing "external comms" category: ASK by default and
# DENY for the researcher role, which is the intent for every channel.
_SEND = ToolPolicy(_S.OUTBOUND_SEND, _C.EMAIL_SEND)
_SOCIAL = ToolPolicy(_S.SOCIAL_POST, _C.SOCIAL_POST)
_MONEY = ToolPolicy(_S.MONEY_MOVING, _C.BILLING_WRITE)
_FISCAL = ToolPolicy(_S.FISCAL, _C.BILLING_WRITE)
_INFRA = ToolPolicy(_S.INFRA_MUTATING, _C.INFRASTRUCTURE_EXEC)
_INFRA_DESTROY = ToolPolicy(_S.DESTRUCTIVE, _C.INFRASTRUCTURE_EXEC)
_SECRET = ToolPolicy(_S.SECRET_OR_IDENTITY, _C.SECRET_MANAGEMENT)
_EXT_WRITE = ToolPolicy(_S.EXTERNAL_WRITE, _C.EXTERNAL_WRITE)
_CRM_WRITE = ToolPolicy(_S.EXTERNAL_WRITE, _C.CRM_UPDATE)


BUILTIN_TOOL_POLICY: dict[str, ToolPolicy] = {
    # -- a2a / delegation -------------------------------------------------
    "call_external_agent": _EXT_WRITE,  # ships a task + context to a remote agent
    "delegate_task": _DRAFT,  # in-process subagent; its own tool calls are gated
    # -- accounting (Dhanam / Karafiel reads + calculators) ---------------
    "bank_reconcile": _READ,
    "declaration_prep": _READ,  # prepares data; files nothing
    "isr_calculate": _READ,
    "iva_calculate": _READ,
    "payment_summary": _READ,
    # -- Argo CD ------------------------------------------------------------
    "argocd_get_app": _READ_INFRA,
    "argocd_list_apps": _READ_INFRA,
    # A hard refresh can trigger an auto-sync on apps with automated sync.
    "argocd_refresh_app": _INFRA,
    "argocd_sync_app": ToolPolicy(_S.INFRA_MUTATING, _C.DEPLOY),
    # -- artifacts ------------------------------------------------------------
    "list_artifacts": _READ_FILE,
    "retrieve_artifact": _READ_FILE,
    "save_artifact": _DRAFT,
    # -- backups ------------------------------------------------------------
    "pgbackrest_backup": _INFRA,
    "pgbackrest_check": _READ_INFRA,
    "pgbackrest_info": _READ_INFRA,
    # -- Belvo / SPEI ---------------------------------------------------------
    "spei_account_balance": _READ,
    "spei_beneficiary_create": _MONEY,
    "spei_transaction_list": _READ,
    "spei_transfer_initiate": _MONEY,
    "spei_transfer_status": _READ,
    # -- billing --------------------------------------------------------------
    "create_checkout_link": _MONEY,
    "get_revenue_metrics": _READ,
    # -- social ---------------------------------------------------------------
    "bluesky_post": _SOCIAL,
    "linkedin_post": _SOCIAL,  # ships dark (env-armed)
    "mastodon_post": _SOCIAL,
    "reddit_post": _SOCIAL,
    "x_post": _SOCIAL,  # ships dark (env-armed)
    "linkedin_draft_create": ToolPolicy(_S.DRAFT_LOCAL, _C.FILE_WRITE),  # was ASK; kept
    "linkedin_draft_list": _READ,
    # -- calendar / meetings --------------------------------------------------
    "create_calendar_event": _SEND,  # invites attendees
    "list_calendar_events": _READ,
    "mexican_business_calendar": _READ,
    "meeting_find_slots": _READ,
    "meeting_schedule": _SEND,  # creates events + invites per participant
    # -- Cloudflare -----------------------------------------------------------
    "cloudflare_create_dns_record": _INFRA,
    "cloudflare_create_redirect_rule": _INFRA,
    "cloudflare_create_zone": _INFRA,
    "cloudflare_list_dns_records": _READ_INFRA,
    "cloudflare_list_page_rules": _READ_INFRA,
    "cloudflare_list_zones": _READ_INFRA,
    "r2_bucket_create": _INFRA,
    "r2_bucket_delete": _INFRA_DESTROY,
    "r2_bucket_list": _READ_INFRA,
    "r2_cors_set": _INFRA,
    "cf_saas_hostname_add": _INFRA,
    "cf_saas_hostname_delete": _INFRA_DESTROY,
    "cf_saas_hostname_list": _READ_INFRA,
    "cf_saas_hostname_status": _READ_INFRA,
    "cf_tunnel_create": _INFRA,
    "cf_tunnel_get_ingress": _READ_INFRA,
    "cf_tunnel_list": _READ_INFRA,
    "cf_tunnel_put_ingress": _INFRA,
    # -- code execution -------------------------------------------------------
    "bash_exec": ToolPolicy(_S.INFRA_MUTATING, _C.BASH_EXECUTE),
    "python_exec": ToolPolicy(_S.INFRA_MUTATING, _C.BASH_EXECUTE),
    "execute_code": ToolPolicy(_S.INFRA_MUTATING, _C.BASH_EXECUTE),
    "package_install": ToolPolicy(_S.INFRA_MUTATING, _C.BASH_EXECUTE),
    "start_background_process": ToolPolicy(_S.INFRA_MUTATING, _C.BASH_EXECUTE),
    "kill_background_process": ToolPolicy(_S.DESTRUCTIVE, _C.BASH_EXECUTE),
    "list_background_processes": _READ,
    # -- communication --------------------------------------------------------
    "create_report": ToolPolicy(_S.DRAFT_LOCAL, _C.FILE_WRITE),  # was ASK; kept
    "send_notification": _SEND,
    "send_email": _SEND,
    "send_marketing_email": _SEND,
    "read_email": _READ_FILE,
    "slack_message": _SEND,
    "discord_send_embed": _SEND,
    "discord_send_message": _SEND,
    "telegram_get_updates": _READ,
    "telegram_send_message": _SEND,
    "telegram_send_photo": _SEND,
    "sms_list_messages": _READ,
    "sms_send": _SEND,
    "sms_send_template": _SEND,
    "sms_status": _READ,
    "voice_call_make": _SEND,
    "voice_call_say": _SEND,
    "voice_call_status": _READ,
    "whatsapp_send_template": _SEND,
    "webhook_send": _EXT_WRITE,
    # -- CRM --------------------------------------------------------------------
    "create_crm_activity": _CRM_WRITE,
    "create_lead": _CRM_WRITE,
    "update_lead_status": _CRM_WRITE,
    "phyndcrm_campaign_authorization_decide": _CRM_WRITE,
    "phyndcrm_campaign_authorization_request": _CRM_WRITE,
    # Read-only, ASK today only because "crm" is a fallback substring; kept.
    "phyndcrm_campaign_authorization_preview": ToolPolicy(_S.READ_ONLY, _C.CRM_UPDATE),
    "phyndcrm_campaign_authorizations_pending": ToolPolicy(_S.READ_ONLY, _C.CRM_UPDATE),
    "phyndcrm_tenant_config_get": ToolPolicy(_S.READ_ONLY, _C.CRM_UPDATE),
    "phyndcrm_pipeline_bootstrap": _CRM_WRITE,
    "phyndcrm_tenant_create": _CRM_WRITE,
    # -- data / documents -----------------------------------------------------
    "csv_read": _READ_FILE,
    "data_transform": _READ,  # safe_eval sandboxed expression over given data
    "json_parse": _READ,
    "generate_chart": _DRAFT,
    "generate_pdf": _DRAFT,
    "markdown_to_html": _DRAFT,
    "parse_pdf": _READ_FILE,
    "contpaqi_export": _DRAFT,
    "erp_export": _DRAFT,
    "generate_image": _DRAFT,
    "text_to_speech": _DRAFT,
    "speech_to_text": _READ,
    "image_analysis": _READ,
    # -- databases ------------------------------------------------------------
    "database_schema": _READ,
    "sql_query": _READ,  # SELECT-only enforced in the tool
    "sql_write": ToolPolicy(_S.DESTRUCTIVE, _C.DATABASE_MIGRATION),
    "db_dump_to_r2": _INFRA,  # copies a database (PII) to object storage
    "db_mask_and_copy": ToolPolicy(_S.INFRA_MUTATING, _C.DATABASE_MIGRATION),
    "db_restore_from_r2": ToolPolicy(_S.DESTRUCTIVE, _C.DATABASE_MIGRATION),
    "db_size_report": _READ_INFRA,
    # -- deploy -----------------------------------------------------------------
    # deploy_status / deploy_preflight are reads, ASK today via DEPLOY; kept.
    "deploy_status": ToolPolicy(_S.READ_ONLY, _C.DEPLOY),
    "deploy_preflight": ToolPolicy(_S.READ_ONLY, _C.DEPLOY),
    "deploy_trigger": ToolPolicy(_S.INFRA_MUTATING, _C.DEPLOY),
    "rollback_evidence_record": _DRAFT,
    "endpoint_smoke_check": _READ,
    # -- dev quality ------------------------------------------------------------
    "lint_and_typecheck": _READ,
    "test_coverage_for_diff": _READ,
    # -- Dhanam -----------------------------------------------------------------
    # Read-only; ASK today only because "credit" contains "edit"; kept.
    "dhanam_credit_ledger_query": ToolPolicy(_S.READ_ONLY, _C.FILE_WRITE),
    "dhanam_space_create": _MONEY,
    "dhanam_subscription_create": _MONEY,
    "dhanam_subscription_update": _MONEY,
    # -- DNS (Porkbun) --------------------------------------------------------
    "porkbun_create_dns_record": _INFRA,
    "porkbun_delete_dns_record": _INFRA_DESTROY,
    "porkbun_delete_url_forwarding": _INFRA_DESTROY,
    "porkbun_domain_health_check": _READ_INFRA,
    "porkbun_get_nameservers": _READ_INFRA,
    "porkbun_list_dns_records": _READ_INFRA,
    "porkbun_list_domains": _READ_INFRA,
    "porkbun_list_url_forwarding": _READ_INFRA,
    "porkbun_ping": _READ_INFRA,
    "porkbun_update_nameservers": _INFRA,
    # -- Enclii -----------------------------------------------------------------
    "enclii_exec": ToolPolicy(_S.INFRA_MUTATING, _C.BASH_EXECUTE),
    "enclii_health": _READ_INFRA,
    "enclii_logs": _READ_INFRA,
    "enclii_restart": _INFRA,
    "enclii_scale": _INFRA,
    "enclii_secrets": _SECRET,
    # -- environment ------------------------------------------------------------
    "env_info": _READ,
    # -- factory lines (identical to the rules in classifier.TOOL_CATEGORY_MAP)
    "factory_manifest_get_for_repo": _READ,
    "factory_manifest_publish": ToolPolicy(_S.EXTERNAL_WRITE, _C.FILE_WRITE),
    "factory_manifest_verify": _READ,
    # -- files ------------------------------------------------------------------
    "file_delete": ToolPolicy(_S.DESTRUCTIVE, _C.FILE_WRITE),
    "file_list": _READ_FILE,
    "file_read": _READ_FILE,
    "file_search": _READ_FILE,
    "file_write": ToolPolicy(_S.DRAFT_LOCAL, _C.FILE_WRITE),
    # -- git ----------------------------------------------------------------
    "git_branch": _DRAFT,  # local branch create/list/switch in the task worktree
    "git_commit": ToolPolicy(_S.DRAFT_LOCAL, _C.GIT_COMMIT),
    "git_create_pr": ToolPolicy(_S.EXTERNAL_WRITE, _C.GIT_PUSH),
    "git_diff": _READ_FILE,
    "git_push": ToolPolicy(_S.EXTERNAL_WRITE, _C.GIT_PUSH),
    # -- GitHub admin -----------------------------------------------------------
    "github_admin_audit_team_membership": _READ,
    "github_admin_create_team": ToolPolicy(_S.SECRET_OR_IDENTITY, _C.GITHUB_ADMIN),
    "github_admin_set_branch_protection": ToolPolicy(_S.SECRET_OR_IDENTITY, _C.GITHUB_ADMIN),
    "github_admin_set_team_membership": ToolPolicy(_S.SECRET_OR_IDENTITY, _C.GITHUB_ADMIN),
    # -- observability ----------------------------------------------------------
    "grafana_dashboard_list": _READ_INFRA,
    "grafana_panel_export": _READ_INFRA,
    "loki_labels": _READ_INFRA,
    "loki_query_range": _READ_INFRA,
    "prom_alerts_active": _READ_INFRA,
    "prom_query": _READ_INFRA,
    "prom_query_range": _READ_INFRA,
    "prom_silence_create": _INFRA,  # silences alerts
    "sentry_breadcrumbs_get": _READ_FILE,
    "sentry_event_list_for_issue": _READ_INFRA,
    "sentry_issue_get": _READ_INFRA,
    "sentry_issue_list": _READ_INFRA,
    "sentry_issue_update": _EXT_WRITE,
    # -- HITL / meta-harness introspection --------------------------------------
    "hitl_get_effective_tier": _READ,
    "hitl_get_my_bucket_state": _READ,
    "hitl_recent_decisions": _READ,
    "hitl_why_asked": _READ,
    "meta_harness_budget_gate": _READ,
    "meta_harness_convergence_check": _READ,
    "meta_harness_escalate_tier": _DRAFT,  # can only make gating stricter
    "meta_harness_role_summary": _READ,
    "meta_harness_route": _READ,
    "meta_harness_submit_round": _DRAFT,
    # -- HTTP (params-aware in the classifier: GET/HEAD/OPTIONS and GraphQL
    #    queries are reads; any other method or a mutation is EXTERNAL_WRITE)
    "graphql_query": _READ,
    "http_request": _READ,
    # -- intelligence (public data reads) ---------------------------------------
    "dof_monitor": _READ,
    "exchange_rate": _READ,
    "inflation_rate": _READ,
    "sat_monitor": _READ,
    "siem_compliance": _READ,
    "tiie_rate": _READ,
    "uma_tracker": _READ,
    # -- Janua ------------------------------------------------------------------
    "janua_oauth_client_create": _SECRET,
    "janua_oauth_client_delete": ToolPolicy(_S.DESTRUCTIVE, _C.SECRET_MANAGEMENT),
    "janua_oauth_client_rotate_secret": _SECRET,
    "janua_oauth_client_update": _SECRET,
    "janua_org_create": _SECRET,
    # -- Kubernetes -------------------------------------------------------------
    "config_delete_configmap_key": ToolPolicy(_S.INFRA_MUTATING, _C.K8S_CONFIGMAP_WRITE),
    "config_list_configmaps": _READ_INFRA,
    "config_read_configmap": _READ_FILE,
    "config_set_configmap_value": ToolPolicy(_S.INFRA_MUTATING, _C.K8S_CONFIGMAP_WRITE),
    "k8s_describe_pod": _READ_INFRA,
    "k8s_get_events": _READ_INFRA,
    "k8s_get_pods": _READ_INFRA,
    "k8s_get_replicasets": _READ_INFRA,
    "k8s_rollout_status": _READ_INFRA,
    "write_kubernetes_secret": ToolPolicy(_S.SECRET_OR_IDENTITY, _C.K8S_SECRET_WRITE),
    "kustomize_build": _READ_INFRA,
    "kustomize_list_images": _READ_INFRA,
    "kustomize_set_image": _INFRA,  # rewrites deploy manifests (image digests)
    # -- Karafiel (fiscal) ------------------------------------------------------
    "blacklist_check": _READ,
    "cfdi_generate": _FISCAL,  # creates a CFDI document in Karafiel
    "cfdi_stamp": _FISCAL,  # PAC stamp: legally binding, not undoable
    "cfdi_status": _READ,
    "complemento_pago": _FISCAL,
    "constancia_fiscal": _READ,
    "nom035_report": _DRAFT,
    "nom035_survey": _DRAFT,
    "rfc_validation": _READ,
    "karafiel_invoice_series_create": _FISCAL,
    "karafiel_org_create": _FISCAL,
    "karafiel_pac_register": _FISCAL,
    "karafiel_sat_cert_upload": _SECRET,  # CSD signing key + password
    # -- legal / privacy --------------------------------------------------------
    "compliance_check": _READ,
    "contract_generate": _DRAFT,
    "law_search": _READ,
    "repse_check": _READ,
    "data_deletion_search": _READ,
    "pii_classify": _READ,
    "privacy_notice_generate": _DRAFT,
    # -- npm registry -----------------------------------------------------------
    "selva_npm_check_expiry": _READ,
    "selva_npm_create_token": _SECRET,
    "selva_npm_rotate_token": _SECRET,
    "selva_npm_update_github_secrets": _SECRET,
    # -- operations / phygital --------------------------------------------------
    "carrier_tracking": _READ,
    "inventory_check": _READ,
    "pedimento_lookup": _READ,
    "generate_parametric_model": _DRAFT,
    "generate_quote": ToolPolicy(_S.EXTERNAL_WRITE, _C.PRICING_PROPOSAL),
    "get_production_order_status": _READ,
    "run_dfm_analysis": _READ,
    # -- pricing / catalog ------------------------------------------------------
    "catalog_load": _READ,
    "catalog_promo_stack_check": _READ,
    "catalog_tier_gap_audit": _READ,
    "competitor_price_lookup": _READ,
    "product_catalog": _READ,
    # -- Resend domains ---------------------------------------------------------
    "resend_domain_add": _INFRA,
    "resend_domain_delete": _INFRA_DESTROY,
    "resend_domain_list": _READ_INFRA,
    "resend_domain_verify": _READ_INFRA,  # asks Resend to re-poll DNS
    # -- Selva office seats / tenant identity -----------------------------------
    "selva_office_seat_assign_department": _SECRET,
    "selva_office_seat_create": _SECRET,
    "selva_office_seat_revoke": ToolPolicy(_S.DESTRUCTIVE, _C.SECRET_MANAGEMENT),
    "tenant_create_identity_record": _SECRET,
    "tenant_resolve": _READ,
    "tenant_validate_consistency": _READ,
    # -- skills / tool catalog --------------------------------------------------
    "skill_get_metrics": _READ,
    "skill_record_outcome": _DRAFT,
    "describe_tool": _READ,
    "list_my_tools": _READ,
    "search_tools_by_capability": _READ,
    # -- Stripe Connect ---------------------------------------------------------
    "stripe_connect_account_create": _MONEY,
    "stripe_connect_account_link": _MONEY,  # mints an onboarding URL for the account
    "stripe_connect_account_status": _READ,
    # -- vault / credentials ----------------------------------------------------
    "read_credential_file": _SECRET,  # returns credential contents to the model
    "selva_vault_delete": ToolPolicy(_S.DESTRUCTIVE, _C.SECRET_MANAGEMENT),
    "selva_vault_list": _READ,  # key names only, never values
    "selva_vault_retrieve": _SECRET,  # returns the secret value to the model
    "selva_vault_rotate": _SECRET,
    "selva_vault_store": _SECRET,
    # -- web --------------------------------------------------------------------
    "web_extract": _READ,
    "web_fetch": _READ,
    "web_scrape": _READ,
    "web_search": _READ,
    # -- webhooks ---------------------------------------------------------------
    "webhooks_janua_register_oidc_redirect": ToolPolicy(
        _S.SECRET_OR_IDENTITY, _C.WEBHOOK_MANAGEMENT
    ),
    "webhooks_resend_create": ToolPolicy(_S.EXTERNAL_WRITE, _C.WEBHOOK_MANAGEMENT),
    "webhooks_stripe_create": ToolPolicy(_S.EXTERNAL_WRITE, _C.WEBHOOK_MANAGEMENT),
    "webhooks_stripe_delete": ToolPolicy(_S.DESTRUCTIVE, _C.WEBHOOK_MANAGEMENT),
    "webhooks_stripe_list": _READ,
    # -- inference budget ---------------------------------------------------
    "inference_budget_status": _READ,  # provider-grant status (platform-only)
    # -- worker-local tools (apps/workers/selva_workers/graphs/base.py) ---------
    "create_worktree": ToolPolicy(_S.DRAFT_LOCAL, _C.FILE_WRITE),
    "cleanup_worktree": ToolPolicy(_S.DESTRUCTIVE, _C.FILE_WRITE),
}


#: Tool name -> category, as consumed by ``ActionClassifier``.
BUILTIN_TOOL_CATEGORY_MAP: dict[str, ActionCategory] = {
    name: policy.category for name, policy in BUILTIN_TOOL_POLICY.items()
}

#: Worker-local tool names (apps/workers graphs/base.py), not registered by
#: ``selva_tools.builtins.get_builtin_tools()``.
NON_REGISTRY_TOOL_NAMES: frozenset[str] = frozenset({"create_worktree", "cleanup_worktree"})
