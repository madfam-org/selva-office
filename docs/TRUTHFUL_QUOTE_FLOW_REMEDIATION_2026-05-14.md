# Selva truthful quote orchestration roadmap

Last updated: 2026-10-08

## Scope

Selva agents must be able to generate client quotes through Yantra4D/Cotiza without human superadmin credentials and without presenting fallback pricing as final.

## Current evidence

- `GenerateQuoteTool` supports project-based Yantra quote requests and structured Cotiza quote requests.
- Unit tests prove the tool routes project slugs to Yantra and structured geometry to Cotiza.
- The tool requires `market_verified=true` by default and fails closed when a downstream quote is not market verified.
- 2026-05-14 update adds service-token propagation for Yantra and Cotiza calls.
- 2026-10-07 update: the phygital tools call only the routes vendored in
  `packages/tools/tests/fixtures/phygital_routes.json`, send the service token on
  every request, and send nothing when no token is configured.
- 2026-10-08 update: Yantra4D and Pravara-MES calls mint short-lived Janua
  `client_credentials` tokens from per-edge client credentials and cache them
  until 60 seconds before expiry (`selva_tools/builtins/service_auth.py`); static
  tokens remain the fallback.

## Production gap

Selva still needs provisioned Janua/Enclii-backed service credentials with the minimum scopes required for live client quoting.

## Remediation plan

1. Create a dedicated Selva quote service account.
2. Grant only the required scopes: `yantra4d:quote`, `yantra4d:render` (Yantra4D checks it on the render routes for machine tokens), `cotiza:quote`, `forgesight:read`, `pravara-mes:read` (production-order status), and later `phynd:engagement.write`.
3. Store service credentials through Enclii secrets, not human accounts.
4. Give the workers one Janua client per machine edge: `SELVA_YANTRA4D_CLIENT_ID` / `SELVA_YANTRA4D_CLIENT_SECRET` (scope `yantra4d:render`, from the `selva-service-clients` ExternalSecret) and `SELVA_PRAVARA_CLIENT_ID` / `SELVA_PRAVARA_CLIENT_SECRET` (scope `pravara-mes:read`). The tools mint and cache short-lived tokens; static tokens (`SELVA_YANTRA4D_SERVICE_TOKEN`, `SELVA_PRAVARA_SERVICE_TOKEN`, `SELVA_COTIZA_SERVICE_TOKEN` or the shared `SELVA_SERVICE_TOKEN`) are only a fallback, and Cotiza still uses one.
5. Keep `require_market_verified=true` as the default.
6. Map downstream failures to agent-actionable messages: auth missing, tier denied, market data unavailable, quote needs review, and client-ready.
7. Add staging/live contract tests once the service account exists.

## Acceptance gates

- Selva can request a client quote without superadmin credentials.
- Selva refuses to report a final quote unless the downstream response is market verified.
- Service-token headers are covered by unit tests.
- Live contract tests use service credentials only.
