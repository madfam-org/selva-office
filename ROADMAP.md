# Selva Office (AutoSwarm) — Product Roadmap

> **Selva** is the autonomous virtual office product by **Innovaciones MADFAM SAS de CV**.
> It runs at `selva.town` and integrates with the full MADFAM ecosystem.

---

## Current Status: v2.0.0 — Enterprise Mexican Market MVP ✅

| Metric | Value |
|--------|-------|
| API routes | 139 |
| Built-in tools | 74 |
| Workflow graphs | 12 (coding, research, crm, deployment, puppeteer, meeting, project, billing, accounting, sales, intelligence, custom) |
| Ecosystem adapters | 6 (Karafiel, Dhanam, PhyneCRM, Tezca, Crawler, A2A) |
| Skills (en + es-MX) | 17 |
| Alembic migrations | 16 (0000–0015) |
| TS tests | 817+ passing |
| Enterprise tests | 308+ |
| Python lint | 0 errors |
| Messaging gateways | 18 channels |
| Solarpunk visual phases | 4/4 complete |
| PWA installable | Yes |

---

## Completed Milestones

### Q3/Q4: Autonomous Cleanroom Protocol ✅
LangGraph execution engine, Playwright browser tooling, durable task queue,
airgap handoff, Enclii deployment integration, QA Oracle sandbox.

### Q1: Hive Mind & Continuous Learning ✅
Autonomous skill generation, FTS5 edge memory, serverless hibernation,
MCP capabilities, dialectic profiling, 18-channel gateway.

### Q2: Hermes Gap Remediation ✅
Waves 1-4: skill refiner, memory compactor, cron scheduler, browser/vision,
HITL approval gate, plugin architecture, prompt caching, context compression,
session checkpoints, SOUL.md, 23 new tools, skills hub.

### Competitive Dominance Waves 1-4 (v0.6.0–v0.9.0) ✅
Screen sharing polish, iterative skill refinement, PWA, voice STT (Whisper),
LiveKit SFU scaling, tool expansion (→54), A2A protocol, mobile UX polish,
competitive benchmark documentation.

### Solarpunk Visual Overhaul Phases 1-4 (v1.0.0–v1.2.0) ✅
Warm earth palette, 79 FF6-quality tiles, 12-pose walk cycles, solarpunk UI
tokens + particles, Living Office biome map, atmospheric lighting, companions,
emotes, animated tiles, agent idle animations.

### Codebase Remediation (v0.5.1–v1.2.1) ✅
K8s env fix, Alembic migration chain, SSRF protection, bare exception logging,
auth exports, skills package fix, Colyseus state sync, brand correction
(MADFAM ecosystem / Selva product), zero ruff errors, hardcoded localhost fix.

---

## Selva Brand Deployment Checklist

- `[x]` Product domains: `api.selva.town`, `ws.selva.town`, `admin.selva.town`, `app.selva.town`
- `[x]` MADFAM ecosystem preserved: `auth.madfam.io`, `crm.madfam.io`, `status.madfam.io`, `npm.madfam.io`
- `[x]` Redirect config: `selvatown.com` → `selva.town` (301)
- `[x]` DNS records provisioned in Cloudflare (all zones)
- `[x]` Cloudflare Tunnel routes configured
- `[x]` Email routing: `*@selva.town` → `admin@madfam.io`
- `[x]` Docker images built + pushed to `ghcr.io/madfam-org`
- `[x]` K8s secrets (8 keys) + configmap (org-config) deployed
- `[x]` Alembic migrations applied in production
- `[x]` MADFAM org seeded (4 nodes, 10 named agents)
- `[ ]` `selva.town/terms` and `selva.town/privacy` pages
- `[ ]` Working unsubscribe endpoint at `madfam.io/unsubscribe`

---

## Factory-as-a-Product Protocol Roadmap

> **Goal**: End-to-end phygital pipeline where a customer's digital design
> becomes a quoted, manufactured, shipped, and invoiced physical product —
> entirely orchestrated by Selva agents.

### Phase F1: Autonomous Revenue Loop ✅ Code Complete (2026-04-16)

The CRM-driven email loop is deployed and security-hardened. Waiting on
Anthropic credits and Stripe live mode confirmation.

```
HeartbeatService (*/30 cron)
  → CRM Scraper → Hot Lead Detection
    → Auto-Dispatch (dedup, 10/tick cap, HITL gate)
      → LLM Drafts Email (via inference proxy)
        → Resend Sends (madfam.io verified, CAN-SPAM compliant)
          → Dhanam Checkout CTA (Stripe MX, 6 products, 15 prices)
            → Payment → Subscription Activation
```

Status: **Blocked on $20 Anthropic credits + Stripe live mode verification.**

### Phase F2: Compliance Wedge (GTM Wave 1)

Lead with Karafiel compliance for Mexican SMBs:
- `[x]` CFDI 4.0 tools (generate, stamp, status, blacklist check)
- `[x]` RFC validation
- `[x]` Billing graph (6-node monthly close)
- `[ ]` Karafiel public pricing page ($499 MXN/mo)
- `[ ]` 10+ paying customers on Karafiel compliance
- `[ ]` Referral flywheel active (PhyneCRM funnel → Dhanam rewards)

### Phase F3: Fabrication Bundle (GTM Wave 2)

Bundle Cotiza + Yantra4D + PravaraMES for digital fabrication shops:
- `[x]` Cotiza↔Yantra4D bidirectional webhooks
- `[x]` Cotiza↔PravaraMES HMAC-signed order webhooks
- `[x]` PravaraMES↔Dhanam usage billing
- `[ ]` **Phygital workflow graph** (`phygital.py`): design → quote → approve → manufacture → ship → invoice
  - Yantra4D: customer uploads parametric design, Selva renders + generates BOM
  - Cotiza: auto-quotes based on BOM + ForgeSight market pricing
  - Customer approval (HITL gate in browser at app.selva.town)
  - PravaraMES: creates work order, tracks production
  - Dhanam: generates invoice, CFDI stamp via Karafiel
  - Logistics: shipment tracking (Estafeta/FedEx MX integration — future)
- `[ ]` End-to-end demo: parametric design → physical product delivered

### Phase F4: Intelligence APIs (GTM Wave 3)

Expose Fortuna + Tezca + Forgesight as paid APIs:
- `[x]` Inference centralized through Selva proxy
- `[x]` API key system via Janua + credit metering via Dhanam
- `[ ]` Fortuna public API (problem intelligence, market sensing)
- `[ ]` Tezca public API (legal search, 30K+ Mexican laws)
- `[ ]` Forgesight public API (fabrication pricing intelligence)

### Phase F5: Full Platform Launch (GTM Wave 4-5)

Selva seats at $149-499/mo as the autonomous AI workforce:
- `[ ]` Proven unit economics (LTV > CAC)
- `[ ]` Multi-tenant self-provisioning
- `[ ]` Per-tenant compute budgets wired to Dhanam subscriptions
- `[ ]` White-label capability
- `[ ]` 3D Voxel View (React Three Fiber + MagicaVoxel)
- `[ ]` $500K MRR target at 24 months

---

## Enterprise Autonomy Roadmap

### Phase E1: Multi-Tenant Enterprise Hardening

**Goal**: Any Mexican business can self-provision a Selva org and start running autonomous operations.

- `[x]` **Tenant provisioning API** (Sprint 7): `POST /api/v1/tenants/`, TenantConfig model, migration 0015, RFC validation via Karafiel
- `[x]` **Department templates** (Sprint 7): Auto-create 6 Mexican departments (Dirección General, Administración, Contabilidad, Ventas, Operaciones, Legal)
- `[x]` **Daily task limits** (Sprint 7): Per-tenant enforcement (429) in swarms dispatch
- `[ ]` **Per-tenant compute budgets**: Wire Dhanam subscription tier → quota enforcement
- `[ ]` **Tenant data isolation audit**: Verify RLS on all 16 tables, Redis key prefixing, Colyseus room isolation
- `[ ]` **Enterprise SSO**: SAML/OIDC via Janua per-tenant connections
- `[ ]` **White-label capability**: Per-tenant branding (logo, colors, custom domain)

**MADFAM Ecosystem Integration**:
| Repo | Role | Integration |
|------|------|-------------|
| `janua/` | Authentication | SSO, OIDC, enterprise connections, guest access |
| `dhanam/` | Billing | Per-tenant subscription, compute token ledger, usage metering |
| `enclii/` | Deployment | Tenant-isolated worker pod provisioning, scale-to-zero |
| `phyne-crm/` | CRM | Per-tenant customer data, pipeline, activity feed |

### Phase E2: Mexican Regulatory Compliance

**Goal**: Agents autonomously handle SAT obligations, labor law compliance, and data privacy.

#### SAT / CFDI 4.0 (Electronic Invoicing)
- `[x]` **CFDI tools via Karafiel** (Sprint 1): CFDIGenerate, CFDIStamp, CFDIStatus, BlacklistCheck — all delegating to Karafiel's DRF API
- `[x]` **Billing graph** (Sprint 1): 6-node workflow (fetch → validate RFCs → blacklist → generate → stamp → notify) with conditional edges
- `[x]` **RFC validation** (Sprint 1): RFCValidationTool via KarafielAdapter + regex format check in tenants router
- `[x]` **WhatsApp invoice delivery** (Sprint 2): factura_enviada template via Meta Business API
- `[x]` **Invoices API**: POST /generate + GET /{uuid}/status
- `[ ]` **Constancia de Situación Fiscal** lookup via Karafiel SAT portal agent
- `[ ]` **Complemento de Pagos**: Partial payment CFDI complement via Karafiel

**Integration**: All compliance via `karafiel/` (SAT, CFDI, fiscal modules)

#### Labor Law (Ley Federal del Trabajo)
- `[ ]` **Nómina calculation engine**: ISR retention tables (SAT annual update), IMSS cuotas, INFONAVIT, fondo de ahorro
- `[ ]` **IMSS automation**: Alta, baja, modificación salarial via IDSE/SUA integration
- `[ ]` **Vacation tracking**: 12+ days first year (2023 reform), progressive scale, prima vacacional (25%)
- `[ ]` **Aguinaldo calculation**: 15 days minimum by Dec 20, pro-rata for partial year
- `[ ]` **PTU distribution**: 10% of fiscal profit, 50/50 split (days worked / salary proportion)
- `[ ]` **NOM-035 compliance**: Psychosocial risk surveys, STPS report generation

#### Data Privacy (LFPDPPP)
- `[ ]` **PII classification tagging** on all agent-processed documents
- `[ ]` **Right-to-deletion workflow**: Agent searches + purges PII across artifacts, memory, transcripts
- `[ ]` **Privacy notice generator**: Per-tenant aviso de privacidad from template
- `[ ]` **Cross-border data transfer controls**: Flag when data leaves Mexican jurisdiction

### Phase E3: Department-Specific Autonomous Workflows

**Goal**: Pre-built graph templates that agents execute end-to-end for each department.

#### Contabilidad (Accounting) ✅ Sprint 4
- `[x]` **Accounting graph**: 5-node monthly close (fetch → reconcile → compute taxes → prepare declaration → HITL review)
- `[x]` **DhanamAdapter**: list_transactions, get_bank_statements (Belvo), get_payment_summary (Stripe MX/Conekta/OXXO/SPEI), get_pos_transactions, economic indicators (exchange rate, TIIE, inflation, UMA)
- `[x]` **Tax tools**: ISRCalculator, IVACalculator, BankReconciliation, DeclarationPrep, PaymentSummary — all via Karafiel/Dhanam
- `[x]` **Tax compliance skill**: SKILL.md + SKILL.es-MX.md
- `[ ]` CONTPAQi / Aspel adapter for ERP export

#### Ventas (Sales) ✅ Sprint 5
- `[x]` **Sales graph**: 7-node pipeline (qualify → cotización → approval → send → pedido → billing → cobranza)
- `[x]` **WhatsApp Business templates** (Sprint 2): factura_enviada, recordatorio_pago, confirmacion_pedido, cotizacion_lista
- `[x]` **PhyneCRM integration**: lead scoring, pipeline management, activity logging
- `[x]` **Sales pipeline skill**: SKILL.md + SKILL.es-MX.md
- `[ ]` Pipeline analytics dashboard in office UI

#### Recursos Humanos (HR)
- `[ ]` Onboarding workflow: IMSS alta, contract generation, NDA, handbook delivery
- `[ ]` Offboarding: IMSS baja, finiquito/liquidación calculation, constancia laboral
- `[ ]` Performance review cycle with 360° feedback
- `[ ]` Training tracking for STPS compliance

#### Legal ✅ Sprint 5
- `[x]` **Legal tools**: ContractGenerate (→Karafiel CLM), REPSECheck (→Karafiel), LawSearch (→Tezca), ComplianceCheck (→Tezca)
- `[x]` **TezcaAdapter**: search_laws, get_article, check_compliance
- `[x]` **Legal compliance skill**: SKILL.md + SKILL.es-MX.md
- `[ ]` Poder notarial tracking and renewal alerts
- `[ ]` **MADFAM integration**: `legal-ops/` for contract lifecycle management

#### Operaciones (Operations)
- `[ ]` Supply chain: pedimento document automation for customs
- `[ ]` Inventory management with IMMEX/PITEX regime awareness
- `[ ]` Logistics: Mexican carrier integration (Estafeta, FedEx MX, DHL, Paquetexpress)
- `[ ]` **MADFAM integration**: `pravara-mes/` for manufacturing execution, `digifab-quoting/` for fabrication quotes, `routecraft/` for logistics optimization

### Phase E4: Mexican Market Intelligence Layer

**Goal**: Agents proactively monitor regulatory, economic, and market changes.

- `[ ]` **SAT monitor agent**: RFC status, tax obligation alerts, constancia updates
- `[x]` **DOF agent** (Sprint 6): DOFMonitorTool via CrawlerAdapter → madfam-crawler
- `[ ]` **INEGI data integration**: GDP, employment, industry-specific indicators
- `[x]` **Economic indicators via Dhanam** (Sprint 6): ExchangeRate (USD/MXN), TIIE, Inflation, UMA — all via DhanamAdapter
- `[x]` **UMA/UMI tracker** (Sprint 6): UMATrackerTool via DhanamAdapter
- `[x]` **Intelligence graph** (Sprint 6): 4-node daily briefing (scan DOF → economic data → LLM briefing → notify team)
- `[x]` **Market intelligence skill**: SKILL.md + SKILL.es-MX.md
- `[ ]` **SIEM compliance**: Annual registration automation
- `[ ]` **Profeco monitor**: Consumer protection regulation changes
- `[ ]` **MADFAM integration**: `social-sentiment-monitor/` for brand monitoring, `fortuna/` for market problem intelligence

### Phase E5: Localization & Cultural Adaptation

**Goal**: Every agent interaction feels native to Mexican business culture.

- `[x]` **Full Spanish (MX) language support** (Sprint 3): 15 SKILL.es-MX.md files, locale-aware system prompts (plan/implement/review), graph prompt variants (project, crm, billing, coding, research), SkillRegistry locale parameter
- `[x]` **Timezone/currency/locale** (Sprint 7): TenantConfig with defaults (America/Mexico_City, MXN, es-MX)
- `[ ]` **Mexican business calendar**: Art. 74 LFT holidays, puentes, Semana Santa, Buen Fin, CFDI deadlines
- `[ ]` **Number/date formatting**: DD/MM/YYYY, comma thousands, period decimal
- `[ ]` **MADFAM integration**: `madfam-site/` for Mexican-localized marketing pages

### Phase E6: Enterprise Architecture Scaling

**Goal**: Support 100+ concurrent tenant organizations with full data sovereignty.

- `[ ]` **Multi-region deployment**: Primary in Mexico-adjacent region (GCP `us-south1` / AWS `us-east-1`), latency <30ms from CDMX
- `[ ]` **Data residency option**: All-Mexico hosting for government contracts and LFPDPPP compliance
- `[ ]` **Horizontal scaling**: Auto-scale workers per tenant load via Enclii (`enclii/`)
- `[ ]` **API-first architecture**: Every agent capability exposed via REST + A2A for integration with Mexican ERPs (SAP, Oracle, CONTPAQi, Aspel, Microsip)
- `[ ]` **Offline-capable PWA**: Critical for businesses in areas with intermittent connectivity
- `[ ]` **Audit trail**: Complete event log per tenant for regulatory compliance (SAT audits, STPS inspections)
- `[ ]` **MADFAM integration**: `internal-devops/` for infrastructure automation, `enclii/` for deployment orchestration

---

## Full MADFAM Ecosystem Integration Map

```
MADFAM Ecosystem (Innovaciones MADFAM SAS de CV)
│
├── 🏢 Selva Office (autoswarm-office/) — THIS PRODUCT
│   ├── selva.town — Virtual office + AI agent swarm
│   ├── 74 built-in tools, 12 graphs, 6 adapters, 18 gateways, A2A protocol
│   └── Solarpunk UI, PWA, LiveKit SFU, es-MX locale, multi-tenant
│
├── 🔐 Janua (janua/) — Authentication & SSO
│   ├── auth.madfam.io
│   ├── OIDC/SAML, enterprise connections, guest access
│   └── → Selva uses for all user auth + tenant isolation
│
├── 💰 Dhanam (dhanam/) — Billing & Subscriptions
│   ├── dhan.am
│   ├── Compute token ledger, subscription tiers, webhooks
│   └── → Selva uses for per-tenant metering + quotas
│
├── 🚀 Enclii (enclii/) — Deployment & Infrastructure
│   ├── enclii.dev
│   ├── Container orchestration, scale-to-zero, webhooks
│   └── → Selva uses for worker pod provisioning + deployment graph
│
├── 📊 PhyneCRM (phyne-crm/) — Customer Relationship Management
│   ├── crm.madfam.io
│   ├── Contacts, pipeline, activities, billing profiles
│   └── → Selva uses for CRM graph, lead data, customer context
│
├── ⚖️ Tezca (tezca/) — Legal Intelligence
│   ├── tezca.mx
│   └── → Selva E3: contract analysis, regulatory monitoring
│
├── 🔮 Fortuna (fortuna/) — Problem Intelligence
│   ├── fortuna.tube
│   └── → Selva E4: market problem detection, opportunity scoring
│
├── 🏭 Pravara MES (pravara-mes/) — Manufacturing Execution
│   └── → Selva E3: production scheduling, quality tracking
│
├── 🎨 Yantra4D (yantra4d/) — 3D Design & Digital Twins
│   ├── yantra4d.com
│   └── → Selva E3: product visualization, facility planning
│
├── 🧮 Coforma Studio (coforma-studio/) — Fabrication Quoting
│   ├── cotiza.studio
│   └── → Selva E3: manufacturing cost estimation
│
├── 🎰 CEQ (ceq/) — Creative AI Engine
│   ├── ceq.lol
│   └── → Selva E3: content generation, brand creative
│
├── 📡 Madfam Crawler (madfam-crawler/) — Web Intelligence
│   └── → Selva E4: DOF monitoring, competitor tracking
│
├── 📈 Social Sentiment Monitor (social-sentiment-monitor/)
│   └── → Selva E4: brand monitoring, market sentiment
│
├── 🧾 Factlas (factlas/) — Invoice/CFDI Services
│   └── → Selva E2: CFDI 4.0 stamping, SAT integration
│
├── 📐 Geom Core (geom-core/) — Geometry Engine
│   └── → Yantra4D dependency, spatial calculations
│
├── 🌿 Solarpunk Foundry (solarpunk-foundry/) — Design System
│   └── → Selva: solarpunk UI tokens, component library
│
├── 🎴 Stratum TCG (stratum-tcg/) — Card Game
├── 🌙 Nuit One (nuit-one/) — Night Operations
├── 🏗️ Forj (forj/) — Build Tools
├── 🔍 Forgesight (forgesight/) — Code Analysis
├── 📜 Bloom Scroll (bloom-scroll/) — Document Platform
├── 🧪 Sim4D (sim4d/) — Simulation Engine
├── 🏪 Tablaco (tablaco/) — Marketplace
├── 🛤️ Routecraft (routecraft/) — Logistics
├── 🎯 Zavlo (zavlo/) — Task Management
├── 🔧 Blueprint Harvester (blueprint-harvester/) — Schema Extraction
├── 📧 Proton Bridge Pipeline (proton-bridge-pipeline/) — Email Processing
├── 🏠 Karafiel (karafiel/) — Property Management
├── 💎 Avala (avala/) — Asset Valuation
├── 🖥️ Server Auction Tracker (server-auction-tracker/) — Hardware
├── 🎮 Turnbased Engine (turnbased-engine/) — Game Engine
├── 🌐 Madfam Site (madfam-site/) — Corporate Website
├── 🔒 Primavera3D (primavera3d/) — 3D Security
├── 📋 Rondelio (rondelio/) — Inspections
├── 🛡️ Internal DevOps (internal-devops/) — Infrastructure
└── 📦 Autoswarm Sandbox (autoswarm-sandbox/) — Agent Testing
```

---

## Autonomous Revenue Loop (v2.1.0) — 2026-04-16 ✅ Code Complete

### Infrastructure Deployed
- `[x]` HeartbeatService cron (`*/30 * * * *`) with CRM scraper + auto-dispatch
- `[x]` PlaybookGuard with conditional approval bypass + financial circuit breaker ($50/day)
- `[x]` CRM graph: fetch_context → draft_communication → approval_gate → send (Resend + PhyneCRM log)
- `[x]` Resend Pro transactional ($20/mo, 50K emails, 10 domains). madfam.io verified
- `[x]` MADFAM branded HTML email template (table-based, Outlook/Gmail/Apple Mail compatible)
- `[x]` Service consumption tracking (email sends → event stream)
- `[x]` Email delivery skill definition (`packages/skills/skill-definitions/email-delivery/SKILL.md`)
- `[x]` Security hardened: dev-bypass rejected in production, proper SSO via Janua PKCE
- `[x]` Responsive UI: Phaser RESIZE mode, mobile HUD, chat compaction
- `[x]` Player spawn fix: TMJ map spawn points (not hardcoded wall tile)

### Inference Centralization
- `[x]` OpenAI-compatible proxy at `/v1/chat/completions` + `/v1/embeddings` (`inference_proxy.py`)
- `[x]` Shared `build_router_from_env()` factory (`packages/inference/madfam_inference/factory.py`)
- `[x]` Org-config ConfigMap deployed to K8s, mounted at `/etc/autoswarm/org-config.yaml`
- `[x]` ServiceConfig model for tracking external accounts (Resend, Anthropic, DeepInfra, Stripe, etc.)
- `[x]` PhyneCRM, Fortuna, Yantra4D secrets patched for Selva inference routing
- `[x]` 196 inference tests passing (org_config + router + factory + worker wiring)

### Blocking First Revenue
- `[ ]` **Anthropic API credits** — $0 balance blocks all LLM inference. Add $20 at console.anthropic.com
- `[ ]` **Stripe live mode** — Verify `sk_live_` prefix (not `sk_test_`)
- `[ ]` Resend domain verification (9 pending — DNS records added, click "Verify" in dashboard)
- `[ ]` DeepInfra API key (optional — 13x cost reduction on volume tasks)
- `[ ]` PhyneCRM webhook registration (CRM → Selva event flow)

---

## Immediate Next Sprint (Priority Order)

1. `[ ]` **Add Anthropic credits** — Unblocks entire autonomous loop + all ecosystem AI features
2. `[ ]` **Verify Stripe live mode** — Confirm real payments can flow
3. `[ ]` **Verify Resend domains** — Expand branded email across 9 ecosystem services
4. `[ ]` **First autonomous sale** — HeartbeatService picks up lead → drafts email → sends → checkout CTA → payment
5. `[ ]` **DeepInfra API key** — 13x cost reduction ($0.23 vs $3 per 1M tokens)
6. `[ ]` **3D Voxel View** — React Three Fiber + MagicaVoxel (see `ROADMAP_3D_VOXEL.md`)

---

## Production Readiness Checklist

- `[x]` Zero Python lint errors (ruff)
- `[x]` Zero TypeScript type errors
- `[x]` 817+ TS tests passing
- `[x]` 252+ Python tests passing (196 inference alone)
- `[x]` 7/7 build tasks successful
- `[x]` 139 API routes loaded
- `[x]` Docker compose valid (8 services)
- `[x]` All hardcoded localhost → env vars
- `[x]` SSRF protection on all webhook handlers
- `[x]` Zero bare except:pass
- `[x]` Brand architecture correct (MADFAM ecosystem / Selva product)
- `[x]` PWA installable
- `[x]` Solarpunk visual overhaul complete
- `[x]` Org-config ConfigMap deployed to K8s
- `[x]` Inference proxy live (`/v1/chat/completions` + `/v1/embeddings`)
- `[x]` Ecosystem inference centralized (Fortuna, Yantra4D, PhyneCRM → Selva proxy)
- `[x]` Service resource registry (8 external accounts tracked)
- `[x]` Email delivery verified (Resend Pro, madfam.io domain)
- `[x]` 6 autoswarm pods healthy (nexus-api, workers, gateway, colyseus, office-ui, admin)
- `[x]` ArgoCD synced to latest commit
- `[x]` Dev-bypass rejected in production auth
- `[ ]` Anthropic API credit balance > $0
- `[ ]` Stripe MX in live mode (sk_live_)
- `[ ]` Gateway secrets injection (DingTalk, Feishu, etc.)
- `[ ]` Docker socket sandboxing for worker pods
