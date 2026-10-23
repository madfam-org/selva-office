"""Accounting source inspection; period calculations await verified source contracts."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from ..event_emitter import instrumented_node
from .base import BaseGraphState
from .base import run_async as _run_async

logger = logging.getLogger(__name__)


# -- State --------------------------------------------------------------------


class AccountingState(BaseGraphState, TypedDict, total=False):
    """Extended state for the accounting / contabilidad workflow.

    Separation of concerns:
    - Karafiel: ISR/IVA computation (fiscal module), CFDI validation, declarations
    - Dhanam: Transaction data, bank statements, payment summaries, POS data
    - Selva (this graph): Source coverage inspection; period calculations remain blocked
    """

    org_id: str
    period: str  # YYYY-MM
    rfc: str  # Emisor RFC for CFDI matching
    regime: str  # Fiscal regime (pf, pm, resico)
    transactions: list[dict[str, Any]]
    bank_statements: list[dict[str, Any]]
    pos_transactions: list[dict[str, Any]]
    payment_summary: dict[str, Any] | None
    reconciliation: dict[str, Any] | None
    tax_computation: dict[str, Any] | None
    declaration_data: dict[str, Any] | None
    source_coverage: dict[str, Any]
    transaction_read_proof: dict[str, Any] | None


# -- Helpers ------------------------------------------------------------------


def _period_to_range(period: str) -> tuple[str, str]:
    """Convert ``YYYY-MM`` to ``(since, until)`` ISO date strings."""
    year, month = period.split("-")
    since = f"{year}-{month}-01"
    m = int(month)
    until = f"{int(year) + 1}-01-01" if m == 12 else f"{year}-{m + 1:02d}-01"
    return since, until


# -- Node functions -----------------------------------------------------------


def _accounting_unavailable(
    state: AccountingState,
    reason: str,
    read_proof: dict[str, Any] | None = None,
) -> AccountingState:
    """Unproven input coverage cannot produce balances, taxes or a closed period."""
    return {
        **state,
        "messages": [
            *state.get("messages", []),
            AIMessage(
                content=(
                    "Accounting source coverage is unavailable. "
                    "No reconciliation, tax computation or declaration was completed."
                )
            ),
        ],
        "transactions": [],
        "bank_statements": [],
        "pos_transactions": [],
        "payment_summary": None,
        "reconciliation": None,
        "tax_computation": None,
        "declaration_data": None,
        "source_coverage": {"status": "unavailable", "reason": reason},
        "transaction_read_proof": read_proof,
        "status": "blocked",
        "result": {"error": reason},
    }


@instrumented_node
def fetch_period_data(state: AccountingState) -> AccountingState:
    """Gather a transaction read proof without implying full accounting coverage."""
    import os

    from madfam_inference.adapters.dhanam import DhanamAdapter
    from madfam_inference.adapters.financial_reads import CompleteTransactionRead

    payload = state.get("workflow_variables", {})
    org_id = state.get("org_id", "") or payload.get("org_id", "")
    period = state.get("period", "") or payload.get("period", "")
    if not org_id or not period or not os.environ.get("DHANAM_API_URL"):
        return _accounting_unavailable(state, "accounting_source_unconfigured")
    try:
        since, until = _period_to_range(period)
        read = _run_async(DhanamAdapter().list_transactions(org_id, since, until))
        if (
            not isinstance(read, CompleteTransactionRead)
            or read.proof.scope_id != org_id
            or read.proof.since != since
            or read.proof.until_exclusive != until
        ):
            raise ValueError("Missing period read proof")
    except Exception:
        logger.warning("Accounting transaction read unavailable or incomplete")
        return _accounting_unavailable(state, "accounting_transaction_read_unavailable")

    # A complete transaction response is only one input. The bank-statement,
    # POS, summary and authorized CFDI-history contracts remain unimplemented;
    # do not silently omit them or mistake a verified-empty response for close.
    return _accounting_unavailable(
        {**state, "org_id": org_id, "period": period},
        "accounting_source_contracts_unavailable",
        read.proof.model_dump(),
    )


@instrumented_node
def reconcile_bank(state: AccountingState) -> AccountingState:
    """No matching is available until scoped CFDI and statement reads are proven."""
    return _accounting_unavailable(state, "accounting_source_contracts_unavailable")


@instrumented_node
def compute_taxes(state: AccountingState) -> AccountingState:
    """Never calculate a period from absent, partial or caller-asserted coverage."""
    return _accounting_unavailable(state, "accounting_period_calculation_not_enabled")


@instrumented_node
def prepare_declaration(state: AccountingState) -> AccountingState:
    """Do not synthesize declarations from an unverified period calculation."""
    return _accounting_unavailable(state, "accounting_period_calculation_not_enabled")


@instrumented_node
def review_gate(state: AccountingState) -> AccountingState:
    """An approval cannot establish missing source coverage or close a period."""
    return _accounting_unavailable(state, "accounting_period_calculation_not_enabled")


# -- Conditional edge routing -------------------------------------------------


def _route_after_fetch(state: AccountingState) -> str:
    return "reconcile_bank" if state.get("status") == "data_fetched" else END


def _route_after_reconcile(state: AccountingState) -> str:
    return "compute_taxes" if state.get("status") == "reconciled" else END


def _route_after_compute(state: AccountingState) -> str:
    return "prepare_declaration" if state.get("status") == "taxes_computed" else END


def _route_after_prepare(state: AccountingState) -> str:
    return "review_gate" if state.get("status") == "declarations_prepared" else END


# -- Graph construction -------------------------------------------------------


def build_accounting_graph() -> StateGraph:
    """Construct the accounting workflow state graph.

    Flow::

        fetch_period_data --(unavailable coverage)--> END

    Downstream nodes remain registered for checkpoint compatibility and refuse
    period calculations until the complete input and fiscal contracts exist.
    """
    graph = StateGraph(AccountingState)

    graph.add_node("fetch_period_data", fetch_period_data)
    graph.add_node("reconcile_bank", reconcile_bank)
    graph.add_node("compute_taxes", compute_taxes)
    graph.add_node("prepare_declaration", prepare_declaration)
    graph.add_node("review_gate", review_gate)

    graph.add_edge(START, "fetch_period_data")
    graph.add_conditional_edges("fetch_period_data", _route_after_fetch)
    graph.add_conditional_edges("reconcile_bank", _route_after_reconcile)
    graph.add_conditional_edges("compute_taxes", _route_after_compute)
    graph.add_conditional_edges("prepare_declaration", _route_after_prepare)
    graph.add_edge("review_gate", END)

    return graph
