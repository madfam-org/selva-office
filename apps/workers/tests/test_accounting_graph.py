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


class TestAccountingCoverageBoundary:
    def test_unconfigured_source_blocks_before_reads(self, monkeypatch):
        from selva_workers.graphs.accounting import fetch_period_data

        monkeypatch.delenv("DHANAM_API_URL", raising=False)
        with patch("madfam_inference.adapters.dhanam.DhanamAdapter") as adapter:
            result = fetch_period_data(
                {"messages": [], "org_id": "synthetic-space", "period": "2026-04"}
            )
        adapter.assert_not_called()
        assert result["status"] == "blocked"
        assert result["source_coverage"]["status"] == "unavailable"
        assert result["transaction_read_proof"] is None

    def test_failed_or_legacy_list_reads_are_not_complete(self, caplog):
        from selva_workers.graphs.accounting import fetch_period_data

        for returned in ([], {}, {"data": [], "total": 0}):
            with (
                patch.dict("os.environ", {"DHANAM_API_URL": "https://example.invalid"}),
                patch("madfam_inference.adapters.dhanam.DhanamAdapter") as adapter,
                patch("selva_workers.graphs.accounting._run_async", side_effect=lambda x: x),
            ):
                adapter.return_value.list_transactions.return_value = returned
                result = fetch_period_data(
                    {"messages": [], "org_id": "synthetic-space", "period": "2026-04"}
                )
            assert result["status"] == "blocked"
            assert result["transaction_read_proof"] is None

        with (
            patch.dict("os.environ", {"DHANAM_API_URL": "https://example.invalid"}),
            patch("madfam_inference.adapters.dhanam.DhanamAdapter") as adapter,
        ):
            adapter.return_value.list_transactions.side_effect = RuntimeError("SENSITIVE_SENTINEL")
            result = fetch_period_data(
                {"messages": [], "org_id": "synthetic-space", "period": "2026-04"}
            )
        assert result["status"] == "blocked"
        assert "SENSITIVE_SENTINEL" not in str(result) + caplog.text

    def test_verified_empty_transactions_do_not_establish_full_period_coverage(self):
        from madfam_inference.adapters.financial_reads import (
            CompleteTransactionRead,
            TransactionReadProof,
        )
        from selva_workers.graphs.accounting import build_accounting_graph

        read = CompleteTransactionRead(
            items=[],
            proof=TransactionReadProof(
                scope_id="synthetic-space",
                since="2026-04-01",
                until_exclusive="2026-05-01",
                total=0,
                pages_read=1,
                page_size=100,
            ),
        )
        with (
            patch.dict("os.environ", {"DHANAM_API_URL": "https://example.invalid"}),
            patch("madfam_inference.adapters.dhanam.DhanamAdapter") as adapter,
            patch("selva_workers.graphs.accounting._run_async", side_effect=lambda x: x),
            patch("madfam_inference.adapters.karafiel.KarafielAdapter") as fiscal,
        ):
            adapter.return_value.list_transactions.return_value = read
            result = (
                build_accounting_graph()
                .compile()
                .invoke(
                    {
                        "messages": [],
                        "org_id": "synthetic-space",
                        "period": "2026-04",
                    }
                )
            )
        fiscal.assert_not_called()
        assert result["transaction_read_proof"]["total"] == 0
        assert result["transaction_read_proof"]["status"] == "complete"
        assert result["source_coverage"]["status"] == "unavailable"
        assert result["status"] == "blocked"
        assert result["tax_computation"] is None
        assert result["declaration_data"] is None

    def test_resumed_nodes_cannot_calculate_or_close_from_asserted_coverage(self):
        from selva_workers.graphs.accounting import (
            compute_taxes,
            prepare_declaration,
            reconcile_bank,
            review_gate,
        )

        with patch("madfam_inference.adapters.karafiel.KarafielAdapter") as adapter:
            for node in (reconcile_bank, compute_taxes, prepare_declaration, review_gate):
                result = node(
                    {
                        "messages": [],
                        "status": "reconciled",
                        "approved": True,
                        "source_coverage": {"status": "complete"},
                        "transactions": [],
                        "tax_computation": {"total_income": 0},
                    }
                )
                assert result["status"] == "blocked"
                assert result["tax_computation"] is None
                assert result["declaration_data"] is None
        adapter.assert_not_called()

    def test_unknown_status_stops_every_edge(self):
        from selva_workers.graphs.accounting import (
            _route_after_compute,
            _route_after_fetch,
            _route_after_prepare,
            _route_after_reconcile,
        )

        for edge in (
            _route_after_fetch,
            _route_after_reconcile,
            _route_after_compute,
            _route_after_prepare,
        ):
            for status in (None, "blocked", "error", "unknown"):
                assert edge({"status": status}) == "__end__"


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
