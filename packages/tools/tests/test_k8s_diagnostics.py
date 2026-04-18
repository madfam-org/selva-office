"""Tests for k8s_diagnostics tools."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from selva_tools.builtins.k8s_diagnostics import (
    K8sDescribePodTool,
    K8sGetEventsTool,
    K8sGetPodsTool,
    K8sGetReplicasetsTool,
    K8sRolloutStatusTool,
    get_k8s_diagnostic_tools,
)


class TestRegistry:
    def test_five_tools_exported(self) -> None:
        names = {t.name for t in get_k8s_diagnostic_tools()}
        assert names == {
            "k8s_get_pods",
            "k8s_describe_pod",
            "k8s_get_events",
            "k8s_get_replicasets",
            "k8s_rollout_status",
        }


class TestCredentialGating:
    @pytest.mark.asyncio
    async def test_missing_k8s_client_returns_structured_error(self) -> None:
        with patch(
            "selva_tools.builtins.k8s_diagnostics._load_clients",
            return_value=None,
        ):
            r = await K8sGetPodsTool().execute(namespace="x")
            assert r.success is False
            assert "kubernetes client unavailable" in (r.error or "")


# -- get_pods ----------------------------------------------------------------


def _mk_pod(name: str, ready: int, total: int, restarts: int, phase: str = "Running"):
    container_statuses = [
        SimpleNamespace(ready=i < ready, restart_count=restarts) for i in range(total)
    ]
    return SimpleNamespace(
        metadata=SimpleNamespace(name=name),
        spec=SimpleNamespace(node_name="node-1"),
        status=SimpleNamespace(
            phase=phase,
            pod_ip="10.42.0.1",
            container_statuses=container_statuses,
        ),
    )


class TestGetPods:
    @pytest.mark.asyncio
    async def test_returns_ready_ratio(self) -> None:
        core = MagicMock()
        core.list_namespaced_pod.return_value = SimpleNamespace(
            items=[_mk_pod("madlab-client-xyz", 1, 1, 0)]
        )
        with patch(
            "selva_tools.builtins.k8s_diagnostics._load_clients",
            return_value=(core, MagicMock(), MagicMock()),
        ):
            r = await K8sGetPodsTool().execute(namespace="madlab")
            assert r.success is True
            assert r.data["pods"][0]["ready"] == "1/1"
            assert r.data["pods"][0]["restarts"] == 0

    @pytest.mark.asyncio
    async def test_passes_label_selector_through(self) -> None:
        core = MagicMock()
        core.list_namespaced_pod.return_value = SimpleNamespace(items=[])
        with patch(
            "selva_tools.builtins.k8s_diagnostics._load_clients",
            return_value=(core, MagicMock(), MagicMock()),
        ):
            await K8sGetPodsTool().execute(
                namespace="madlab", label_selector="app=madlab-server"
            )
            call = core.list_namespaced_pod.call_args
            assert call.kwargs["label_selector"] == "app=madlab-server"


# -- describe_pod -----------------------------------------------------------


class TestDescribePod:
    @pytest.mark.asyncio
    async def test_crashloop_container_state_surfaced(self) -> None:
        waiting = SimpleNamespace(
            reason="CrashLoopBackOff",
            message="back-off 40s restarting failed container",
        )
        cs = SimpleNamespace(
            name="server",
            image="ghcr.io/madfam-org/accionables-madlab-server@sha256:abc",
            ready=False,
            restart_count=7,
            state=SimpleNamespace(running=None, waiting=waiting, terminated=None),
        )
        pod = SimpleNamespace(
            metadata=SimpleNamespace(name="madlab-server-xyz"),
            status=SimpleNamespace(
                phase="Running",
                container_statuses=[cs],
                conditions=[
                    SimpleNamespace(type="Ready", status="False", reason="ContainersNotReady")
                ],
            ),
        )
        event = SimpleNamespace(
            type="Warning",
            reason="BackOff",
            message="Back-off restarting failed container",
            last_timestamp=datetime.now(UTC),
            event_time=None,
        )
        core = MagicMock()
        core.read_namespaced_pod.return_value = pod
        core.list_namespaced_event.return_value = SimpleNamespace(items=[event])
        with patch(
            "selva_tools.builtins.k8s_diagnostics._load_clients",
            return_value=(core, MagicMock(), MagicMock()),
        ):
            r = await K8sDescribePodTool().execute(
                namespace="madlab", name="madlab-server-xyz"
            )
            assert r.success is True
            assert r.data["containers"][0]["state"]["waiting"]["reason"] == (
                "CrashLoopBackOff"
            )
            assert r.data["events"][0]["reason"] == "BackOff"
            assert r.data["conditions"][0]["reason"] == "ContainersNotReady"


# -- get_events -------------------------------------------------------------


class TestGetEvents:
    @pytest.mark.asyncio
    async def test_warning_only_filter_passes_field_selector(self) -> None:
        core = MagicMock()
        core.list_namespaced_event.return_value = SimpleNamespace(items=[])
        with patch(
            "selva_tools.builtins.k8s_diagnostics._load_clients",
            return_value=(core, MagicMock(), MagicMock()),
        ):
            await K8sGetEventsTool().execute(namespace="x", warning_only=True)
            call = core.list_namespaced_event.call_args
            assert call.kwargs["field_selector"] == "type=Warning"

    @pytest.mark.asyncio
    async def test_sort_most_recent_first(self) -> None:
        t1 = datetime(2026, 4, 18, 10, 0, tzinfo=UTC)
        t2 = datetime(2026, 4, 18, 11, 0, tzinfo=UTC)
        events = [
            SimpleNamespace(
                type="Normal",
                reason="Scheduled",
                involved_object=SimpleNamespace(kind="Pod", name="p1"),
                message="scheduled",
                count=1,
                last_timestamp=t1,
                event_time=None,
            ),
            SimpleNamespace(
                type="Warning",
                reason="Failed",
                involved_object=SimpleNamespace(kind="Pod", name="p2"),
                message="fail",
                count=3,
                last_timestamp=t2,
                event_time=None,
            ),
        ]
        core = MagicMock()
        core.list_namespaced_event.return_value = SimpleNamespace(items=events)
        with patch(
            "selva_tools.builtins.k8s_diagnostics._load_clients",
            return_value=(core, MagicMock(), MagicMock()),
        ):
            r = await K8sGetEventsTool().execute(namespace="x")
            assert r.data["events"][0]["reason"] == "Failed"


# -- get_replicasets --------------------------------------------------------


class TestGetReplicasets:
    @pytest.mark.asyncio
    async def test_desired_current_ready_surfaced(self) -> None:
        apps = MagicMock()
        rs = SimpleNamespace(
            metadata=SimpleNamespace(
                name="madlab-server-abc",
                creation_timestamp=datetime.now(UTC),
            ),
            spec=SimpleNamespace(
                replicas=1,
                template=SimpleNamespace(
                    spec=SimpleNamespace(
                        containers=[SimpleNamespace(image="img:tag")]
                    )
                ),
            ),
            status=SimpleNamespace(replicas=1, ready_replicas=0),
        )
        apps.list_namespaced_replica_set.return_value = SimpleNamespace(items=[rs])
        with patch(
            "selva_tools.builtins.k8s_diagnostics._load_clients",
            return_value=(MagicMock(), apps, MagicMock()),
        ):
            r = await K8sGetReplicasetsTool().execute(namespace="madlab")
            assert r.success is True
            s = r.data["replicasets"][0]
            assert s["desired"] == 1
            assert s["current"] == 1
            assert s["ready"] == 0


# -- rollout_status ---------------------------------------------------------


class TestRolloutStatus:
    @pytest.mark.asyncio
    async def test_deployment_conditions_surfaced(self) -> None:
        apps = MagicMock()
        obj = SimpleNamespace(
            metadata=SimpleNamespace(generation=5),
            status=SimpleNamespace(
                observed_generation=5,
                replicas=1,
                ready_replicas=1,
                updated_replicas=1,
                available_replicas=1,
                conditions=[
                    SimpleNamespace(
                        type="Available",
                        status="True",
                        reason="MinimumReplicasAvailable",
                        message="Deployment has minimum availability.",
                    )
                ],
            ),
        )
        apps.read_namespaced_deployment.return_value = obj
        with patch(
            "selva_tools.builtins.k8s_diagnostics._load_clients",
            return_value=(MagicMock(), apps, MagicMock()),
        ):
            r = await K8sRolloutStatusTool().execute(
                namespace="madlab", kind="Deployment", name="madlab-server"
            )
            assert r.success is True
            assert r.data["observed_generation"] == 5
            assert r.data["conditions"][0]["type"] == "Available"

    @pytest.mark.asyncio
    async def test_statefulset_kind_dispatch(self) -> None:
        apps = MagicMock()
        apps.read_namespaced_stateful_set.return_value = SimpleNamespace(
            metadata=SimpleNamespace(generation=1),
            status=SimpleNamespace(
                observed_generation=1,
                replicas=1,
                ready_replicas=1,
                conditions=[],
            ),
        )
        with patch(
            "selva_tools.builtins.k8s_diagnostics._load_clients",
            return_value=(MagicMock(), apps, MagicMock()),
        ):
            r = await K8sRolloutStatusTool().execute(
                namespace="data", kind="StatefulSet", name="madlab-postgres"
            )
            assert r.success is True
            apps.read_namespaced_stateful_set.assert_called_once()
