"""Cost estimation for any LLM-spending workload in the MADFAM ecosystem.

The estimator is intentionally conservative: when in doubt, it overstates cost.
It is safer to block a harmless run than to wave through a runaway one.

Callers override the pricing table via ``MADFAM_MODEL_PRICING_PATH`` or by
passing a path to ``PricingTable.load()``. The bundled default lives at
``madfam_budget_gate/default_config/model_pricing.yaml`` and should be
treated as a starting point — prices drift; re-verify monthly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_PRICING_PATH = (
    Path(__file__).resolve().parent / "default_config" / "model_pricing.yaml"
)


@dataclass(frozen=True)
class ModelPrice:
    model: str
    input_usd_per_mtok: float
    output_usd_per_mtok: float
    vendor: str


@dataclass(frozen=True)
class RunShape:
    """Describes the worst-case token profile of a Meta-Harness run.

    All fields are worst case, not expected. The gate should see the ceiling.
    """

    model: str
    iterations: int
    candidates_per_iteration: int
    eval_set_size: int
    input_tokens_per_eval: int
    output_tokens_per_eval: int
    # Proposer cost is usually much smaller than inner-loop eval cost, but
    # on cheap models it can dominate. Pass zero if the proposer runs
    # under a separate approval.
    proposer_input_tokens: int = 0
    proposer_output_tokens: int = 0
    proposer_model: str | None = None


@dataclass(frozen=True)
class CostEstimate:
    run: RunShape
    total_usd: float
    inner_loop_usd: float
    proposer_usd: float
    total_input_tokens: int
    total_output_tokens: int

    def summary_lines(self) -> list[str]:
        lines = [
            f"model            : {self.run.model}",
            f"iterations       : {self.run.iterations}",
            f"candidates/iter  : {self.run.candidates_per_iteration}",
            f"eval set size    : {self.run.eval_set_size}",
            f"input tok total  : {self.total_input_tokens:,}",
            f"output tok total : {self.total_output_tokens:,}",
            f"inner-loop cost  : ${self.inner_loop_usd:,.2f}",
        ]
        if self.proposer_usd > 0:
            lines.append(f"proposer cost    : ${self.proposer_usd:,.2f}")
        lines.append(f"WORST-CASE TOTAL : ${self.total_usd:,.2f}")
        return lines


class PricingTable:
    """Read-only price lookup sourced from YAML."""

    def __init__(self, models: dict[str, ModelPrice], fallback: ModelPrice) -> None:
        self._models = models
        self._fallback = fallback

    @classmethod
    def load(cls, path: Path | None = None) -> "PricingTable":
        resolved = Path(
            os.environ.get("MADFAM_MODEL_PRICING_PATH") or path or DEFAULT_PRICING_PATH
        )
        if not resolved.exists():
            raise FileNotFoundError(f"pricing table not found at {resolved}")
        raw = yaml.safe_load(resolved.read_text())
        models: dict[str, ModelPrice] = {}
        for name, body in (raw.get("models") or {}).items():
            models[name] = ModelPrice(
                model=name,
                input_usd_per_mtok=float(body["input_usd_per_mtok"]),
                output_usd_per_mtok=float(body["output_usd_per_mtok"]),
                vendor=str(body.get("vendor", "unknown")),
            )
        fb_raw = raw.get("unknown_model_fallback")
        if not fb_raw:
            raise ValueError("pricing table missing unknown_model_fallback")
        fallback = ModelPrice(
            model="__fallback__",
            input_usd_per_mtok=float(fb_raw["input_usd_per_mtok"]),
            output_usd_per_mtok=float(fb_raw["output_usd_per_mtok"]),
            vendor=str(fb_raw.get("vendor", "unknown")),
        )
        return cls(models, fallback)

    def price_for(self, model: str) -> ModelPrice:
        price = self._models.get(model)
        if price is None:
            # Fallback is pessimistic on purpose — unknown model => treated as
            # Opus-class for estimation.
            return ModelPrice(
                model=model,
                input_usd_per_mtok=self._fallback.input_usd_per_mtok,
                output_usd_per_mtok=self._fallback.output_usd_per_mtok,
                vendor="unknown",
            )
        return price

    def known_models(self) -> list[str]:
        return sorted(self._models)


def _cost_usd(price: ModelPrice, input_tokens: int, output_tokens: int) -> float:
    return (
        input_tokens * price.input_usd_per_mtok / 1_000_000.0
        + output_tokens * price.output_usd_per_mtok / 1_000_000.0
    )


def estimate(run: RunShape, pricing: PricingTable | None = None) -> CostEstimate:
    """Compute worst-case cost.

    Formula:
        calls_per_iter  = candidates_per_iteration * eval_set_size
        total_calls     = iterations * calls_per_iter
        total_input_tok = total_calls * input_tokens_per_eval
        total_output_tok= total_calls * output_tokens_per_eval
        inner_loop_usd  = price(model) applied to totals
        proposer_usd    = price(proposer_model) applied to proposer tokens
    """
    pricing = pricing or PricingTable.load()

    total_calls = run.iterations * run.candidates_per_iteration * run.eval_set_size
    total_input = total_calls * run.input_tokens_per_eval
    total_output = total_calls * run.output_tokens_per_eval

    inner_price = pricing.price_for(run.model)
    inner_cost = _cost_usd(inner_price, total_input, total_output)

    proposer_cost = 0.0
    if run.proposer_model and (run.proposer_input_tokens or run.proposer_output_tokens):
        proposer_price = pricing.price_for(run.proposer_model)
        proposer_cost = _cost_usd(
            proposer_price, run.proposer_input_tokens, run.proposer_output_tokens
        )

    return CostEstimate(
        run=run,
        total_usd=inner_cost + proposer_cost,
        inner_loop_usd=inner_cost,
        proposer_usd=proposer_cost,
        total_input_tokens=total_input + run.proposer_input_tokens,
        total_output_tokens=total_output + run.proposer_output_tokens,
    )
