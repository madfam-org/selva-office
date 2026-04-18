"""Tests for the accounting workflow graph (contabilidad -- monthly close)."""

from __future__ import annotations

from unittest.mock import patch


class TestAccountingGraphStructure:
    """Accounting graph has correct nodes, edges, and conditional routing."""

    def test_graph_has_expected_nodes(self) -> None:
        from selva_workers.graphs.accounting import build_accounting_graph

        graph = build_accounting_graph()
        node_names = set(graph.nodes.keys())
        assert "fetch_period_data" in node_names
        assert "reconcile_bank" in node_names
        assert "compute_taxes" in node_names
        assert "prepare_declaration" in node_names
        assert "review_gate" in node_names

    def test_graph_compiles(self) -> None:
        from selva_workers.graphs.accounting import build_accounting_graph

        graph = build_accounting_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_accounting_state_fields(self) -> None:
        from selva_workers.graphs.accounting import AccountingState

        annotations = AccountingState.__annotations__
        assert "org_id" in annotations
        assert "period" in annotations
        assert "rfc" in annotations
        assert "regime" in annotations
        assert "transactions" in annotations
        assert "bank_statements" in annotations
        assert "pos_transactions" in annotations
        assert "payment_summary" in annotations
        assert "reconciliation" in annotations
        assert "tax_computation" in annotations
        assert "declaration_data" in annotations


class TestFetchPeriodData:
    """fetch_period_data() gathers data from Dhanam or falls back."""

    def test_requires_org_id_and_period(self) -> None:
        from selva_workers.graphs.accounting import fetch_period_data

        result = fetch_period_data({
            "messages": [],
            "org_id": "",
            "period": "",
        })
        assert result["status"] == "error"
        err = result["result"]["error"].lower()
        assert "org_id" in err or "period" in err

    def test_requires_period(self) -> None:
        from selva_workers.graphs.accounting import fetch_period_data

        result = fetch_period_data({
            "messages": [],
            "org_id": "org-1",
            "period": "",
        })
        assert result["status"] == "error"

    def test_fetches_without_dhanam(self) -> None:
        """Without DHANAM_API_URL, falls back to empty data."""
        from selva_workers.graphs.accounting import fetch_period_data

        result = fetch_period_data({
            "messages": [],
            "org_id": "org-1",
            "period": "2026-04",
            "rfc": "XAXX010101000",
        })
        assert result["status"] == "data_fetched"
        assert result["org_id"] == "org-1"
        assert result["period"] == "2026-04"
        assert result["transactions"] == []
        assert result["bank_statements"] == []
        assert result["pos_transactions"] == []
        assert len(result["messages"]) == 1
        assert "Period data fetched" in result["messages"][0].content

    def test_reads_from_workflow_variables(self) -> None:
        from selva_workers.graphs.accounting import fetch_period_data

        result = fetch_period_data({
            "messages": [],
            "workflow_variables": {
                "org_id": "from-vars",
                "period": "2026-03",
                "rfc": "RFC_VARS",
                "regime": "resico",
            },
        })
        assert result["status"] == "data_fetched"
        assert result["org_id"] == "from-vars"
        assert result["period"] == "2026-03"
        assert result["rfc"] == "RFC_VARS"
        assert result["regime"] == "resico"


class TestReconcileBank:
    """reconcile_bank() matches bank transactions against CFDIs."""

    def test_reconcile_without_karafiel(self) -> None:
        """Without KARAFIEL_API_URL, reconciliation has no CFDI data."""
        from selva_workers.graphs.accounting import reconcile_bank

        result = reconcile_bank({
            "messages": [],
            "rfc": "XAXX010101000",
            "period": "2026-04",
            "transactions": [
                {"id": "txn-1", "amount": "1000.00", "counterparty_rfc": ""},
            ],
            "status": "data_fetched",
        })
        assert result["status"] == "reconciled"
        assert result["reconciliation"]["total_bank_txns"] == 1
        assert result["reconciliation"]["total_cfdis"] == 0
        assert result["reconciliation"]["matched_count"] == 0
        assert result["reconciliation"]["unmatched_bank_count"] == 1

    def test_reconcile_skips_on_error(self) -> None:
        from selva_workers.graphs.accounting import reconcile_bank

        result = reconcile_bank({
            "messages": [],
            "status": "error",
        })
        assert result["status"] == "error"

    def test_reconcile_with_empty_transactions(self) -> None:
        from selva_workers.graphs.accounting import reconcile_bank

        result = reconcile_bank({
            "messages": [],
            "rfc": "",
            "period": "2026-04",
            "transactions": [],
            "status": "data_fetched",
        })
        assert result["status"] == "reconciled"
        assert result["reconciliation"]["total_bank_txns"] == 0
        assert result["reconciliation"]["matched_count"] == 0


class TestComputeTaxes:
    """compute_taxes() calculates ISR/IVA."""

    def test_compute_taxes_without_karafiel(self) -> None:
        """Without Karafiel, uses placeholder values."""
        from selva_workers.graphs.accounting import compute_taxes

        result = compute_taxes({
            "messages": [],
            "reconciliation": {
                "matched": [
                    {"bank_txn": {}, "cfdi": {"total": "5000.00"}},
                    {"bank_txn": {}, "cfdi": {"total": "3000.00"}},
                ],
            },
            "pos_transactions": [
                {"amount": "2000.00"},
            ],
            "payment_summary": {"total_income": "0", "by_method": {}},
            "regime": "pf",
            "status": "reconciled",
        })
        assert result["status"] == "taxes_computed"
        tax = result["tax_computation"]
        assert tax["total_income"] == 10000.0  # 5000 + 3000 + 2000
        assert tax["isr"]["details"].get("placeholder") is True
        content = result["messages"][0].content
        assert "ISR" in content.upper() or "isr" in content.lower()

    def test_compute_taxes_skips_on_error(self) -> None:
        from selva_workers.graphs.accounting import compute_taxes

        result = compute_taxes({
            "messages": [],
            "status": "error",
        })
        assert result["status"] == "error"

    def test_compute_taxes_uses_dhanam_income_when_higher(self) -> None:
        from selva_workers.graphs.accounting import compute_taxes

        result = compute_taxes({
            "messages": [],
            "reconciliation": {"matched": []},
            "pos_transactions": [],
            "payment_summary": {"total_income": "50000.00", "by_method": {}},
            "regime": "pm",
            "status": "reconciled",
        })
        assert result["tax_computation"]["total_income"] == 50000.0


class TestPrepareDeclaration:
    """prepare_declaration() builds ISR, IVA, and DIOT declarations."""

    def test_prepare_without_karafiel(self) -> None:
        """Without Karafiel, returns placeholder declarations."""
        from selva_workers.graphs.accounting import prepare_declaration

        result = prepare_declaration({
            "messages": [],
            "org_id": "org-1",
            "period": "2026-04",
            "tax_computation": {
                "total_income": 10000.0,
                "iva": {"tax_amount": "1600.00"},
                "payment_method_breakdown": {},
            },
            "reconciliation": {
                "matched": [
                    {
                        "bank_txn": {},
                        "cfdi": {"receptor_rfc": "RFC_A", "total": "5000.00"},
                    },
                    {
                        "bank_txn": {},
                        "cfdi": {"receptor_rfc": "RFC_B", "total": "3000.00"},
                    },
                ],
            },
            "status": "taxes_computed",
        })
        assert result["status"] == "declarations_prepared"
        decl = result["declaration_data"]
        assert "isr_provisional" in decl
        assert "iva_mensual" in decl
        assert "diot" in decl
        assert "Declarations prepared" in result["messages"][0].content

    def test_prepare_skips_on_error(self) -> None:
        from selva_workers.graphs.accounting import prepare_declaration

        result = prepare_declaration({
            "messages": [],
            "status": "error",
        })
        assert result["status"] == "error"

    def test_diot_groups_by_rfc(self) -> None:
        from selva_workers.graphs.accounting import prepare_declaration

        result = prepare_declaration({
            "messages": [],
            "org_id": "org-1",
            "period": "2026-04",
            "tax_computation": {
                "total_income": 0,
                "iva": {"tax_amount": "0"},
                "payment_method_breakdown": {},
            },
            "reconciliation": {
                "matched": [
                    {"bank_txn": {}, "cfdi": {"receptor_rfc": "SAME_RFC", "total": "1000.00"}},
                    {"bank_txn": {}, "cfdi": {"receptor_rfc": "SAME_RFC", "total": "2000.00"}},
                    {"bank_txn": {}, "cfdi": {"emisor_rfc": "OTHER_RFC", "total": "500.00"}},
                ],
            },
            "status": "taxes_computed",
        })
        diot = result["declaration_data"]["diot"]
        diot_data = diot.get("data", {})
        assert diot_data["domestic_count"] == 2  # SAME_RFC and OTHER_RFC


class TestReviewGate:
    """review_gate() uses interrupt for HITL approval."""

    def test_review_gate_skips_on_error(self) -> None:
        from selva_workers.graphs.accounting import review_gate

        result = review_gate({
            "messages": [],
            "status": "error",
        })
        assert result["status"] == "error"

    def test_review_gate_skips_on_blocked(self) -> None:
        from selva_workers.graphs.accounting import review_gate

        result = review_gate({
            "messages": [],
            "status": "blocked",
        })
        assert result["status"] == "blocked"

    def test_review_gate_approved(self) -> None:
        from selva_workers.graphs.accounting import review_gate

        with patch(
            "selva_workers.graphs.accounting.interrupt",
            return_value={"approved": True},
        ):
            result = review_gate({
                "messages": [],
                "period": "2026-04",
                "reconciliation": {"matched_count": 5},
                "tax_computation": {
                    "total_income": 10000,
                    "isr": {"tax_amount": "1000"},
                    "iva": {"tax_amount": "1600"},
                },
                "declaration_data": {"isr_provisional": {}, "iva_mensual": {}, "diot": {}},
                "status": "declarations_prepared",
            })

        assert result["status"] == "completed"
        assert result["result"]["approval"] == "approved"
        assert "approved" in result["messages"][0].content.lower()

    def test_review_gate_denied(self) -> None:
        from selva_workers.graphs.accounting import review_gate

        with patch(
            "selva_workers.graphs.accounting.interrupt",
            return_value={"approved": False, "feedback": "Fix reconciliation"},
        ):
            result = review_gate({
                "messages": [],
                "period": "2026-04",
                "reconciliation": {},
                "tax_computation": {},
                "declaration_data": {},
                "status": "declarations_prepared",
            })

        assert result["status"] == "denied"
        assert result["result"]["feedback"] == "Fix reconciliation"
        assert "denied" in result["messages"][0].content.lower()


class TestConditionalEdges:
    """Conditional edge routing functions."""

    def test_route_after_fetch_error_goes_to_end(self) -> None:
        from selva_workers.graphs.accounting import _route_after_fetch

        result = _route_after_fetch({"status": "error"})
        assert result == "__end__"

    def test_route_after_fetch_ok_goes_to_reconcile(self) -> None:
        from selva_workers.graphs.accounting import _route_after_fetch

        result = _route_after_fetch({"status": "data_fetched"})
        assert result == "reconcile_bank"


class TestAccountingRegistration:
    """Accounting graph is properly registered in the system."""

    def test_accounting_in_graph_builders(self) -> None:
        from selva_workers.__main__ import GRAPH_BUILDERS

        assert "accounting" in GRAPH_BUILDERS

    def test_accounting_timeout_configured(self) -> None:
        from selva_redis_pool.timeout import DEFAULT_TIMEOUTS

        assert "accounting" in DEFAULT_TIMEOUTS
        assert DEFAULT_TIMEOUTS["accounting"] == 600

    def test_accounting_builder_returns_graph(self) -> None:
        from selva_workers.graphs.accounting import build_accounting_graph

        graph = build_accounting_graph()
        assert graph is not None
        assert hasattr(graph, "nodes")


class TestPeriodToRange:
    """_period_to_range() helper converts YYYY-MM to date range."""

    def test_normal_month(self) -> None:
        from selva_workers.graphs.accounting import _period_to_range

        since, until = _period_to_range("2026-04")
        assert since == "2026-04-01"
        assert until == "2026-05-01"

    def test_december_wraps_year(self) -> None:
        from selva_workers.graphs.accounting import _period_to_range

        since, until = _period_to_range("2026-12")
        assert since == "2026-12-01"
        assert until == "2027-01-01"

    def test_january(self) -> None:
        from selva_workers.graphs.accounting import _period_to_range

        since, until = _period_to_range("2026-01")
        assert since == "2026-01-01"
        assert until == "2026-02-01"
