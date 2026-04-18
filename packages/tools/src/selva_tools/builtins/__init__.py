"""Built-in tools for AutoSwarm agents."""

from __future__ import annotations

from ..base import BaseTool

# Wave 4 additions
from ..execute_code import ExecuteCodeTool
from ..extra_tools import DelegateTaskTool, ReadCredentialFileTool, WebExtractTool
from ..extra_tools import WebSearchTool as WebSearchToolV2
from ..media_tools import GenerateImageTool, TextToSpeechTool
from ..process_registry import (
    KillBackgroundProcessTool,
    ListBackgroundProcessesTool,
    StartBackgroundProcessTool,
)
from .a2a_tool import CallExternalAgentTool
from .accounting import (
    BankReconciliationTool,
    DeclarationPrepTool,
    ISRCalculatorTool,
    IVACalculatorTool,
    PaymentSummaryTool,
)
from .artifact import ListArtifactsTool, RetrieveArtifactTool, SaveArtifactTool
from .billing_tools import CreateCheckoutLinkTool, GetRevenueMetricsTool
from .calendar_tools import (
    CreateCalendarEventTool,
    ListCalendarEventsTool,
    MexicanBusinessCalendarTool,
)
from .code import BashExecTool, PythonExecTool
from .communication import CreateReportTool, SendNotificationTool
from .crm_tools import CreateActivityTool, CreateLeadTool, UpdateLeadStatusTool
from .data import CsvReadTool, DataTransformTool, JsonParseTool
from .database_tools import DatabaseSchemaTool, SQLQueryTool, SQLWriteTool
from .deploy import DeployStatusTool, DeployTool
from .argocd import get_argocd_tools
from .backup_ops import get_backup_tools
from .cloudflare import get_cloudflare_tools
from .cloudflare_r2 import get_r2_tools
from .cloudflare_saas import get_cloudflare_saas_tools
from .belvo_spei import get_belvo_spei_tools
from .cloudflare_tunnel import get_cloudflare_tunnel_tools
from .discord import get_discord_tools
from .dns import get_dns_tools
from .k8s_diagnostics import get_k8s_diagnostic_tools
from .kustomize import get_kustomize_tools
from .meeting_scheduler import get_meeting_scheduler_tools
from .telegram import get_telegram_tools
from .twilio_sms import get_twilio_sms_tools
from .voice_call import get_voice_call_tools
from .document_tools import GenerateChartTool, GeneratePDFTool, MarkdownToHTMLTool, ParsePDFTool
from .email_tools import ReadEmailTool, SendEmailTool
from .enclii_infra import (
    EncliiExecTool,
    EncliiHealthTool,
    EncliiLogsTool,
    EncliiRestartTool,
    EncliiScaleTool,
    EncliiSecretsTool,
)
from .environment import EnvInfoTool, PackageInstallTool
from .erp import CONTPAQiExportTool, GenericERPExportTool
from .files import FileDeleteTool, FileListTool, FileReadTool, FileSearchTool, FileWriteTool
from .git import GitBranchTool, GitCommitTool, GitDiffTool, GitPushTool
from .github_admin import (
    GithubAdminAuditTeamMembershipTool,
    GithubAdminCreateTeamTool,
    GithubAdminSetBranchProtectionTool,
    GithubAdminSetTeamMembershipTool,
)
from .http_tools import GraphQLQueryTool, HTTPRequestTool, WebhookSendTool
from .image_analysis import ImageAnalysisTool
from .k8s_configmap import (
    DeleteConfigMapKeyTool,
    ListConfigMapsTool,
    ReadConfigMapTool,
    SetConfigMapValueTool,
)
from .k8s_secret import KubernetesSecretWriteTool
from .intelligence import (
    DOFMonitorTool,
    ExchangeRateTool,
    InflationTool,
    SATMonitorTool,
    SIEMComplianceTool,
    TIIETool,
    UMATrackerTool,
)
from .k8s_secret import KubernetesSecretWriteTool
from .karafiel import (
    BlacklistCheckTool,
    CFDIGenerateTool,
    CFDIStampTool,
    CFDIStatusTool,
    ComplementoPagoTool,
    ConstanciaFiscalTool,
    NOM035ReportTool,
    NOM035SurveyTool,
    RFCValidationTool,
)
from .legal import (
    ComplianceCheckTool,
    ContractGenerateTool,
    LawSearchTool,
    REPSECheckTool,
)
from .marketing_tools import SendMarketingEmailTool
from .npm_registry import get_npm_registry_tools
from .operations import CarrierTrackingTool, InventoryCheckTool, PedimentoLookupTool
from .phygital_tools import (
    CreateWorkOrderTool,
    GenerateParametricModelTool,
    GenerateQuoteTool,
    RunDFMAnalysisTool,
)
from .pricing_intel import (
    CatalogLoadTool,
    CatalogPromoStackTool,
    CatalogTierGapTool,
    CompetitorPriceLookupTool,
)
from .privacy import DataDeletionTool, PIIClassificationTool, PrivacyNoticeGeneratorTool
from .product_catalog import ProductCatalogTool
from .slack import SlackMessageTool
from .stt import SpeechToTextTool
from .vault import get_vault_tools
from .web import WebFetchTool, WebScrapeTool, WebSearchTool
from .webhooks import (
    JanuaOidcRedirectRegisterTool,
    ResendWebhookCreateTool,
    StripeWebhookCreateTool,
    StripeWebhookDeleteTool,
    StripeWebhookListTool,
)
from .whatsapp import WhatsAppTemplateTool


def get_builtin_tools() -> list[BaseTool]:
    """Return all built-in tool instances."""
    return [
        # File ops
        FileReadTool(),
        FileWriteTool(),
        FileListTool(),
        FileDeleteTool(),
        FileSearchTool(),
        # Code (original)
        PythonExecTool(),
        BashExecTool(),
        # Wave 4: execute_code sandbox (approval-gated)
        ExecuteCodeTool(),
        # Wave 4: process registry
        StartBackgroundProcessTool(),
        ListBackgroundProcessesTool(),
        KillBackgroundProcessTool(),
        # Git
        GitCommitTool(),
        GitPushTool(),
        GitDiffTool(),
        GitBranchTool(),
        # Web (original)
        WebSearchTool(),
        WebFetchTool(),
        WebScrapeTool(),
        # Wave 4: enhanced web tools
        WebSearchToolV2(),
        WebExtractTool(),
        # HTTP / GraphQL / Webhooks
        HTTPRequestTool(),
        GraphQLQueryTool(),
        WebhookSendTool(),
        # Data
        JsonParseTool(),
        CsvReadTool(),
        DataTransformTool(),
        # Communication
        SendNotificationTool(),
        CreateReportTool(),
        SlackMessageTool(),
        # Email
        SendEmailTool(),
        ReadEmailTool(),
        # Calendar
        CreateCalendarEventTool(),
        ListCalendarEventsTool(),
        MexicanBusinessCalendarTool(),
        # Database
        SQLQueryTool(),
        SQLWriteTool(),
        DatabaseSchemaTool(),
        # Documents
        GeneratePDFTool(),
        ParsePDFTool(),
        MarkdownToHTMLTool(),
        GenerateChartTool(),
        # Environment
        EnvInfoTool(),
        PackageInstallTool(),
        # Deployment
        DeployTool(),
        DeployStatusTool(),
        # Artifacts
        SaveArtifactTool(),
        RetrieveArtifactTool(),
        ListArtifactsTool(),
        # Image analysis (original) + Generation (Wave 4)
        ImageAnalysisTool(),
        GenerateImageTool(),
        TextToSpeechTool(),
        # Voice: speech-to-text
        SpeechToTextTool(),
        # Wave 4: delegation + credentials
        DelegateTaskTool(),
        ReadCredentialFileTool(),
        # A2A protocol
        CallExternalAgentTool(),
        # Karafiel compliance
        RFCValidationTool(),
        CFDIGenerateTool(),
        CFDIStampTool(),
        CFDIStatusTool(),
        BlacklistCheckTool(),
        ConstanciaFiscalTool(),
        ComplementoPagoTool(),
        NOM035SurveyTool(),
        NOM035ReportTool(),
        # LFPDPPP privacy
        PIIClassificationTool(),
        PrivacyNoticeGeneratorTool(),
        DataDeletionTool(),
        # WhatsApp Business API
        WhatsAppTemplateTool(),
        # Legal tools (Karafiel CLM + Tezca)
        ContractGenerateTool(),
        REPSECheckTool(),
        LawSearchTool(),
        ComplianceCheckTool(),
        # Accounting / Contabilidad
        ISRCalculatorTool(),
        IVACalculatorTool(),
        BankReconciliationTool(),
        DeclarationPrepTool(),
        PaymentSummaryTool(),
        # Market intelligence
        DOFMonitorTool(),
        ExchangeRateTool(),
        UMATrackerTool(),
        TIIETool(),
        InflationTool(),
        SATMonitorTool(),
        SIEMComplianceTool(),
        # Operations
        PedimentoLookupTool(),
        CarrierTrackingTool(),
        InventoryCheckTool(),
        # ERP export
        CONTPAQiExportTool(),
        GenericERPExportTool(),
        # Product catalog (MADFAM ecosystem)
        ProductCatalogTool(),
        # Pricing intelligence (per RFC 0004 — Selva-local catalog audits;
        # deep competitor + WTP analysis delegated to Tulana once v0.2 ships)
        CatalogLoadTool(),
        CatalogTierGapTool(),
        CatalogPromoStackTool(),
        CompetitorPriceLookupTool(),
        # Revenue tools (Ledger Node)
        CreateCheckoutLinkTool(),
        GetRevenueMetricsTool(),
        # CRM tools (Growth Node)
        CreateLeadTool(),
        UpdateLeadStatusTool(),
        CreateActivityTool(),
        # Marketing tools (Growth Node)
        SendMarketingEmailTool(),
        # Phygital tools (Yantra4D Engine Node)
        GenerateParametricModelTool(),
        RunDFMAnalysisTool(),
        GenerateQuoteTool(),
        CreateWorkOrderTool(),
        # Infrastructure tools (Orchestration Node — SecOps gated)
        EncliiExecTool(),
        EncliiRestartTool(),
        EncliiScaleTool(),
        EncliiLogsTool(),
        EncliiHealthTool(),
        EncliiSecretsTool(),
        # DNS management tools (Porkbun — Orchestration Node)
        *get_dns_tools(),
        # Cloudflare zone + DNS + Page Rules management
        *get_cloudflare_tools(),
        # Cloudflare Zero Trust Tunnel (route public hostnames to cluster)
        *get_cloudflare_tunnel_tools(),
        # Cloudflare R2 object storage (bucket CRUD + CORS)
        *get_r2_tools(),
        # Cloudflare for SaaS custom-hostname onboarding (tenant bring-your-own-domain)
        *get_cloudflare_saas_tools(),
        # ArgoCD application management (sync, refresh, read status)
        *get_argocd_tools(),
        # Kubernetes read-side diagnostics (pods, events, replicasets, rollouts)
        *get_k8s_diagnostic_tools(),
        # Kustomize manifest editing (digest pinning for GitOps)
        *get_kustomize_tools(),
        # pgBackRest operations (info, backup, check)
        *get_backup_tools(),
        # Phase 6 — Communications: Twilio SMS (send, template, status,
        # opt-out). Mexican CDI compliance — explicit consent required.
        *get_twilio_sms_tools(),
        # Phase 6 — Communications: outbound voice calls (Twilio Voice,
        # Vapi AI agent, and a hybrid call-and-transfer path). HITL-gated
        # per the voice_mode consent ledger.
        *get_voice_call_tools(),
        # Phase 6 — Communications: Telegram bot (send message, photo,
        # update webhook) for operator + ops-channel notifications.
        *get_telegram_tools(),
        # Phase 6 — Communications: Discord bot (channel message, DM,
        # webhook) for community + dev-channel notifications.
        *get_discord_tools(),
        # Phase 6 — Adjacent: meeting scheduler (Google Calendar +
        # Microsoft 365) with availability query + invite generation.
        *get_meeting_scheduler_tools(),
        # Phase 6 — Adjacent: Belvo SPEI bank transfers (Mexican SPEI
        # rails). HITL-gated for transfer creation; read-only for status.
        *get_belvo_spei_tools(),
        # NPM registry management (Verdaccio — token rotation + GitHub secrets)
        *get_npm_registry_tools(),
        # Vault — secure secret storage (Orchestration Node — HITL gated)
        *get_vault_tools(),
        # RFC 0005 Sprint 1a — Kubernetes Secret writer (HITL gated per env)
        KubernetesSecretWriteTool(),
        # RFC 0006 Sprint 1 — GitHub org/repo admin (team CRUD, membership
        # reconcile, branch protection, drift audit). HITL-gated per op.
        GithubAdminCreateTeamTool(),
        GithubAdminSetTeamMembershipTool(),
        GithubAdminSetBranchProtectionTool(),
        GithubAdminAuditTeamMembershipTool(),
        # RFC 0007 Sprint 1 — Kubernetes ConfigMap tools (feature flags,
        # non-secret config). dev=ALLOW / staging=ASK / prod=ASK;
        # FEATURE_*/ENABLE_*/*_ENABLED keys in prod escalate to ASK_DUAL.
        ReadConfigMapTool(),
        SetConfigMapValueTool(),
        DeleteConfigMapKeyTool(),
        ListConfigMapsTool(),
        # RFC 0008 Sprint 1 — provider webhook management
        # (signing secrets captured → RFC 0005 writer in one atomic flow)
        StripeWebhookCreateTool(),
        StripeWebhookListTool(),
        StripeWebhookDeleteTool(),
        ResendWebhookCreateTool(),
        JanuaOidcRedirectRegisterTool(),
    ]
