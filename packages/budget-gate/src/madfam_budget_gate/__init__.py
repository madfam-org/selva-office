"""madfam-budget-gate — HITL spend gate for autonomous LLM workloads.

Public surface:

    from madfam_budget_gate import (
        RunShape,
        CostEstimate,
        PricingTable,
        estimate,
        GateConfig,
        ApprovalRecord,
        SpendTracker,
        BudgetDenied,
        BudgetExceededError,
        require_approval,
        new_tracker,
        install_sigusr1_tripwire,
    )

Minimum viable usage::

    import os
    from madfam_budget_gate import (
        RunShape, estimate, GateConfig, require_approval, new_tracker,
    )

    os.environ.setdefault("MADFAM_BUDGET_HARD_CAP_USD", "10.00")
    os.environ.setdefault("MADFAM_EXPERIMENT_ID", "phyne-drip-nightly")
    os.environ.setdefault("MADFAM_EXPERIMENT_OWNER", "aldo")

    cfg = GateConfig.from_env()
    shape = RunShape(
        model="meta-llama/Llama-3.3-70B-Instruct",
        iterations=1,
        candidates_per_iteration=1,
        eval_set_size=50,
        input_tokens_per_eval=2_000,
        output_tokens_per_eval=500,
    )
    est = estimate(shape)
    approval = require_approval(est, cfg)
    tracker = new_tracker(approval, cfg)
    # ... every LLM call: tracker.record_usage(...)

See the README in this package for the full HITL contract and adoption guide.
"""

from .cost_model import (
    CostEstimate,
    ModelPrice,
    PricingTable,
    RunShape,
    estimate,
)
from .gate import (
    ApprovalRecord,
    BudgetDenied,
    BudgetExceededError,
    GateConfig,
    SpendTracker,
    install_sigusr1_tripwire,
    new_tracker,
    require_approval,
)

__all__ = [
    "ApprovalRecord",
    "BudgetDenied",
    "BudgetExceededError",
    "CostEstimate",
    "GateConfig",
    "ModelPrice",
    "PricingTable",
    "RunShape",
    "SpendTracker",
    "estimate",
    "install_sigusr1_tripwire",
    "new_tracker",
    "require_approval",
]

__version__ = "0.1.0"
