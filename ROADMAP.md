# Selva Office (AutoSwarm) — Product Roadmap

> **Selva** is the autonomous virtual office product by **Innovaciones MADFAM SAS de CV**.
> It runs at `selva.town` and integrates with the full MADFAM ecosystem.

---

## Current Status: v1.2.1 — Production Ready ✅

| Metric | Value |
|--------|-------|
| API routes | 133 |
| Built-in tools | 54 |
| TS tests | 817+ passing |
| Python lint | 0 errors |
| Graph types | 8 node types + custom YAML |
| Messaging gateways | 18 channels |
| Solarpunk visual phases | 4/4 complete |
| A2A protocol | 4 endpoints |
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
- `[ ]` Provision DNS records for `selva.town` zone in Cloudflare
- `[ ]` Configure Cloudflare Tunnel routes
- `[ ]` Email routing: `*@selva.town` → `admin@madfam.io`
- `[ ]` Build + push Docker images to `ghcr.io/madfam-org`
- `[ ]` K8s secrets + configmap deployment
- `[ ]` Run `alembic upgrade head` in production
- `[ ]` Seed MADFAM org agents
- `[ ]` `selva.town/terms` and `selva.town/privacy` pages

---

## Enterprise Autonomy Roadmap

### Phase E1: Multi-Tenant Enterprise Hardening

**Goal**: Any Mexican business can self-provision a Selva org and start running autonomous operations.

- `[ ]` **Tenant provisioning API**: Self-service org creation with RFC (Registro Federal de Contribuyentes) validation
- `[ ]` **Department templates for Mexican businesses**: Auto-create Dirección General, Administración, Contabilidad, Ventas, Operaciones, RH, Legal
- `[ ]` **Per-tenant compute budgets**: Wire Dhanam (`dhanam/`) billing per org with token metering
- `[ ]` **Tenant data isolation audit**: Verify RLS on all 15 tables, Redis key prefixing, Colyseus room isolation
- `[ ]` **Enterprise SSO**: SAML/OIDC via Janua (`janua/`) for Azure AD, Google Workspace, custom LDAP
- `[ ]` **White-label capability**: Per-tenant branding (logo, colors, custom domain) on shared infrastructure

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
- `[ ]` **`CFDITool`**: Generate CFDI 4.0 XML, stamp via PAC (Finkok / SW SmarterWeb), generate PDF representation
- `[ ]` **`facturación` graph type**: CRM data → RFC validation → XML sealing (CSD) → PAC stamping → PDF → email delivery
- `[ ]` **Constancia de Situación Fiscal** lookup via SAT web services
- `[ ]` **RFC validation tool**: 4-char (persona moral) / 13-char (persona física) with check digit algorithm
- `[ ]` **Complemento de Pagos**: Payment complement for partial payments (common in Mexican B2B)

**Integration**: `factlas/` (if CFDI service exists), or new `packages/sat/` within autoswarm-office

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

#### Contabilidad (Accounting)
- `[ ]` Monthly close: bank reconciliation → pólizas → balance general
- `[ ]` Declaraciones mensuales: ISR provisional, IVA, DIOT preparation
- `[ ]` Integration: CONTPAQi / Aspel / Alegra adapters or direct SAT API
- `[ ]` **MADFAM integration**: `dhanam/` ledger for compute cost allocation per department

#### Ventas (Sales)
- `[ ]` Lead → Cotización → Pedido → Factura → Cobranza automated chain
- `[ ]` WhatsApp Business API integration (transactional messages — dominant Mexican B2B channel)
- `[ ]` Pipeline dashboard with Mexican sales cycle awareness (seguimiento culture)
- `[ ]` **MADFAM integration**: `phyne-crm/` for contact data, pipeline, activity tracking

#### Recursos Humanos (HR)
- `[ ]` Onboarding workflow: IMSS alta, contract generation, NDA, handbook delivery
- `[ ]` Offboarding: IMSS baja, finiquito/liquidación calculation, constancia laboral
- `[ ]` Performance review cycle with 360° feedback
- `[ ]` Training tracking for STPS compliance

#### Legal
- `[ ]` Contract generation: Mexican civil/mercantile law templates
- `[ ]` Poder notarial tracking and renewal alerts
- `[ ]` REPSE compliance: registration and periodic reporting for specialized services
- `[ ]` **MADFAM integration**: `legal-ops/` for contract lifecycle management, `tezca/` for legal intelligence

#### Operaciones (Operations)
- `[ ]` Supply chain: pedimento document automation for customs
- `[ ]` Inventory management with IMMEX/PITEX regime awareness
- `[ ]` Logistics: Mexican carrier integration (Estafeta, FedEx MX, DHL, Paquetexpress)
- `[ ]` **MADFAM integration**: `pravara-mes/` for manufacturing execution, `digifab-quoting/` for fabrication quotes, `routecraft/` for logistics optimization

### Phase E4: Mexican Market Intelligence Layer

**Goal**: Agents proactively monitor regulatory, economic, and market changes.

- `[ ]` **SAT monitor agent**: RFC status, tax obligation alerts, constancia updates
- `[ ]` **DOF agent**: Daily scan of Diario Oficial de la Federación for regulatory changes
- `[ ]` **INEGI data integration**: GDP, inflation, employment, industry-specific indicators
- `[ ]` **Economic indicators via Dhanam**: Real-time USD/MXN, TIIE rates, monetary policy alerts (Dhanam proxies Banxico SIE internally)
- `[ ]` **UMA/UMI tracker**: Current values for labor and tax calculations (updated annually by INEGI)
- `[ ]` **SIEM compliance**: Annual Sistema de Información Empresarial Mexicano registration automation
- `[ ]` **Profeco monitor**: Consumer protection regulation changes
- `[ ]` **MADFAM integration**: `social-sentiment-monitor/` for brand monitoring, `madfam-crawler/` for web intelligence, `fortuna/` for market problem intelligence

### Phase E5: Localization & Cultural Adaptation

**Goal**: Every agent interaction feels native to Mexican business culture.

- `[ ]` **Full Spanish (MX) language support**: All 10 skill definitions, system prompts, UI strings, error messages in Mexican Spanish
- `[ ]` **Mexican business calendar**: Art. 74 LFT holidays, puentes, Semana Santa, Buen Fin, CFDI deadlines (17th monthly for ISR)
- `[ ]` **Timezone handling**: CST/CDT default (`America/Mexico_City`), Sonora awareness (no DST), Quintana Roo (EST), border DST rules
- `[ ]` **Currency**: MXN primary, USD secondary for export/border businesses, UDI for mortgage/financial calculations
- `[ ]` **Number/date formatting**: DD/MM/YYYY, comma thousands, period decimal
- `[ ]` **Formal business communication**: Uso de usted, carta poder format, acuse de recibo conventions
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
│   ├── 54 built-in tools, 18 gateways, A2A protocol
│   └── Solarpunk UI, PWA, LiveKit SFU
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

## Immediate Next Sprint (Priority Order)

1. `[ ]` **CFDI 4.0 tool** — Highest value for Mexican market (every business needs electronic invoicing)
2. `[ ]` **WhatsApp Business API gateway** — Dominant B2B channel in Mexico (95%+ business adoption)
3. `[ ]` **Spanish (MX) agent prompts** — All 10 skill definitions + system prompts
4. `[ ]` **RFC validation tool** — Simple but essential for every Mexican business workflow
5. `[ ]` **Nómina calculation engine** — ISR tables + IMSS + INFONAVIT (complex, huge value)
6. `[ ]` **Factlas integration** — Connect `factlas/` repo for CFDI stamping backend

---

## Production Readiness Checklist

- `[x]` Zero Python lint errors (ruff)
- `[x]` Zero TypeScript type errors
- `[x]` 817+ TS tests passing
- `[x]` 252+ Python tests passing
- `[x]` 7/7 build tasks successful
- `[x]` 133 API routes loaded
- `[x]` Docker compose valid (8 services)
- `[x]` All hardcoded localhost → env vars
- `[x]` SSRF protection on all webhook handlers
- `[x]` Zero bare except:pass
- `[x]` Brand architecture correct (MADFAM ecosystem / Selva product)
- `[x]` PWA installable
- `[x]` Solarpunk visual overhaul complete
- `[ ]` Gateway secrets injection (DingTalk, Feishu, etc.)
- `[ ]` Docker socket sandboxing for worker pods
