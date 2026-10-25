"""The Telegram text of a diagnosis (Spanish, plain text, ≤ 4096 chars).

The plan hash is in the message so the human who approves applies exactly
the reviewed plan (Enclii's ``expected_plan``). v1 never applies anything.
"""

from __future__ import annotations

from .agent import DiagnosisReport

TELEGRAM_LIMIT = 4096

_STATUS = {
    "diagnosed": "diagnóstico listo",
    "evidence_only": "solo evidencia",
    "sin_presupuesto": "sin presupuesto (sin modelo): solo evidencia",
    "stopped": "detenido",
}


def render(report: DiagnosisReport) -> str:
    lines = [
        f"[Selva autoheal] Incidente {report.incident_key}",
        f"Alerta: {report.alertname or '-'} · namespace {report.namespace or '-'}",
        f"Estado: {_STATUS.get(report.status, report.status)}"
        + (f" ({report.stop_reason})" if report.stop_reason else ""),
        "",
        f"Resumen: {report.summary}",
    ]
    if report.root_cause:
        lines.append(f"Causa probable ({report.confidence}): {report.root_cause}")
    if report.cited_evidence:
        cited = {e["id"]: e for e in report.evidence}
        lines.append("")
        lines.append("Evidencia:")
        for eid in report.cited_evidence[:6]:
            item = cited.get(eid)
            if item:
                args = " ".join(f"{k}={v}" for k, v in item.get("args", {}).items())
                lines.append(f"- {eid} {item['tool']} {args}")
    remedy = report.remedy
    if remedy:
        lines.append("")
        lines.append(f"Remedio propuesto ({remedy.get('kind', 'manual')}): {remedy.get('title', '')}")
        if remedy.get("detail"):
            lines.append(str(remedy["detail"]))
        if remedy.get("plan_hash"):
            op = remedy.get("enclii_op") or {}
            lines.append(
                f"Plan Enclii {op.get('domain', '')}/{op.get('action', '')}: "
                f"plan_hash {remedy['plan_hash']}"
            )
            lines.append(
                "Para aplicar: revisar el plan en Enclii y aplicarlo con ese plan_hash "
                "(expected_plan). Selva no aplica nada en v1."
            )
        if remedy.get("verify"):
            lines.append(f"Verificar: {remedy['verify']}")
    lines.append("")
    lines.append(
        f"Gasto del agente: USD {report.spent_usd:.4f} en {report.llm_calls} llamada(s)"
        + (f" vía {', '.join(report.providers_used)}" if report.providers_used else "")
        + ". Ninguna escritura en producción."
    )
    text = "\n".join(lines)
    if len(text) > TELEGRAM_LIMIT:
        text = text[: TELEGRAM_LIMIT - 20] + "\n…[recortado]"
    return text
