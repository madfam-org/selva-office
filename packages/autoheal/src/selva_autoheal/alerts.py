"""Alertmanager webhook (payload version 4) → incident.

One Alertmanager notification is one *group* (Alertmanager already grouped
and deduplicated the alerts by the route's ``group_by``). Its ``groupKey`` is
stable for the life of the group, so the incident key is derived from it:
every repeat notification of the same group lands on the same incident.

Labels and annotations become evidence an LLM reads. They are DATA: they are
length-capped here and the agent's prompt marks them as untrusted.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .config import AutohealConfig

MAX_LABEL_VALUE = 256
MAX_ANNOTATION_VALUE = 1024
MAX_ALERTS_KEPT = 20


class Alert(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: Literal["firing", "resolved"]
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: datetime | None = None
    endsAt: datetime | None = None
    generatorURL: str = ""
    fingerprint: str = ""


class AlertmanagerWebhook(BaseModel):
    """Alertmanager's ``webhook_config`` body (version "4")."""

    model_config = ConfigDict(extra="ignore")

    version: str = "4"
    groupKey: str = Field(min_length=1, max_length=2048)
    truncatedAlerts: int = 0
    status: Literal["firing", "resolved"]
    receiver: str = ""
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: str = ""
    alerts: list[Alert] = Field(default_factory=list, max_length=1000)


def incident_key(payload: AlertmanagerWebhook) -> str:
    """Stable id of the incident for this alert group (``inc-`` + 16 hex)."""
    digest = hashlib.sha256(payload.groupKey.encode("utf-8")).hexdigest()
    return f"inc-{digest[:16]}"


def _cap(values: dict[str, str], limit: int) -> dict[str, str]:
    return {str(k)[:64]: str(v)[:limit] for k, v in list(values.items())[:40]}


@dataclass(frozen=True)
class IncidentSignal:
    """The normalised alert group the agent works from."""

    key: str
    status: str
    alertname: str
    severity: str
    namespace: str
    labels: dict[str, str]
    annotations: dict[str, str]
    alerts: tuple[dict[str, Any], ...]
    truncated_alerts: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "status": self.status,
            "alertname": self.alertname,
            "severity": self.severity,
            "namespace": self.namespace,
            "labels": dict(self.labels),
            "annotations": dict(self.annotations),
            "alerts": [dict(a) for a in self.alerts],
            "truncated_alerts": self.truncated_alerts,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> IncidentSignal:
        return cls(
            key=str(raw["key"]),
            status=str(raw.get("status", "firing")),
            alertname=str(raw.get("alertname", "")),
            severity=str(raw.get("severity", "")),
            namespace=str(raw.get("namespace", "")),
            labels=dict(raw.get("labels") or {}),
            annotations=dict(raw.get("annotations") or {}),
            alerts=tuple(dict(a) for a in raw.get("alerts") or ()),
            truncated_alerts=int(raw.get("truncated_alerts") or 0),
        )


def normalise(payload: AlertmanagerWebhook) -> IncidentSignal:
    """Reduce a webhook to the signal the agent reads (capped, label-only)."""
    common = payload.commonLabels
    first = payload.alerts[0].labels if payload.alerts else {}
    alertname = common.get("alertname") or first.get("alertname", "")
    alerts = tuple(
        {
            "status": a.status,
            "labels": _cap(a.labels, MAX_LABEL_VALUE),
            "annotations": _cap(a.annotations, MAX_ANNOTATION_VALUE),
            "startsAt": a.startsAt.isoformat() if a.startsAt else None,
            "fingerprint": a.fingerprint[:64],
        }
        for a in payload.alerts[:MAX_ALERTS_KEPT]
    )
    return IncidentSignal(
        key=incident_key(payload),
        status=payload.status,
        alertname=alertname[:MAX_LABEL_VALUE],
        severity=(common.get("severity") or first.get("severity", ""))[:32],
        namespace=(common.get("namespace") or first.get("namespace", ""))[:MAX_LABEL_VALUE],
        labels=_cap(common or first, MAX_LABEL_VALUE),
        annotations=_cap(payload.commonAnnotations, MAX_ANNOTATION_VALUE),
        alerts=alerts,
        truncated_alerts=payload.truncatedAlerts + max(0, len(payload.alerts) - MAX_ALERTS_KEPT),
    )


@dataclass(frozen=True)
class Qualification:
    qualifies: bool
    reason: str


def qualify(signal: IncidentSignal, cfg: AutohealConfig) -> Qualification:
    """Does this alert group open (or continue) an incident for the agent?"""
    if signal.status == "resolved":
        return Qualification(False, "resolved")
    if not cfg.alertnames or signal.alertname not in cfg.alertnames:
        return Qualification(False, "alertname_not_allowlisted")
    if cfg.severities and signal.severity not in cfg.severities:
        return Qualification(False, "severity_not_allowlisted")
    return Qualification(True, "qualifies")
