"""Evidence collection and deterministic known-incident signatures.

The agent always starts with a fixed, cheap, read-only probe set chosen from
the alert's labels (no model call). Signatures then match that evidence
against incidents we already understand. A signature match is a diagnosis
with evidence even when no model budget is left («sin presupuesto»), and it
anchors the model when there is budget.

Signature 1, ``cnpg-operator-ingress-blocked`` (incident of 2026-10-24):
CloudNativePG reports «Instance Status Extraction Error: HTTP communication
issue» because the namespace has a default-deny ingress NetworkPolicy and no
policy admits ``cnpg-system`` to the instances' status port (TCP 8000). Enclii
fixed it in switchyard (enclii #854: ``<cluster>-operator-ingress``, converged
at provisioning, on refresh and every 10 minutes by the addon network sweep).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .alerts import IncidentSignal
from .tools import Toolbox, ToolOutcome

CNPG_NAMESPACE = "cnpg-system"
CNPG_STATUS_PORT = "8000"
CNPG_SYMPTOMS = ("instance status extraction error", "http communication issue")


@dataclass
class Evidence:
    id: str
    tool: str
    args: dict[str, Any]
    ok: bool
    text: str
    data: Any = None

    def brief(self) -> dict[str, Any]:
        return {"id": self.id, "tool": self.tool, "args": self.args, "ok": self.ok}


@dataclass
class EvidenceLog:
    items: list[Evidence] = field(default_factory=list)

    def add(self, tool: str, args: dict[str, Any], outcome: ToolOutcome) -> Evidence:
        item = Evidence(
            id=f"E{len(self.items) + 1}",
            tool=tool,
            args=dict(args),
            ok=outcome.ok,
            text=outcome.text,
            data=outcome.data,
        )
        self.items.append(item)
        return item

    def ids(self) -> set[str]:
        return {e.id for e in self.items}


def _looks_cnpg(signal: IncidentSignal) -> bool:
    blob = " ".join(
        [signal.alertname, *signal.labels.keys(), *signal.labels.values(),
         *signal.annotations.values()]
    ).lower()
    return "cnpg" in blob or "postgres" in blob or "cloudnative" in blob


def _first_pod(outcome: ToolOutcome, needle: str) -> str | None:
    data = outcome.data.get("data") if isinstance(outcome.data, dict) else None
    pods = data.get("pods") if isinstance(data, dict) else data
    if not isinstance(pods, list):
        return None
    for pod in pods:
        name = pod.get("name") if isinstance(pod, dict) else None
        if isinstance(name, str) and needle in name:
            return name
    return None


async def collect_evidence(signal: IncidentSignal, toolbox: Toolbox) -> EvidenceLog:
    """The fixed first pass: reads only, no model."""
    log = EvidenceLog()

    async def probe(tool: str, args: dict[str, Any]) -> ToolOutcome:
        outcome = await toolbox.call(tool, args)
        log.add(tool, args, outcome)
        return outcome

    ns = signal.namespace
    if ns:
        await probe("enclii_ops_read", {"domain": "pods", "action": "diagnose", "namespace": ns})
        await probe(
            "enclii_ops_read",
            {"domain": "inventory", "action": "network-policies", "namespace": ns},
        )
    project = signal.labels.get("enclii_project") or signal.labels.get("project")
    if project:
        await probe("enclii_get", {"path": f"/v1/projects/{project}/addons"})
    if _looks_cnpg(signal):
        operator = await probe(
            "enclii_ops_read",
            {"domain": "pods", "action": "diagnose", "namespace": CNPG_NAMESPACE},
        )
        pod = _first_pod(operator, "cnpg")
        if pod:
            await probe(
                "enclii_ops_read",
                {
                    "domain": "pods",
                    "action": "logs",
                    "namespace": CNPG_NAMESPACE,
                    "target": pod,
                    "tail_lines": 200,
                },
            )
    return log


@dataclass(frozen=True)
class SignatureMatch:
    id: str
    summary: str
    root_cause: str
    evidence_ids: tuple[str, ...]
    remedy: dict[str, Any]
    confidence: str = "high"


def _policies(item: Evidence, namespace: str) -> list[dict[str, Any]] | None:
    data = item.data.get("data") if isinstance(item.data, dict) else None
    groups = data.get("groups") if isinstance(data, dict) else None
    if not isinstance(groups, list):
        return None
    for group in groups:
        if isinstance(group, dict) and group.get("namespace") == namespace:
            return [p for p in group.get("policies") or [] if isinstance(p, dict)]
    return []


def _is_default_deny_ingress(policy: dict[str, Any]) -> bool:
    return (
        policy.get("pod_selector_summary") == "all pods"
        and "Ingress" in (policy.get("policy_types") or [])
        and int(policy.get("ingress_rules") or 0) == 0
    )


def _admits_cnpg_operator(policy: dict[str, Any]) -> bool:
    for rule in policy.get("ingress_summary") or []:
        text = str(rule)
        source, _, ports = text.partition("->")
        open_source = "all sources" in source or CNPG_NAMESPACE in source
        open_port = "any-port" in ports or f"/{CNPG_STATUS_PORT}" in ports or "/any" in ports
        if open_source and open_port:
            return True
    return False


def match_cnpg_operator_ingress(signal: IncidentSignal, log: EvidenceLog) -> SignatureMatch | None:
    ns = signal.namespace
    if not ns:
        return None
    texts = [e for e in log.items if any(s in e.text.lower() for s in CNPG_SYMPTOMS)]
    alert_text = " ".join([*signal.annotations.values(), *signal.labels.values()]).lower()
    if not texts and not any(s in alert_text for s in CNPG_SYMPTOMS):
        return None
    for item in log.items:
        if item.tool != "enclii_ops_read" or item.args.get("action") != "network-policies":
            continue
        policies = _policies(item, ns)
        if policies is None:
            continue
        deny = [p for p in policies if _is_default_deny_ingress(p)]
        admitting = [p for p in policies if _admits_cnpg_operator(p)]
        if not deny or admitting:
            return None
        cluster = signal.labels.get("cluster") or signal.labels.get("cnpg_io_cluster") or "<cluster>"
        deny_names = ", ".join(str(p.get("name")) for p in deny)
        return SignatureMatch(
            id="cnpg-operator-ingress-blocked",
            summary=(
                f"CNPG no puede leer el estado de las instancias en {ns}: la política "
                f"default-deny ({deny_names}) bloquea a {CNPG_NAMESPACE} → TCP/{CNPG_STATUS_PORT}."
            ),
            root_cause=(
                f"El namespace {ns} tiene ingress default-deny y ninguna NetworkPolicy admite "
                f"pods de {CNPG_NAMESPACE} al puerto de estado {CNPG_STATUS_PORT} de las "
                "instancias; el operador marca el clúster con «Instance Status Extraction "
                "Error: HTTP communication issue»."
            ),
            evidence_ids=tuple(e.id for e in [*texts, item]),
            remedy={
                "kind": "prepare_only_pr",
                "title": f"Converger {cluster}-operator-ingress en {ns}",
                "detail": (
                    f"Falta la NetworkPolicy `{cluster}-operator-ingress` (ingress desde el "
                    f"namespace {CNPG_NAMESPACE} a TCP/{CNPG_STATUS_PORT} en pods "
                    f"cnpg.io/cluster={cluster}). Enclii la crea al aprovisionar y la "
                    "reconcilia cada 10 min desde enclii #854 (addon network sweep). "
                    "Verificar que switchyard-api corre una versión con #854 y que el sweep "
                    "está activo. Enclii no tiene op que escriba NetworkPolicies: si el "
                    "sweep no la crea, el remedio es un PR prepare-only en enclii."
                ),
                "verify": (
                    f"inventory/network-policies muestra {cluster}-operator-ingress en {ns} y "
                    "el estado del addon deja de mencionar «Instance Status Extraction Error»."
                ),
            },
        )
    return None


SIGNATURES = (match_cnpg_operator_ingress,)


def match_signatures(signal: IncidentSignal, log: EvidenceLog) -> list[SignatureMatch]:
    return [m for fn in SIGNATURES if (m := fn(signal, log)) is not None]
