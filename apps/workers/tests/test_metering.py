"""Tests for inference metering."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestMeterInferenceCall:
    """meter_inference_call sends usage data to the billing API."""

    @pytest.mark.asyncio
    async def test_posts_usage_to_billing_endpoint(self) -> None:
        mock_response = MagicMock(status_code=201)
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "selva_workers.metering.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
            patch("selva_workers.metering.httpx.AsyncClient", return_value=mock_client),
        ):
            from selva_workers.metering import meter_inference_call

            await meter_inference_call(
                usage={"input_tokens": 100, "output_tokens": 50},
                provider="anthropic",
                model="claude-sonnet-4-6",
                agent_id="agent-1",
                task_id="task-1",
                org_id="test-org",
            )

            mock_client.post.assert_called_once()
            call_args = mock_client.post.call_args
            assert call_args[0][0] == "http://test:4300/api/v1/billing/record"
            payload = call_args[1]["json"]
            assert payload["amount"] == 150
            assert payload["provider"] == "anthropic"
            assert payload["model"] == "claude-sonnet-4-6"
            assert payload["org_id"] == "test-org"

    @pytest.mark.asyncio
    async def test_sends_worker_auth_headers(self) -> None:
        """The billing endpoint is authenticated (RFC 0034 P0): an unauthenticated
        POST is silently 401-dropped, so metering must send worker auth headers
        with the tenant org declared."""
        mock_response = MagicMock(status_code=201)
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "selva_workers.metering.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
            patch("selva_workers.metering.httpx.AsyncClient", return_value=mock_client),
            patch(
                "selva_workers.metering.get_worker_auth_headers",
                return_value={
                    "Authorization": "Bearer worker-token",
                    "X-Selva-Tenant-Org": "test-org",
                },
            ) as mock_headers,
        ):
            from selva_workers.metering import meter_inference_call

            await meter_inference_call(
                usage={"input_tokens": 1, "output_tokens": 1},
                provider="anthropic",
                model="claude-sonnet-4-6",
                org_id="test-org",
            )

            mock_headers.assert_called_once_with(org_id="test-org")
            headers = mock_client.post.call_args[1]["headers"]
            assert headers["Authorization"] == "Bearer worker-token"
            assert headers["X-Selva-Tenant-Org"] == "test-org"

    @pytest.mark.asyncio
    async def test_skips_when_zero_tokens(self) -> None:
        with patch("selva_workers.metering.httpx.AsyncClient") as mock_cls:
            from selva_workers.metering import meter_inference_call

            await meter_inference_call(
                usage={"input_tokens": 0, "output_tokens": 0},
                provider="anthropic",
                model="test",
            )
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_when_empty_usage(self) -> None:
        with patch("selva_workers.metering.httpx.AsyncClient") as mock_cls:
            from selva_workers.metering import meter_inference_call

            await meter_inference_call(
                usage={},
                provider="anthropic",
                model="test",
            )
            mock_cls.assert_not_called()

    @pytest.mark.asyncio
    async def test_does_not_raise_on_http_error(self) -> None:
        mock_client = AsyncMock()
        mock_client.post.side_effect = Exception("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "selva_workers.metering.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
            patch("selva_workers.metering.httpx.AsyncClient", return_value=mock_client),
        ):
            from selva_workers.metering import meter_inference_call

            # Should not raise
            await meter_inference_call(
                usage={"input_tokens": 10, "output_tokens": 5},
                provider="anthropic",
                model="test",
            )

    @pytest.mark.asyncio
    async def test_logs_warning_on_non_201_status(self) -> None:
        mock_response = MagicMock(status_code=400, text="Bad request")
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with (
            patch(
                "selva_workers.metering.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
            patch("selva_workers.metering.httpx.AsyncClient", return_value=mock_client),
            patch("selva_workers.metering.logger") as mock_logger,
        ):
            from selva_workers.metering import meter_inference_call

            await meter_inference_call(
                usage={"input_tokens": 10, "output_tokens": 5},
                provider="anthropic",
                model="test",
            )
            mock_logger.warning.assert_called()


class TestCallLlmMetering:
    """call_llm meters usage after successful inference."""

    @pytest.mark.asyncio
    async def test_meters_usage_after_successful_call(self) -> None:
        mock_response = MagicMock(
            content="Hello",
            provider="anthropic",
            model="claude-sonnet-4-6",
            usage={"input_tokens": 50, "output_tokens": 25},
        )
        mock_router = MagicMock()
        mock_router.complete = AsyncMock(return_value=mock_response)

        with patch(
            "selva_workers.metering.meter_inference_call",
            new_callable=AsyncMock,
        ) as mock_meter:
            from selva_workers.inference import call_llm

            result = await call_llm(
                mock_router,
                [{"role": "user", "content": "hi"}],
                agent_id="agent-1",
                task_id="task-1",
                org_id="test-org",
            )
            assert result == "Hello"
            mock_meter.assert_called_once_with(
                usage={"input_tokens": 50, "output_tokens": 25},
                provider="anthropic",
                model="claude-sonnet-4-6",
                agent_id="agent-1",
                task_id="task-1",
                org_id="test-org",
                task_type=None,
            )

    @pytest.mark.asyncio
    async def test_skips_metering_when_no_usage(self) -> None:
        mock_response = MagicMock(
            content="Hello",
            provider="anthropic",
            model="test",
            usage={},
        )
        mock_router = MagicMock()
        mock_router.complete = AsyncMock(return_value=mock_response)

        with patch(
            "selva_workers.metering.meter_inference_call",
            new_callable=AsyncMock,
        ) as mock_meter:
            from selva_workers.inference import call_llm

            result = await call_llm(mock_router, [{"role": "user", "content": "hi"}])
            assert result == "Hello"
            mock_meter.assert_not_called()


class TestTaskOrgAttribution:
    """call_llm attributes spend and routing to the task's org, not ``default``."""

    @staticmethod
    def _router() -> MagicMock:
        router = MagicMock()
        router.complete = AsyncMock(
            return_value=MagicMock(
                content="ok",
                provider="anthropic",
                model="claude-opus-5-5",
                usage={"input_tokens": 1, "output_tokens": 1},
            )
        )
        return router

    @pytest.mark.asyncio
    async def test_task_org_is_bound_for_call_sites_that_do_not_pass_it(self) -> None:
        from selva_workers.inference import call_llm, with_task_org

        router = self._router()
        with (
            patch("selva_workers.metering.meter_inference_call", new_callable=AsyncMock) as meter,
            with_task_org("madfam"),
        ):
            await call_llm(router, [{"role": "user", "content": "hi"}], task_type="planning")
        request = router.complete.call_args[0][0]
        assert request.policy.org_id == "madfam"
        assert meter.call_args.kwargs["org_id"] == "madfam"
        assert meter.call_args.kwargs["task_type"] == "planning"

    @pytest.mark.asyncio
    async def test_explicit_org_wins_and_default_remains_last_resort(self) -> None:
        from selva_workers.inference import call_llm, with_task_org

        router = self._router()
        with (
            patch("selva_workers.metering.meter_inference_call", new_callable=AsyncMock),
            with_task_org("madfam"),
        ):
            await call_llm(router, [{"role": "user", "content": "hi"}], org_id="tenant-x")
        assert router.complete.call_args[0][0].policy.org_id == "tenant-x"

        with patch("selva_workers.metering.meter_inference_call", new_callable=AsyncMock):
            await call_llm(router, [{"role": "user", "content": "hi"}])
        assert router.complete.call_args[0][0].policy.org_id == "default"

    def test_run_async_propagates_the_task_org_into_its_helper_thread(self) -> None:
        import asyncio

        from selva_workers.graphs.base import run_async
        from selva_workers.inference import resolve_task_org_id, with_task_org

        async def _probe() -> str:
            return resolve_task_org_id()

        async def _outer() -> str:
            # A running loop forces run_async onto its ThreadPoolExecutor path.
            return run_async(_probe())

        with with_task_org("madfam"):
            assert asyncio.run(_outer()) == "madfam"


class TestCallLlmFailsVisibly:
    @pytest.mark.asyncio
    async def test_raises_instead_of_placeholder_and_records_failure(self) -> None:
        from selva_workers.inference import LLMCallError, call_llm, with_task_org

        router = MagicMock()
        router.complete = AsyncMock(side_effect=RuntimeError("All providers failed"))
        with with_task_org("madfam") as failures, pytest.raises(LLMCallError):
            await call_llm(router, [{"role": "user", "content": "hi"}], task_type="coding")
        assert len(failures) == 1
        assert failures[0]["task_type"] == "coding"
        assert "All providers failed" in failures[0]["error"]


class TestMeteringSendsSplitForUsd:
    @pytest.mark.asyncio
    async def test_payload_carries_split_cache_and_task_type(self) -> None:
        mock_client = AsyncMock()
        mock_client.post.return_value = MagicMock(status_code=201)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        with (
            patch(
                "selva_workers.metering.get_settings",
                return_value=MagicMock(nexus_api_url="http://test:4300"),
            ),
            patch("selva_workers.metering.httpx.AsyncClient", return_value=mock_client),
        ):
            from selva_workers.metering import meter_inference_call

            await meter_inference_call(
                usage={
                    "input_tokens": 10,
                    "output_tokens": 20,
                    "cache_read_input_tokens": 3000,
                    "cache_creation_input_tokens": 400,
                },
                provider="anthropic",
                model="claude-opus-5-5",
                org_id="madfam",
                task_type="planning",
            )
        payload = mock_client.post.call_args[1]["json"]
        assert payload["amount"] == 30  # unchanged meaning: uncached in + out
        assert payload["input_tokens"] == 10
        assert payload["output_tokens"] == 20
        assert payload["cache_read_tokens"] == 3000
        assert payload["cache_creation_tokens"] == 400
        assert payload["task_type"] == "planning"


class TestModelPin:
    @staticmethod
    def _router(allowed: list[str], registered: list[str]) -> MagicMock:
        router = MagicMock()
        router.allowed_providers_for = MagicMock(return_value=allowed)
        router.available_providers = registered
        router.complete = AsyncMock(
            return_value=MagicMock(content="ok", provider="x", model="y", usage={})
        )
        return router

    @pytest.mark.asyncio
    async def test_pin_honoured_when_provider_allowed_for_org(self) -> None:
        from selva_workers.inference import call_llm

        router = self._router(["deepinfra", "anthropic"], ["deepinfra", "anthropic", "ollama"])
        await call_llm(router, [{"role": "user", "content": "x"}], model="claude-opus-5-5")
        policy = router.complete.call_args[0][0].policy
        assert policy.provider_allowlist == ["anthropic", "deepinfra"]
        assert policy.provider_models == {"anthropic": "claude-opus-5-5"}

    @pytest.mark.asyncio
    async def test_pin_ignored_when_org_config_does_not_allow_provider(self) -> None:
        from selva_workers.inference import call_llm

        router = self._router(["deepinfra"], ["deepinfra", "anthropic", "ollama"])
        await call_llm(router, [{"role": "user", "content": "x"}], model="gpt-4o")
        policy = router.complete.call_args[0][0].policy
        assert policy.provider_allowlist is None
        assert policy.model_override is None

    @pytest.mark.asyncio
    async def test_provider_neutral_model_id_passes_through(self) -> None:
        from selva_workers.inference import call_llm

        router = self._router(["deepinfra"], ["deepinfra"])
        await call_llm(
            router, [{"role": "user", "content": "x"}], model="meta-llama/Llama-3.3-70B-Instruct"
        )
        policy = router.complete.call_args[0][0].policy
        assert policy.model_override == "meta-llama/Llama-3.3-70B-Instruct"
