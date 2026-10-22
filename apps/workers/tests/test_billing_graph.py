"""Tests for the billing workflow graph (CFDI 4.0 via Karafiel)."""

from __future__ import annotations

from unittest.mock import AsyncMock, call, patch

import pytest


@pytest.fixture(autouse=True)
def isolated_graph_io(monkeypatch):
    """No graph test may emit events or use ambient adapter configuration."""
    for key in ("DHANAM_API_URL", "PHYND_CRM_URL", "KARAFIEL_API_URL", "KARAFIEL_API_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    with patch("selva_workers.event_emitter.emit_event", new_callable=AsyncMock):
        yield


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

    @pytest.mark.parametrize("missing", ["KARAFIEL_API_URL", "KARAFIEL_API_TOKEN"])
    def test_unconfigured_validation_is_unavailable(self, missing, monkeypatch):
        from selva_workers.graphs.billing import validate_rfcs

        monkeypatch.setenv("KARAFIEL_API_URL", "https://example.invalid")
        monkeypatch.setenv("KARAFIEL_API_TOKEN", "synthetic-token")
        monkeypatch.delenv(missing)
        with patch("madfam_inference.adapters.karafiel.KarafielAdapter") as adapter:
            result = validate_rfcs(self._state())
        adapter.assert_not_called()
        self._assert_unavailable(result)

    def test_both_subjects_need_explicit_valid_results(self):
        from madfam_inference.adapters.karafiel import RFCValidationResult
        from selva_workers.graphs.billing import _route_after_validate

        result, adapter = self._check(
            [
                RFCValidationResult(valid=True, rfc=rfc, check_status="checked")
                for rfc in ("XAXX010101000", "XEXX010101000")
            ]
        )
        assert result["status"] == "rfcs_validated"
        assert _route_after_validate(result) == "check_blacklist"
        assert "both emisor and receptor" in result["messages"][-1].content
        assert "XAXX010101000" not in result["messages"][-1].content
        assert adapter.validate_rfc.await_args_list == [
            call("XAXX010101000"),
            call("XEXX010101000"),
        ]

    @pytest.mark.parametrize("invalid_subject", ["emisor", "receptor"])
    def test_explicit_invalid_result_stops_instead_of_using_model_truthiness(self, invalid_subject):
        from madfam_inference.adapters.karafiel import RFCValidationResult
        from selva_workers.graphs.billing import _route_after_validate

        result, _ = self._check(
            [
                RFCValidationResult(
                    valid=subject != invalid_subject, rfc=rfc, check_status="checked"
                )
                for subject, rfc in (("emisor", "XAXX010101000"), ("receptor", "XEXX010101000"))
            ]
        )
        assert result["status"] == "error"
        assert result["result"] == {"error": "rfc_validation_invalid", "subject": invalid_subject}
        assert _route_after_validate(result) == "__end__"
        assert "XAXX010101000" not in result["messages"][-1].content

    @pytest.mark.parametrize("response", [True, False, None, {}, {"valid": True}])
    def test_untyped_response_is_unavailable(self, response):
        result, _ = self._check([response])
        self._assert_unavailable(result)

    def test_unknown_wrong_subject_and_error_results_are_unavailable(self):
        from madfam_inference.adapters.karafiel import RFCValidationResult

        for response in (
            RFCValidationResult(valid=False, rfc="XAXX010101000", status="unavailable"),
            RFCValidationResult(valid=True, rfc="XAXX010101000"),
            RFCValidationResult(valid=True, rfc="XEXX010101000", check_status="checked"),
            RFCValidationResult(
                valid=True, rfc="XAXX010101000", status="error", check_status="checked"
            ),
        ):
            result, _ = self._check([response])
            self._assert_unavailable(result)

    def test_second_subject_unavailable_does_not_claim_both_valid(self):
        from madfam_inference.adapters.karafiel import RFCValidationResult

        result, _ = self._check(
            [
                RFCValidationResult(valid=True, rfc="XAXX010101000", check_status="checked"),
                RFCValidationResult(valid=False, rfc="XEXX010101000", status="unavailable"),
            ]
        )
        self._assert_unavailable(result)

    def test_import_failure_is_unavailable(self, monkeypatch):
        import sys

        from selva_workers.graphs.billing import validate_rfcs

        monkeypatch.setenv("KARAFIEL_API_URL", "https://example.invalid")
        monkeypatch.setenv("KARAFIEL_API_TOKEN", "synthetic-token")
        with patch.dict(sys.modules, {"madfam_inference.adapters.karafiel": None}):
            result = validate_rfcs(self._state())
        self._assert_unavailable(result)

    def test_transport_failure_is_unavailable_and_redacted(self, caplog):
        result, _ = self._check(RuntimeError("SENSITIVE_SENTINEL"))
        self._assert_unavailable(result)
        assert "SENSITIVE_SENTINEL" not in str(result) + caplog.text

    def _state(self):
        return {"messages": [], "emisor_rfc": "XAXX010101000", "receptor_rfc": "XEXX010101000"}

    def _assert_unavailable(self, result):
        from selva_workers.graphs.billing import _route_after_validate

        assert result["status"] == "error"
        assert result["result"] == {"error": "rfc_validation_unavailable"}
        assert _route_after_validate(result) == "__end__"
        assert "unavailable" in result["messages"][-1].content
        assert "validated" not in result["messages"][-1].content.lower()

    def _check(self, responses):
        from selva_workers.graphs.billing import validate_rfcs

        with (
            patch.dict(
                "os.environ",
                {
                    "KARAFIEL_API_URL": "https://example.invalid",
                    "KARAFIEL_API_TOKEN": "synthetic-token",
                },
            ),
            patch("madfam_inference.adapters.karafiel.KarafielAdapter") as adapter,
        ):
            adapter.return_value.validate_rfc = AsyncMock(side_effect=responses)
            result = validate_rfcs(self._state())
        return result, adapter.return_value


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
