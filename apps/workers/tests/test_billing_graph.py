"""Tests for the billing workflow graph (CFDI 4.0 via Karafiel)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestBillingGraphStructure:
    """Billing graph has correct nodes, edges, and conditional routing."""

    def test_graph_has_expected_nodes(self) -> None:
        from selva_workers.graphs.billing import build_billing_graph

        graph = build_billing_graph()
        node_names = set(graph.nodes.keys())
        assert "fetch_context" in node_names
        assert "validate_rfcs" in node_names
        assert "check_blacklist" in node_names
        assert "generate_cfdi" in node_names
        assert "stamp_cfdi" in node_names
        assert "notify_customer" in node_names

    def test_graph_compiles(self) -> None:
        from selva_workers.graphs.billing import build_billing_graph

        graph = build_billing_graph()
        compiled = graph.compile()
        assert compiled is not None

    def test_billing_state_fields(self) -> None:
        from selva_workers.graphs.billing import BillingState

        annotations = BillingState.__annotations__
        assert "emisor_rfc" in annotations
        assert "receptor_rfc" in annotations
        assert "conceptos" in annotations
        assert "cfdi_xml" in annotations
        assert "cfdi_uuid" in annotations
        assert "stamp_result" in annotations
        assert "customer_phone" in annotations
        assert "customer_email" in annotations


class TestFetchContext:
    """fetch_context() gathers billing data from adapters or state."""

    def test_fetch_context_populates_state(self) -> None:
        from selva_workers.graphs.billing import fetch_context

        result = fetch_context(
            {
                "messages": [],
                "emisor_rfc": "XAXX010101000",
                "receptor_rfc": "XEXX010101000",
                "conceptos": [{"descripcion": "Servicio", "importe": 1000}],
                "customer_email": "test@example.com",
            }
        )

        assert result["status"] == "fetching_context"
        assert result["emisor_rfc"] == "XAXX010101000"
        assert result["receptor_rfc"] == "XEXX010101000"
        assert len(result["conceptos"]) == 1
        assert result["customer_email"] == "test@example.com"
        assert len(result["messages"]) == 1
        assert "Billing context fetched" in result["messages"][0].content

    def test_fetch_context_reads_from_workflow_variables(self) -> None:
        from selva_workers.graphs.billing import fetch_context

        result = fetch_context(
            {
                "messages": [],
                "workflow_variables": {
                    "emisor_rfc": "FROM_VARS",
                    "receptor_rfc": "FROM_VARS_R",
                    "conceptos": [{"desc": "item"}],
                },
            }
        )

        assert result["emisor_rfc"] == "FROM_VARS"
        assert result["receptor_rfc"] == "FROM_VARS_R"
        assert len(result["conceptos"]) == 1

    def test_fetch_context_without_adapters(self) -> None:
        """Without DHANAM or PHYND env vars, falls back to state values."""
        from selva_workers.graphs.billing import fetch_context

        result = fetch_context(
            {
                "messages": [],
                "emisor_rfc": "AAA010101AAA",
                "receptor_rfc": "BBB020202BBB",
                "conceptos": [],
            }
        )

        assert result["status"] == "fetching_context"
        assert result["emisor_rfc"] == "AAA010101AAA"


class TestValidateRfcs:
    """validate_rfcs() blocks on invalid or missing RFCs."""

    def test_validate_rfcs_blocks_on_empty_emisor(self) -> None:
        from selva_workers.graphs.billing import validate_rfcs

        result = validate_rfcs(
            {
                "messages": [],
                "emisor_rfc": "",
                "receptor_rfc": "XEXX010101000",
            }
        )

        assert result["status"] == "error"
        assert "Missing" in result["result"]["error"]

    def test_validate_rfcs_blocks_on_empty_receptor(self) -> None:
        from selva_workers.graphs.billing import validate_rfcs

        result = validate_rfcs(
            {
                "messages": [],
                "emisor_rfc": "XAXX010101000",
                "receptor_rfc": "",
            }
        )

        assert result["status"] == "error"

    def test_validate_rfcs_passes_without_karafiel(self) -> None:
        """Without KARAFIEL_API_URL, validation is skipped (passes)."""
        from selva_workers.graphs.billing import validate_rfcs

        result = validate_rfcs(
            {
                "messages": [],
                "emisor_rfc": "XAXX010101000",
                "receptor_rfc": "XEXX010101000",
            }
        )

        assert result["status"] == "rfcs_validated"
        assert len(result["messages"]) == 1
        assert "validated" in result["messages"][0].content.lower()

    def test_validate_rfcs_blocks_on_invalid_emisor_with_karafiel(self) -> None:
        import sys

        from selva_workers.graphs.billing import validate_rfcs

        mock_adapter_instance = MagicMock()
        mock_adapter_instance.validate_rfc.return_value = False

        mock_module = MagicMock()
        mock_module.KarafielAdapter.return_value = mock_adapter_instance

        with (
            patch.dict("os.environ", {"KARAFIEL_API_URL": "http://fake-karafiel:8080"}),
            patch.dict(sys.modules, {"madfam_inference.adapters.karafiel": mock_module}),
            patch("selva_workers.graphs.billing._run_async", side_effect=lambda x: x),
        ):
            result = validate_rfcs(
                {
                    "messages": [],
                    "emisor_rfc": "INVALID",
                    "receptor_rfc": "XEXX010101000",
                }
            )

        assert result["status"] == "error"
        assert "Invalid emisor RFC" in result["result"]["error"]


class TestCheckBlacklist:
    """Only a complete, explicitly unlisted response can reach generation."""

    def test_blacklist_stops_without_karafiel(self, monkeypatch) -> None:
        from selva_workers.graphs.billing import check_blacklist

        monkeypatch.delenv("KARAFIEL_API_URL", raising=False)
        result = check_blacklist({"messages": [], "receptor_rfc": "XEXX010101000"})
        assert result["status"] == "error"
        assert "unknown" in result["messages"][0].content

    def test_blacklist_blocks_listed_rfc(self) -> None:
        from madfam_inference.adapters.karafiel import BlacklistResult

        result = self._check(
            BlacklistResult(
                rfc="XEXX010101000",
                listed=True,
                article_69b=True,
                definitive=False,
                check_status="checked",
            )
        )
        assert result["status"] == "blocked"
        assert "69-B" in result["messages"][0].content

    def test_blacklist_clear_continues(self) -> None:
        from madfam_inference.adapters.karafiel import BlacklistResult

        result = self._check(
            BlacklistResult(
                rfc="XEXX010101000",
                listed=False,
                article_69b=False,
                definitive=False,
                check_status="checked",
            )
        )
        assert result["status"] == "blacklist_clear"

    def test_unknown_malformed_or_wrong_subject_stops(self) -> None:
        from madfam_inference.adapters.karafiel import BlacklistResult
        from selva_workers.graphs.billing import _route_after_blacklist

        for screening in (
            False,
            True,
            None,
            {},
            BlacklistResult(rfc="XEXX010101000"),
            BlacklistResult(rfc="XEXX010101000", listed=False),
            BlacklistResult(
                rfc="XAXX010101000",
                listed=False,
                article_69b=False,
                definitive=False,
                check_status="checked",
            ),
        ):
            result = self._check(screening)
            assert result["status"] == "error"
            assert _route_after_blacklist(result) == "__end__"
            assert "XEXX010101000" not in result["messages"][0].content

    def test_unavailable_source_does_not_leak_error(self, caplog) -> None:
        from selva_workers.graphs.billing import check_blacklist

        with (
            patch.dict("os.environ", {"KARAFIEL_API_URL": "https://example.invalid"}),
            patch("madfam_inference.adapters.karafiel.KarafielAdapter") as adapter,
        ):
            adapter.return_value.check_blacklist.side_effect = RuntimeError("SENSITIVE_SENTINEL")
            result = check_blacklist({"messages": [], "receptor_rfc": "XEXX010101000"})
        assert result["status"] == "error"
        assert "SENSITIVE_SENTINEL" not in str(result) + caplog.text

    def _check(self, screening):
        from selva_workers.graphs.billing import check_blacklist

        with (
            patch.dict("os.environ", {"KARAFIEL_API_URL": "https://example.invalid"}),
            patch("madfam_inference.adapters.karafiel.KarafielAdapter") as adapter,
            patch("selva_workers.graphs.billing._run_async", side_effect=lambda x: x),
        ):
            adapter.return_value.check_blacklist.return_value = screening
            return check_blacklist({"messages": [], "receptor_rfc": "XEXX010101000"})


class TestFiscalExecutionDisabled:
    """Legacy graph execution cannot produce or send synthetic fiscal evidence."""

    def test_all_fiscal_nodes_refuse_even_with_configuration_and_agent_approval(self):
        from selva_workers.graphs.billing import generate_cfdi, notify_customer, stamp_cfdi

        for node in (generate_cfdi, stamp_cfdi, notify_customer):
            with (
                patch.dict(
                    "os.environ",
                    {
                        "KARAFIEL_API_URL": "https://example.invalid",
                        "SMTP_HOST": "example.invalid",
                        "WHATSAPP_API_URL": "https://example.invalid",
                    },
                ),
                patch("madfam_inference.adapters.karafiel.KarafielAdapter") as adapter,
                patch("selva_workers.graphs.billing._run_async") as run_async,
            ):
                result = node(
                    {
                        "messages": [],
                        "status": "stamped",
                        "approved": True,
                        "cfdi_xml": "<synthetic/>",
                        "cfdi_uuid": "synthetic-folio",
                        "stamp_result": {"folio_fiscal": "synthetic-folio"},
                        "customer_email": "test@example.invalid",
                        "customer_phone": "SYNTHETIC_PHONE",
                    }
                )
            assert result["status"] == "blocked"
            assert result["result"] == {"error": "fiscal_execution_not_enabled"}
            assert result["cfdi_xml"] is None
            assert result["cfdi_uuid"] is None
            assert result["stamp_result"] is None
            adapter.assert_not_called()
            run_async.assert_not_called()
            assert "customer_email" not in result["messages"][0].content

    def test_unconfigured_nodes_do_not_create_placeholders(self, monkeypatch):
        from selva_workers.graphs.billing import generate_cfdi, notify_customer, stamp_cfdi

        monkeypatch.delenv("KARAFIEL_API_URL", raising=False)
        for node in (generate_cfdi, stamp_cfdi, notify_customer):
            result = node({"messages": [], "task_id": "synthetic-task"})
            assert result["status"] == "blocked"
            assert result["cfdi_uuid"] is None
            assert result["stamp_result"] is None

    def test_failed_generation_and_stamp_do_not_reach_following_nodes(self):
        from selva_workers.graphs.billing import _route_after_generate, _route_after_stamp

        for status in (None, "blocked", "error", "unknown", "pending"):
            assert _route_after_generate({"status": status}) == "__end__"
            assert _route_after_stamp({"status": status}) == "__end__"

    def test_compiled_graph_stops_after_disabled_generation(self):
        from langgraph.graph import START

        from madfam_inference.adapters.karafiel import BlacklistResult
        from selva_workers.graphs.billing import build_billing_graph

        with (
            patch.dict("os.environ", {"KARAFIEL_API_URL": "https://example.invalid"}),
            patch("madfam_inference.adapters.karafiel.KarafielAdapter") as adapter,
            patch("selva_workers.graphs.billing._run_async", side_effect=lambda x: x),
        ):
            adapter.return_value.check_blacklist.return_value = BlacklistResult(
                rfc="XEXX010101000",
                listed=False,
                article_69b=False,
                definitive=False,
                check_status="checked",
            )
            # Enter at screening to avoid unrelated ledger/customer lookups.
            graph = build_billing_graph()
            graph.edges.discard((START, "fetch_context"))
            graph.add_edge(START, "check_blacklist")
            result = graph.compile().invoke({"messages": [], "receptor_rfc": "XEXX010101000"})
            adapter.return_value.generate_cfdi.assert_not_called()
            adapter.return_value.stamp_cfdi.assert_not_called()
        assert result["status"] == "blocked"
        assert result["stamp_result"] is None


class TestConditionalEdges:
    """Conditional edge routing functions."""

    def test_route_after_validate_error_goes_to_end(self) -> None:
        from selva_workers.graphs.billing import _route_after_validate

        result = _route_after_validate({"status": "error"})
        assert result == "__end__"

    def test_route_after_validate_ok_goes_to_blacklist(self) -> None:
        from selva_workers.graphs.billing import _route_after_validate

        result = _route_after_validate({"status": "rfcs_validated"})
        assert result == "check_blacklist"

    def test_route_after_blacklist_blocked_goes_to_end(self) -> None:
        from selva_workers.graphs.billing import _route_after_blacklist

        result = _route_after_blacklist({"status": "blocked"})
        assert result == "__end__"

    def test_route_after_blacklist_clear_goes_to_generate(self) -> None:
        from selva_workers.graphs.billing import _route_after_blacklist

        result = _route_after_blacklist({"status": "blacklist_clear"})
        assert result == "generate_cfdi"


class TestBillingRegistration:
    """Billing graph is properly registered in the system."""

    def test_billing_in_graph_builders(self) -> None:
        from selva_workers.__main__ import GRAPH_BUILDERS

        assert "billing" in GRAPH_BUILDERS

    def test_billing_timeout_configured(self) -> None:
        from selva_redis_pool.timeout import DEFAULT_TIMEOUTS

        assert "billing" in DEFAULT_TIMEOUTS
        assert DEFAULT_TIMEOUTS["billing"] == 300

    def test_billing_builder_returns_graph(self) -> None:
        from selva_workers.graphs.billing import build_billing_graph

        graph = build_billing_graph()
        assert graph is not None
        assert hasattr(graph, "nodes")
