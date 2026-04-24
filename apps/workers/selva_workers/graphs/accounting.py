"""Accounting workflow graph -- monthly close, reconciliation, tax computation, declarations."""

from __future__ import annotations

import contextlib
import logging
from typing import Any, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

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
    - Selva (this graph): Monthly close orchestration, bank reconciliation matching
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


# -- Helpers ------------------------------------------------------------------


def _period_to_range(period: str) -> tuple[str, str]:
    """Convert ``YYYY-MM`` to ``(since, until)`` ISO date strings."""
    year, month = period.split("-")
    since = f"{year}-{month}-01"
    m = int(month)
    until = f"{int(year) + 1}-01-01" if m == 12 else f"{year}-{m + 1:02d}-01"
    return since, until


# -- Node functions -----------------------------------------------------------


@instrumented_node
def fetch_period_data(state: AccountingState) -> AccountingState:
    """Fetch transactions, bank statements, and POS data from Dhanam.

    Populates ``transactions``, ``bank_statements``, ``pos_transactions``,
    and ``payment_summary`` in state.  Falls back to empty data when
    Dhanam is unavailable.
    """
    messages = state.get("messages", [])
    payload = state.get("workflow_variables", {})

    org_id = state.get("org_id", "") or payload.get("org_id", "")
    period = state.get("period", "") or payload.get("period", "")
    rfc = state.get("rfc", "") or payload.get("rfc", "")
    regime = state.get("regime", "") or payload.get("regime", "pf")

    if not org_id or not period:
        error_msg = AIMessage(content="Accounting fetch failed: org_id and period are required.")
        return {
            **state,
            "messages": [*messages, error_msg],
            "status": "error",
            "result": {"error": "Missing org_id or period"},
        }

    since, until = _period_to_range(period)

    transactions: list[dict[str, Any]] = []
    bank_statements: list[dict[str, Any]] = []
    pos_transactions: list[dict[str, Any]] = []
    payment_summary: dict[str, Any] | None = None

    try:
        import os

        dhanam_url = os.environ.get("DHANAM_API_URL")
        if dhanam_url:
            from madfam_inference.adapters.dhanam import DhanamAdapter

            adapter = DhanamAdapter()
            txns = _run_async(adapter.list_transactions(org_id, since, until))
            transactions = [t.model_dump() for t in txns]

            stmts = _run_async(adapter.get_bank_statements(org_id))
            bank_statements = [s.model_dump() for s in stmts]

            pos = _run_async(adapter.get_pos_transactions(org_id, since, until))
            pos_transactions = [t.model_dump() for t in pos]

            summary = _run_async(adapter.get_payment_summary(org_id, period))
            payment_summary = summary.model_dump()
        else:
            raise RuntimeError("DHANAM_API_URL not set")
    except Exception:
        logger.debug("Dhanam adapter unavailable; proceeding with empty transaction data")

    fetch_msg = AIMessage(
        content=(
            f"Period data fetched for {period}: {len(transactions)} transactions, "
            f"{len(bank_statements)} bank accounts, {len(pos_transactions)} POS transactions."
        ),
        additional_kwargs={
            "action_category": "api_call",
            "accounting_context": {
                "org_id": org_id,
                "period": period,
                "transaction_count": len(transactions),
                "bank_account_count": len(bank_statements),
                "pos_count": len(pos_transactions),
            },
        },
    )

    return {
        **state,
        "messages": [*messages, fetch_msg],
        "org_id": org_id,
        "period": period,
        "rfc": rfc,
        "regime": regime,
        "transactions": transactions,
        "bank_statements": bank_statements,
        "pos_transactions": pos_transactions,
        "payment_summary": payment_summary,
        "status": "data_fetched",
    }


@instrumented_node
def reconcile_bank(state: AccountingState) -> AccountingState:
    """Match bank transactions against CFDIs for the period.

    This is Selva orchestration logic (matching), not Karafiel compliance.
    Fetches CFDIs from Karafiel, then matches by amount + counterparty RFC.
    """
    messages = state.get("messages", [])

    if state.get("status") in ("error", "blocked"):
        return state

    rfc = state.get("rfc", "")
    period = state.get("period", "")
    transactions = state.get("transactions", [])

    # Fetch CFDIs from Karafiel for matching.
    cfdis: list[dict[str, Any]] = []
    if rfc and period:
        try:
            import os

            karafiel_url = os.environ.get("KARAFIEL_API_URL")
            if karafiel_url:
                from madfam_inference.adapters.karafiel import KarafielAdapter

                since, until = _period_to_range(period)
                adapter = KarafielAdapter()
                cfdi_items = _run_async(adapter.list_cfdis(rfc, since, until))
                cfdis = [c.model_dump() for c in cfdi_items]
            else:
                raise RuntimeError("KARAFIEL_API_URL not set")
        except Exception:
            logger.debug("Karafiel CFDI listing unavailable; reconciliation partial")

    # Match bank transactions to CFDIs by amount + counterparty RFC.
    matched: list[dict[str, Any]] = []
    unmatched_cfdi_indices: set[int] = set(range(len(cfdis)))

    for txn in transactions:
        txn_amount = txn.get("amount", "")
        txn_rfc = txn.get("counterparty_rfc", "")
        found_match = False

        for idx in list(unmatched_cfdi_indices):
            cfdi = cfdis[idx]
            if cfdi.get("total") == txn_amount and (
                not txn_rfc
                or cfdi.get("receptor_rfc") == txn_rfc
                or cfdi.get("emisor_rfc") == txn_rfc
            ):
                matched.append({"bank_txn": txn, "cfdi": cfdi})
                unmatched_cfdi_indices.discard(idx)
                found_match = True
                break

        if not found_match:
            matched.append({"bank_txn": txn, "cfdi": None})

    unmatched_cfdis = [cfdis[i] for i in sorted(unmatched_cfdi_indices)]
    unmatched_bank = [m["bank_txn"] for m in matched if m["cfdi"] is None]
    fully_matched = [m for m in matched if m["cfdi"] is not None]

    reconciliation = {
        "period": period,
        "total_bank_txns": len(transactions),
        "total_cfdis": len(cfdis),
        "matched_count": len(fully_matched),
        "unmatched_bank_count": len(unmatched_bank),
        "unmatched_cfdi_count": len(unmatched_cfdis),
        "matched": fully_matched,
        "unmatched_bank": unmatched_bank,
        "unmatched_cfdis": unmatched_cfdis,
    }

    recon_msg = AIMessage(
        content=(
            f"Bank reconciliation for {period}: {len(fully_matched)} matched, "
            f"{len(unmatched_bank)} unmatched bank transactions, "
            f"{len(unmatched_cfdis)} unmatched CFDIs."
        ),
        additional_kwargs={
            "action_category": "api_call",
            "reconciliation_summary": {
                "matched": len(fully_matched),
                "unmatched_bank": len(unmatched_bank),
                "unmatched_cfdis": len(unmatched_cfdis),
            },
        },
    )

    return {
        **state,
        "messages": [*messages, recon_msg],
        "reconciliation": reconciliation,
        "status": "reconciled",
    }


@instrumented_node
def compute_taxes(state: AccountingState) -> AccountingState:
    """Compute ISR and IVA via Karafiel's fiscal module.

    Sums income from matched transactions and POS data, then calls
    Karafiel for ISR provisional and IVA computation.
    """
    messages = state.get("messages", [])

    if state.get("status") in ("error", "blocked"):
        return state

    reconciliation = state.get("reconciliation") or {}
    pos_transactions = state.get("pos_transactions", [])
    payment_summary = state.get("payment_summary") or {}
    regime = state.get("regime", "pf")

    # Calculate total income from reconciliation + POS.
    total_income = 0.0
    matched = reconciliation.get("matched", [])
    for pair in matched:
        cfdi = pair.get("cfdi") or {}
        with contextlib.suppress(ValueError, TypeError):
            total_income += float(cfdi.get("total", "0"))

    for pos_txn in pos_transactions:
        with contextlib.suppress(ValueError, TypeError):
            total_income += float(pos_txn.get("amount", "0"))

    # Also incorporate Dhanam payment summary income if available.
    try:
        dhanam_income = float(payment_summary.get("total_income", "0"))
        if dhanam_income > total_income:
            total_income = dhanam_income
    except (ValueError, TypeError):
        pass

    isr_result: dict[str, Any] = {}
    iva_result: dict[str, Any] = {}

    try:
        import os

        karafiel_url = os.environ.get("KARAFIEL_API_URL")
        if karafiel_url:
            from madfam_inference.adapters.karafiel import KarafielAdapter

            adapter = KarafielAdapter()
            isr = _run_async(
                adapter.compute_isr(income=total_income, period="monthly", regime=regime)
            )
            isr_result = isr.model_dump()

            iva = _run_async(adapter.compute_iva(amount=total_income, rate=0.16))
            iva_result = iva.model_dump()
        else:
            raise RuntimeError("KARAFIEL_API_URL not set")
    except Exception:
        logger.debug("Karafiel tax computation unavailable; using placeholder values")
        isr_result = {
            "tax_type": "isr",
            "base_amount": str(total_income),
            "tax_amount": "0.00",
            "rate": "0.00",
            "details": {"placeholder": True},
        }
        iva_result = {
            "tax_type": "iva",
            "base_amount": str(total_income),
            "tax_amount": str(round(total_income * 0.16, 2)),
            "rate": "0.16",
            "details": {"placeholder": True},
        }

    tax_computation = {
        "total_income": total_income,
        "regime": regime,
        "isr": isr_result,
        "iva": iva_result,
        "payment_method_breakdown": payment_summary.get("by_method", {}),
    }

    tax_msg = AIMessage(
        content=(
            f"Taxes computed: income={total_income:.2f} MXN, "
            f"ISR={isr_result.get('tax_amount', 'N/A')}, "
            f"IVA={iva_result.get('tax_amount', 'N/A')}."
        ),
        additional_kwargs={
            "action_category": "api_call",
            "tax_computation": {
                "income": total_income,
                "isr": isr_result.get("tax_amount"),
                "iva": iva_result.get("tax_amount"),
            },
        },
    )

    return {
        **state,
        "messages": [*messages, tax_msg],
        "tax_computation": tax_computation,
        "status": "taxes_computed",
    }


@instrumented_node
def prepare_declaration(state: AccountingState) -> AccountingState:
    """Prepare monthly declaration data via Karafiel.

    Builds ISR provisional + IVA monthly declaration. Includes payment method
    breakdown for DIOT (domestic transactions, foreign transactions, by RFC).
    """
    messages = state.get("messages", [])

    if state.get("status") in ("error", "blocked"):
        return state

    org_id = state.get("org_id", "")
    period = state.get("period", "")
    tax_computation = state.get("tax_computation") or {}
    reconciliation = state.get("reconciliation") or {}

    total_income = tax_computation.get("total_income", 0.0)
    by_method = tax_computation.get("payment_method_breakdown", {})

    # Build DIOT data from reconciliation (transactions grouped by RFC).
    diot_by_rfc: dict[str, float] = {}
    for pair in reconciliation.get("matched", []):
        cfdi = pair.get("cfdi") or {}
        rfc = cfdi.get("receptor_rfc") or cfdi.get("emisor_rfc") or ""
        if rfc:
            with contextlib.suppress(ValueError, TypeError):
                diot_by_rfc[rfc] = diot_by_rfc.get(rfc, 0.0) + float(cfdi.get("total", "0"))

    diot_data = {
        "by_rfc": diot_by_rfc,
        "by_payment_method": by_method,
        "domestic_count": len(diot_by_rfc),
    }

    declaration_data: dict[str, Any] = {}

    try:
        import os

        karafiel_url = os.environ.get("KARAFIEL_API_URL")
        if karafiel_url:
            from madfam_inference.adapters.karafiel import KarafielAdapter

            adapter = KarafielAdapter()

            # ISR provisional declaration.
            isr_decl = _run_async(
                adapter.build_declaration(
                    org_id=org_id,
                    period=period,
                    declaration_type="isr_provisional",
                    income=total_income,
                )
            )

            # IVA monthly declaration.
            iva_decl = _run_async(
                adapter.build_declaration(
                    org_id=org_id,
                    period=period,
                    declaration_type="iva_mensual",
                    iva_trasladado=float(tax_computation.get("iva", {}).get("tax_amount", "0")),
                )
            )

            # DIOT.
            diot_decl = _run_async(
                adapter.build_declaration(
                    org_id=org_id,
                    period=period,
                    declaration_type="diot",
                    diot_data=diot_data,
                )
            )

            declaration_data = {
                "isr_provisional": isr_decl.model_dump(),
                "iva_mensual": iva_decl.model_dump(),
                "diot": diot_decl.model_dump(),
            }
        else:
            raise RuntimeError("KARAFIEL_API_URL not set")
    except Exception:
        logger.debug("Karafiel declaration build unavailable; using placeholder data")
        declaration_data = {
            "isr_provisional": {
                "declaration_type": "isr_provisional",
                "period": period,
                "status": "placeholder",
                "data": {"income": total_income},
            },
            "iva_mensual": {
                "declaration_type": "iva_mensual",
                "period": period,
                "status": "placeholder",
                "data": {},
            },
            "diot": {
                "declaration_type": "diot",
                "period": period,
                "status": "placeholder",
                "data": diot_data,
            },
        }

    decl_msg = AIMessage(
        content=(
            f"Declarations prepared for {period}: ISR provisional, IVA mensual, DIOT. "
            f"DIOT includes {len(diot_by_rfc)} counterparties."
        ),
        additional_kwargs={
            "action_category": "api_call",
            "declaration_summary": {
                "types": list(declaration_data.keys()),
                "diot_counterparties": len(diot_by_rfc),
            },
        },
    )

    return {
        **state,
        "messages": [*messages, decl_msg],
        "declaration_data": declaration_data,
        "status": "declarations_prepared",
    }


@instrumented_node
def review_gate(state: AccountingState) -> AccountingState:
    """HITL approval before filing declarations.

    Uses LangGraph's ``interrupt()`` to pause for human review.
    Shows: reconciliation summary, tax amounts, declaration preview.
    """
    if state.get("status") in ("error", "blocked"):
        return state

    period = state.get("period", "")
    reconciliation = state.get("reconciliation") or {}
    tax_computation = state.get("tax_computation") or {}
    declaration_data = state.get("declaration_data") or {}

    approval_context = {
        "action": "file_declarations",
        "action_category": "api_call",
        "period": period,
        "reconciliation_summary": {
            "matched": reconciliation.get("matched_count", 0),
            "unmatched_bank": reconciliation.get("unmatched_bank_count", 0),
            "unmatched_cfdis": reconciliation.get("unmatched_cfdi_count", 0),
        },
        "tax_amounts": {
            "income": tax_computation.get("total_income", 0),
            "isr": tax_computation.get("isr", {}).get("tax_amount", "N/A"),
            "iva": tax_computation.get("iva", {}).get("tax_amount", "N/A"),
        },
        "declaration_types": list(declaration_data.keys()),
        "reasoning": (
            f"Monthly close for {period} ready for review. "
            f"Please verify reconciliation, tax amounts, and declaration data "
            f"before filing with the SAT."
        ),
    }

    decision = interrupt(approval_context)

    messages = state.get("messages", [])

    if decision.get("approved", False):
        approve_msg = AIMessage(
            content=f"Monthly close for {period} approved. Declarations ready for filing.",
            additional_kwargs={"action_category": "api_call"},
        )
        return {
            **state,
            "messages": [*messages, approve_msg],
            "status": "completed",
            "result": {
                "period": period,
                "reconciliation": reconciliation,
                "tax_computation": tax_computation,
                "declaration_data": declaration_data,
                "approval": "approved",
            },
        }

    feedback = decision.get("feedback", "No feedback provided")
    deny_msg = AIMessage(
        content=f"Monthly close for {period} denied. Feedback: {feedback}",
        additional_kwargs={"action_category": "api_call"},
    )
    return {
        **state,
        "messages": [*messages, deny_msg],
        "status": "denied",
        "result": {
            "period": period,
            "approval": "denied",
            "feedback": feedback,
        },
    }


# -- Conditional edge routing -------------------------------------------------


def _route_after_fetch(state: AccountingState) -> str:
    """Route to END on error, otherwise continue to reconcile_bank."""
    if state.get("status") == "error":
        return END
    return "reconcile_bank"


# -- Graph construction -------------------------------------------------------


def build_accounting_graph() -> StateGraph:
    """Construct the accounting workflow state graph.

    Flow::

        fetch_period_data --(error)--> END
                          \\--> reconcile_bank -> compute_taxes
                                -> prepare_declaration -> review_gate (interrupt) -> END
    """
    graph = StateGraph(AccountingState)

    graph.add_node("fetch_period_data", fetch_period_data)
    graph.add_node("reconcile_bank", reconcile_bank)
    graph.add_node("compute_taxes", compute_taxes)
    graph.add_node("prepare_declaration", prepare_declaration)
    graph.add_node("review_gate", review_gate)

    graph.add_edge(START, "fetch_period_data")
    graph.add_conditional_edges("fetch_period_data", _route_after_fetch)
    graph.add_edge("reconcile_bank", "compute_taxes")
    graph.add_edge("compute_taxes", "prepare_declaration")
    graph.add_edge("prepare_declaration", "review_gate")
    graph.add_edge("review_gate", END)

    return graph
