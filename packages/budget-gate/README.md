# madfam-budget-gate

Shared HITL (human-in-the-loop) budget gate and cost estimator for
autonomous LLM-spending workloads across the MADFAM ecosystem.

Lifted from the Meta-Harness Phase 0 spike
(`tezca/experiments/meta-harness/src/meta_harness_madfam/`) to be reusable
by any service that wants three guarantees before it starts spending tokens:

1. **Pre-run hard cap.** Env-defined ceiling refuses estimates that exceed it.
2. **Per-run challenge.** Approver must type a challenge string that is
   deterministically derived from the estimate, so changing iterations or
   model invalidates the approval.
3. **Mid-run kill.** Every LLM call updates an in-process tracker; breaching
   `approved_cap × grace_factor` (default 1.10) raises `BudgetExceededError`
   on the next call.

Approval records are append-only JSON; per-call spend is JSONL.

---

## Install

In another package's `pyproject.toml`:

```toml
dependencies = [
    "madfam-budget-gate @ file:///workspaces/autoswarm-office/packages/budget-gate",
    # or once published to the MADFAM internal npm/pypi:
    # "madfam-budget-gate>=0.1",
]
```

## Minimum usage

```python
import os
from madfam_budget_gate import (
    RunShape, estimate, GateConfig, require_approval, new_tracker,
)

os.environ.setdefault("MADFAM_BUDGET_HARD_CAP_USD", "10.00")
os.environ.setdefault("MADFAM_EXPERIMENT_ID", "phyne-drip-nightly")
os.environ.setdefault("MADFAM_EXPERIMENT_OWNER", "aldo")

shape = RunShape(
    model="meta-llama/Llama-3.3-70B-Instruct",
    iterations=1,
    candidates_per_iteration=1,
    eval_set_size=50,
    input_tokens_per_eval=2_000,
    output_tokens_per_eval=500,
)
cfg = GateConfig.from_env()
est = estimate(shape)                   # uses bundled default pricing table
approval = require_approval(est, cfg)   # blocks on stdin until user types challenge
tracker = new_tracker(approval, cfg)

# Every LLM call:
# ... make the call ...
tracker.record_usage(
    model=shape.model,
    input_tokens=resp.usage.prompt_tokens,
    output_tokens=resp.usage.completion_tokens,
    usd=<computed>,  # or use your own price table
    tag="draft-email",
)
# Raises BudgetExceededError if the running total crosses the kill threshold.
```

## Env contract

| Var | Required | Meaning |
|-----|----------|---------|
| `MADFAM_BUDGET_HARD_CAP_USD` | yes | Absolute ceiling. Estimates above it are refused pre-run. |
| `MADFAM_BUDGET_GRACE_FACTOR` | no (default 1.10) | Mid-run kill at `approved × grace`. Clamped [1.0, 2.0]. |
| `MADFAM_EXPERIMENT_ID` | yes | Stable identifier; part of the challenge string + audit filename. |
| `MADFAM_EXPERIMENT_OWNER` | yes | Who is accountable for this spend. Recorded in audit log. |
| `MADFAM_APPROVALS_DIR` | no (default `./approvals`) | Where approval JSONs land. |
| `MADFAM_LOGS_DIR` | no (default `./logs`) | Where per-call spend JSONLs land. |
| `MADFAM_MODEL_PRICING_PATH` | no | Override bundled pricing YAML. |

## What it is NOT

- A full policy engine. No per-user quotas, no org-level caps.
- A streaming-aware cost accumulator (usage is read from the final response).
- A replacement for Selva-side metering (`compute_token_ledger`). The
  in-process tracker exists so autonomous loops kill themselves before Selva
  even knows there's a problem — the two layers are complementary.

## Intended adopters (as of 2026-04-17)

- `tezca/experiments/meta-harness/` — already depends on the lifted modules;
  migrating to this package next.
- `autoswarm-office/apps/workers/` — CRM drip composition. Wrap
  `call_llm()` to record against a per-tick tracker.
- `phyne-crm/apps/worker/` — outbound email drafting.
- Any future Meta-Harness pilot (dhanam categorization, phyne first-touch,
  fortuna Zeitgeist summarization).

## Tests

```bash
cd packages/budget-gate
python3 -m venv .venv && source .venv/bin/activate
pip install -e '.[dev]'
pytest
```

15 tests covering challenge stability, approval happy/reject paths,
env-config validation, tracker accumulation, and the sticky mid-run kill.

## Related runbooks

- `autoswarm-office/docs/runbooks/BRIDGE_DEEPINFRA.md` — how to flip task
  routing to DeepInfra while Anthropic is paused. Compatible with this gate.
