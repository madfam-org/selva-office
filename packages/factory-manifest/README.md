# Factory Manifest v1

**Status:** Draft — schema frozen, awaiting adopter feedback before v1.0 tag.

The Factory Manifest is the declarative contract that turns any MADFAM service
(or composition of services) into a **catalogable, composable, MXN-priced
SKU**. It's the protocol layer of Selva's "Factory-as-a-Product" manifesto.

```
                +--------- Factory Manifest ---------+
                |  inputs   outputs   failure_modes  |
                |  price    sla       idempotency    |
   Service -->  |  endpoint dependencies compliance  |  --> Selva / catalog
                +------------------------------------+
```

## Why this exists

Today, MADFAM services talk via ad-hoc webhooks, tRPC procedures, and
bus events. Good for plumbing, but:

1. **Selva can't compose what it can't introspect.** Without a machine-readable
   contract, composition is hand-coded per pair.
2. **Pricing isn't a property of the service.** You have to know where to look
   (Dhanam prices tables, hardcoded tier configs) to find out what one call
   costs — if anyone even wrote it down.
3. **"Factory-as-a-Product" is a vibe, not a protocol.** Until every factory
   publishes a manifest, we can't put factories in a catalog, compose them
   into bundled SKUs, or attribute revenue back to the underlying work.

A Factory Manifest fixes all three. One file per callable unit, checked into
the owning repo at `.factory-manifest.json`, validated in CI against
`schema/factory-manifest.v1.schema.json`, aggregated by Selva at discovery
time.

## What's in the manifest

| Field | Purpose |
|-------|---------|
| `factory_id` | Stable dotted id (`karafiel.cfdi-stamp`). Versioning is separate. |
| `version` | Semver. Breaking input/output changes bump major. |
| `status` | `alpha` / `beta` / `general_availability` / `deprecated`. |
| `inputs` / `outputs` | Inline JSON Schema — single-consumable artifact, no indirection. |
| `failure_modes` | Stable failure codes, retryable flag, HTTP status. What callers must handle. |
| `endpoint` | `http` / `grpc` / `a2a` / `event_bus`. URL, method, auth type. |
| `price` | MXN cents. `per_call` / `per_unit` / `subscription` / `free_internal`. |
| `sla` | p95/p99 latency, availability target, error-budget window. |
| `idempotency` | Key field + TTL + behavior. Enables safe retries. |
| `compliance` | CFDI impact, RFC required, PII classes, data residency. |
| `dependencies` | Other factories this one calls. Blast-radius + planning. |
| `observability` | PostHog events, Prometheus metrics, Sentry DSN key. |
| `rate_limits` | Published per-caller limits. |

The schema is `draft 2020-12` JSON Schema and validates with any conforming
validator (the examples below use Python's `jsonschema`).

## The three shipped example manifests

Three factories, chosen because they form the minimum viable MXN flywheel:

1. **`karafiel.cfdi-stamp`** — Mexican CFDI 4.0 issuance. The compliance wedge.
   Per-call priced at MX$4.50 (`per_call_mxn_cents: 450`).
2. **`dhanam.billing-charge`** — MXN charge across Stripe MX / Conekta / SPEI / OXXO.
   `free_internal` because it's the pipe, not the product; metered for visibility.
3. **`phyne.attribution-credit`** — closes the loop by crediting the originating
   agent. Event-bus protocol, fires `phyne.lead.converted`.

They're wired together via `dependencies`. Selva can walk the graph:

```
karafiel.cfdi-stamp
    └── (optional) tezca.domain-classify
    └── (required) janua.token-exchange

dhanam.billing-charge
    └── (optional) karafiel.cfdi-stamp
    └── (required) phyne.attribution-credit
```

Composition example: a Karafiel customer completes checkout →
`dhanam.billing-charge` fires → optionally triggers `karafiel.cfdi-stamp` for
the receipt → on success emits `phyne.lead.converted` →
`phyne.attribution-credit` credits the agent that sourced the lead.

All three manifests validate against the schema. Run:

```bash
cd packages/factory-manifest
python -c "
import json
from jsonschema import Draft202012Validator
schema = json.load(open('schema/factory-manifest.v1.schema.json'))
Draft202012Validator.check_schema(schema)
v = Draft202012Validator(schema)
for p in ['examples/karafiel.cfdi-stamp.manifest.json',
          'examples/dhanam.billing-charge.manifest.json',
          'examples/phyne.attribution-credit.manifest.json']:
    errs = list(v.iter_errors(json.load(open(p))))
    print(p, 'valid' if not errs else errs)"
```

## Adoption guide for service owners

1. **Pick a factory_id.** `<product>.<operation>`. Lowercase, dot-separated,
   dashes allowed. Stable forever. Never rename.
2. **Author the manifest.** Copy the nearest shipped example and edit in place.
   Inputs and outputs are inline JSON Schema — don't `$ref` to elsewhere.
3. **Put it in your repo at `.factory-manifest.json`.** One per callable
   entrypoint. Yes, large products will have several (e.g. Dhanam ships one
   per billing operation).
4. **Add CI validation.** Gate merges on schema validation:
   ```yaml
   - name: Validate factory manifest
     run: |
       pip install jsonschema
       python -c "import json; from jsonschema import Draft202012Validator; \
         s = json.load(open('../selva/packages/factory-manifest/schema/factory-manifest.v1.schema.json')); \
         Draft202012Validator(s).validate(json.load(open('.factory-manifest.json')))"
   ```
5. **Bump `version` on every breaking change.** Input/output changes that
   aren't strictly additive require a major bump.
6. **Move `status` deliberately.** `alpha` → `beta` → `general_availability`.
   Selva's catalog will only surface `beta`+ to public callers.

## What this replaces

- **Per-pair glue code** in Selva that hardcodes how factories compose.
- **Handwritten "how does this service work?" docs** that drift from reality.
- **Invisible pricing** scattered across Dhanam tier tables and hardcoded
  product cards.

It does NOT replace:

- OpenAPI. A manifest is a business contract; OpenAPI is an HTTP
  contract. Keep both; link them (the `endpoint.url` in a manifest is
  typically an OpenAPI-documented URL).
- The Selva proxy. The proxy routes; the manifest describes.
- Janua auth. Manifests declare `auth`; Janua still issues the tokens.

## Non-goals for v1

- **Multi-currency**. All prices are MXN cents. ADR: MXN-first is deliberate —
  the ecosystem's immediate goal is peso ingress (per Selva manifesto +
  `project_gtm_strategy` memory).
- **Workflow definitions.** A manifest describes one factory, not a
  multi-step choreography. Compose in Selva, not in the manifest.
- **Physical delivery.** Out of scope for v1; `pravara-mes`-style factories
  will extend v2.

## Validation dependency

`jsonschema>=4.23` in any language of choice. For Python CI:

```bash
pip install 'jsonschema[format]>=4.23'
```

## Next steps (not in this package)

- Selva-side: catalog aggregator that discovers manifests across the org and
  builds the composable graph.
- CI-side: reusable GitHub Action `madfam/validate-factory-manifest@v1`.
- Catalog UI: public-facing MXN SKU catalog on `madfam.io/factories`.
