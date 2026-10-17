# DRAFT — MADFAM as a factory of factories (internal positioning)

> **Status: DRAFT, INTERNAL.** Public copy (README, llms.txt, selva.town
> landing, pricing) is held by ruling R130 until the messaging house is
> signed. Nothing here is rendered on any public surface. The framing is the
> owner's and has no canon ruling yet: an owner ruling on whether it overlays
> the proposed four catalog groups (D-17) comes first.

## The idea in one line

MADFAM runs three automated production lines (software, geometry and
physical goods) and sells the capacity to run them as a product:
**Factory-as-a-Product**. Selva is the operator that coordinates the lines.

## The three lines

| Line | Turns | Into | MADFAM products | Selva today |
|---|---|---|---|---|
| Software factory | a spec | a deployed, monitored service | Enclii, Fragua, Janua, Selva | coding graph (worktree, tests, review, HITL push gate), deploy and Enclii tools, factory-manifest tools |
| Geometry factory | parameters and intent | manufacturable geometry | Yantra4D, geom-core, hyperobjects commons, Pliego, Fashion Cabinet; ceq for generative 3D | `generate_parametric_model`, `run_dfm_analysis` (Yantra4D) |
| Physical-goods factory | geometry and an order | a priced, scheduled, tracked part | Cotiza, Pravara MES, Forgesight | `generate_quote` (HITL-gated), `get_production_order_status` (read-only) |

**Factory-as-a-Product** coordinates the three as one offer. Each factory
publishes a manifest of its capabilities, inputs, outputs, SLAs and catalog
price references. Selva routes the work, and Dhanam bills it against the
Tulana/Dhanam catalog.

## What is true today versus what is a gap (keep claims honest)

- **True:**
  - The software line runs end to end inside Selva, behind HITL gates.
  - Geometry and quoting tools exist and are contract-tested against vendored fixtures.
  - Pravara status is read-only from Selva by design.
- **Gaps:**
  - There is no unified factory-manifest schema. The repo build manifest and Routecraft's product manifest differ.
  - There is no `graphs/phygital.py` and no first-party factory-line skills.
  - There are no geom-core, Pliego, Fashion Cabinet or Forgesight tools.
  - The physical line is not yet sellable self-serve.
  - Each gap is a backlog item in `data/credit-investment/backlog.yaml`.

## Copy candidates (for the messaging house to rule on, not for use)

- "De bits a átomos: tres fábricas, un operador."
- "Software, geometry, physical goods: three factories that run themselves, and the factory that runs them."
- "Factory-as-a-Product: rent the line, not the machine."

## Open owner questions

1. Is the trifecta canon, and does it overlay D-17? (It could add a `factory_line` registry field.)
2. Which Factory-as-a-Product definition is canonical: the protocol (T4 manifests), the micro-factory mesh (SOE), or both as layers?
3. When R130 lifts, which surfaces get this framing first?
