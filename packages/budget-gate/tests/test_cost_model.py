from __future__ import annotations

from madfam_budget_gate.cost_model import RunShape, estimate


def test_estimate_basic_math(tiny_pricing):
    # 1 iter * 2 candidates * 5 items = 10 calls
    # 10 calls * 1000 input + 10 calls * 200 output
    # = 10_000 input tok, 2_000 output tok
    # tiny-model = $1/Mtok input, $2/Mtok output
    # = 0.010 + 0.004 = $0.014
    shape = RunShape(
        model="tiny-model",
        iterations=1,
        candidates_per_iteration=2,
        eval_set_size=5,
        input_tokens_per_eval=1000,
        output_tokens_per_eval=200,
    )
    est = estimate(shape, tiny_pricing)
    assert est.total_input_tokens == 10_000
    assert est.total_output_tokens == 2_000
    assert abs(est.inner_loop_usd - 0.014) < 1e-9
    assert abs(est.total_usd - 0.014) < 1e-9
    assert est.proposer_usd == 0.0


def test_proposer_adds_to_total(tiny_pricing):
    shape = RunShape(
        model="tiny-model",
        iterations=1,
        candidates_per_iteration=1,
        eval_set_size=1,
        input_tokens_per_eval=1000,
        output_tokens_per_eval=1000,
        proposer_model="bigger-model",
        proposer_input_tokens=1_000_000,   # 1 Mtok
        proposer_output_tokens=500_000,    # 0.5 Mtok
    )
    est = estimate(shape, tiny_pricing)
    # inner: 1000 input + 1000 output at tiny => 0.001 + 0.002 = 0.003
    # proposer: 1M * $10 + 0.5M * $30 = 10 + 15 = 25
    assert abs(est.inner_loop_usd - 0.003) < 1e-9
    assert abs(est.proposer_usd - 25.0) < 1e-9
    assert abs(est.total_usd - 25.003) < 1e-9


def test_unknown_model_uses_pessimistic_fallback(tiny_pricing):
    shape = RunShape(
        model="mystery-model-9000",
        iterations=1,
        candidates_per_iteration=1,
        eval_set_size=1,
        input_tokens_per_eval=1_000_000,   # 1 Mtok in
        output_tokens_per_eval=1_000_000,  # 1 Mtok out
    )
    est = estimate(shape, tiny_pricing)
    # fallback: $100/Mtok in, $300/Mtok out  => 100 + 300 = 400
    assert abs(est.total_usd - 400.0) < 1e-9


def test_zero_dims_produce_zero_cost(tiny_pricing):
    shape = RunShape(
        model="tiny-model",
        iterations=0,
        candidates_per_iteration=0,
        eval_set_size=0,
        input_tokens_per_eval=0,
        output_tokens_per_eval=0,
    )
    est = estimate(shape, tiny_pricing)
    assert est.total_usd == 0.0
    assert est.total_input_tokens == 0
