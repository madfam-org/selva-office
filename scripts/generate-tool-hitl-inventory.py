#!/usr/bin/env python3
"""Generate docs/TOOL_HITL_INVENTORY.md from the live tool registry.

Enumerates every built-in tool programmatically (``get_builtin_tools()``,
with the ship-dark social posting tools armed so they are listed too) and
joins it with ``selva_permissions.tool_policy`` and the classifier.

Usage:
    uv run python scripts/generate-tool-hitl-inventory.py          # write
    uv run python scripts/generate-tool-hitl-inventory.py --check  # CI/drift
"""

from __future__ import annotations

import argparse
import inspect
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "TOOL_HITL_INVENTORY.md"

# Ship-dark tools only register when armed; arm them for enumeration only.
ARMING_ENV = ("SELVA_X_POST_ENABLED", "SELVA_LINKEDIN_POST_ENABLED")

# Tool-level gates that cannot be detected from the source automatically.
GATE_NOTES: dict[str, str] = {
    "bluesky_post": "promo playbook require_approval; rate limit",
    "mastodon_post": "promo playbook require_approval; rate limit",
    "reddit_post": "promo playbook require_approval; rate limit",
    "x_post": "ships dark (env-armed); promo playbook require_approval",
    "linkedin_post": "ships dark (env-armed)",
    "sql_query": "SELECT-only enforced",
    "enclii_exec": "command allowlist",
    "http_request": "SSRF guard; classifier is method-aware",
    "graphql_query": "SSRF guard; classifier treats mutations as writes",
    "webhook_send": "SSRF guard",
    "enclii_scale": "replicas capped at 10",
    "read_credential_file": "path confined to ~/.selva/credentials",
    "send_marketing_email": "HTML sanitiser; outbound governance",
    "send_email": "outbound governance",
}

_TABLE_HEADER = (
    "| Tool | Module | Audience | Side effect | Tool-level gate "
    "| Before (category / decision) | After (category / decision) |\n"
    "|---|---|---|---|---|---|---|"
)

# Rules added by open PR #324 (same lines in both PRs); "before" means main
# without them.
_PRE_POLICY_EXCLUDE = frozenset({"generate_quote", "factory_manifest_publish"})


def _legacy_category(name: str):  # type: ignore[no-untyped-def]
    """Classification before the explicit policy table (main @ 2026-10-17)."""
    from selva_permissions import ActionClassifier
    from selva_permissions.types import ActionCategory

    n = name.strip().lower()
    if n in ActionClassifier.TOOL_CATEGORY_MAP and n not in _PRE_POLICY_EXCLUDE:
        return ActionClassifier.TOOL_CATEGORY_MAP[n]
    for sub, cat in ActionClassifier._FALLBACK_RULES:
        if sub in n:
            return cat
    return ActionCategory.API_CALL


def _module_gate(tool: object) -> list[str]:
    gates: list[str] = []
    module = sys.modules.get(type(tool).__module__)
    try:
        src = inspect.getsource(module) if module else ""
    except (OSError, TypeError):
        src = ""
    if "PermissionEngine" in src:
        gates.append("tool-level env escalation (PermissionEngine)")
    return gates


def build() -> str:
    saved = {var: os.environ.get(var) for var in ARMING_ENV}
    os.environ.update({var: "1" for var in ARMING_ENV})
    try:
        return _build()
    finally:
        for var, value in saved.items():
            if value is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = value


def _build() -> str:
    from selva_permissions import ActionClassifier, PermissionEngine
    from selva_permissions.tool_policy import (
        BUILTIN_TOOL_POLICY,
        GATED_SIDE_EFFECTS,
        NON_REGISTRY_TOOL_NAMES,
        SideEffect,
    )
    from selva_tools.builtins import get_builtin_tools

    classifier = ActionClassifier()
    engine = PermissionEngine()

    by_name: dict[str, list[object]] = defaultdict(list)
    for tool in get_builtin_tools():
        by_name[tool.name].append(tool)

    rows: list[str] = []
    counts: Counter[str] = Counter()
    side_counts: Counter[str] = Counter()
    newly_gated: list[str] = []
    relax_candidates: list[str] = []
    for name in sorted(by_name):
        tools = by_name[name]
        modules = ", ".join(sorted({type(t).__module__.rsplit(".", 1)[-1] for t in tools}))
        audience = tools[0].audience.value  # type: ignore[attr-defined]
        policy = BUILTIN_TOOL_POLICY.get(name)
        side = policy.side_effect.value if policy else "UNCLASSIFIED"
        gates: list[str] = []
        if audience == "platform":
            gates.append("platform-only (audience guard)")
        gates.extend(_module_gate(tools[0]))
        if name in GATE_NOTES:
            gates.append(GATE_NOTES[name])
        before_cat = _legacy_category(name)
        before_lvl = engine.evaluate(before_cat).level.value.upper()
        after_cat = classifier.classify(name)
        after_lvl = engine.evaluate(after_cat).level.value.upper()
        side_counts[side] += 1
        if before_lvl == "ALLOW" and after_lvl != "ALLOW":
            newly_gated.append(name)
            counts["newly_gated"] += 1
        if policy and policy.side_effect == SideEffect.READ_ONLY:
            if after_lvl == "ALLOW":
                counts["read_only_allowed"] += 1
            else:
                relax_candidates.append(name)
        if policy and policy.side_effect in GATED_SIDE_EFFECTS:
            counts["gated_total"] += 1
        if before_lvl == after_lvl == "ASK":
            counts["ask_unchanged"] += 1
        rows.append(
            f"| `{name}` | {modules} | {audience} | {side} | "
            f"{'; '.join(gates) or '-'} | {before_cat.value} / {before_lvl} | "
            f"{after_cat.value} / {after_lvl} |"
        )

    side_lines = "\n".join(f"| {k} | {v} |" for k, v in sorted(side_counts.items()))
    newly = ", ".join(f"`{n}`" for n in newly_gated)
    relax = ", ".join(f"`{n}`" for n in relax_candidates)
    extra = ", ".join(f"`{n}`" for n in sorted(NON_REGISTRY_TOOL_NAMES))

    return (
        f"""# Built-in tool HITL inventory

> Generated by `scripts/generate-tool-hitl-inventory.py` from the live
> registry (`selva_tools.builtins.get_builtin_tools()`, ship-dark social
> tools armed for enumeration) and `selva_permissions.tool_policy`.
> Do not edit by hand; `tests/unit/test_tool_hitl_policy.py` fails when
> this file drifts.

## Why

Before the explicit policy table, a tool name that matched no rule in
`ActionClassifier` fell through to `API_CALL`, which the default matrix
resolves to **ALLOW** at the graph HITL layer
(`apps/workers/selva_workers/graphs/base.py::permission_check`). Most
built-in tools were in that bucket, including money-moving, fiscal,
social-post, outbound-send, infra-mutating and secret-mutating tools.

## Policy

- Every built-in tool has an explicit entry in
  `packages/permissions/selva_permissions/tool_policy.py` (side-effect class
  plus `ActionCategory`). A new tool without an entry fails `tests/unit`.
- Side-effecting classes ({", ".join(sorted(s.value for s in GATED_SIDE_EFFECTS))})
  map to categories whose default level is ASK.
- Read-only tools map to `file_read`, `infra_monitor` or `api_call` (ALLOW).
- Tools that were already ASK stay ASK. Where a tool was ASK only because of a
  substring accident in the fallback rules, it is listed below as a relax
  candidate; relaxing is an owner decision, not part of this change.
- `http_request` and `graphql_query` are classified from their arguments:
  GET/HEAD/OPTIONS and GraphQL queries are `api_call`; other methods,
  mutations and subscriptions are `external_write` (ASK).
- Tools that match nothing now resolve to `unclassified_tool` (ASK) instead of
  `api_call` (ALLOW); that flip is its own commit so it can be reverted alone.
- Effective decisions below use the default matrix only. Role matrices,
  context rules, playbooks and skill overrides can still escalate (or, for a
  skill that grants a category, relax) at run time.

## Counts

- Built-in tools enumerated: **{len(by_name)}** (plus {extra} classified as
  worker-local tools).
- Newly gated (ALLOW before, ASK now): **{counts["newly_gated"]}**.
- Side-effecting tools, all ASK now: **{counts["gated_total"]}**.
- Read-only tools explicitly ALLOW: **{counts["read_only_allowed"]}**.
- ASK before and after: **{counts["ask_unchanged"]}**.

| Side-effect class | Tools |
|---|---|
{side_lines}

Newly gated: {newly}.

Read-only but kept ASK (relax candidates for the owner): {relax}.

## Blast radius of the default flip

No production graph calls `permission_check` today: it is defined in
`graphs/base.py` and exercised by tests, while the coding, CRM and deployment
graphs call `check_permission()` with a fixed category string and the
research graph calls the web-search provider directly (no registry tool, no
classifier). Built-in registry tools are executed directly only by the
approved-post executor and the warm-up job, which never consult the
classifier. So the flip changes no graph's behaviour today; it makes the
classifier fail closed for whoever wires it next (a new tool, an MCP or
Coupler proxy tool, or a future tool-calling loop).

## Inventory

{_TABLE_HEADER}
"""
        + "\n".join(rows)
        + "\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the doc is stale")
    args = parser.parse_args()
    content = build()
    if args.check:
        current = DOC_PATH.read_text() if DOC_PATH.exists() else ""
        if current != content:
            print(f"{DOC_PATH} is stale; run scripts/generate-tool-hitl-inventory.py")
            return 1
        return 0
    DOC_PATH.write_text(content)
    print(f"wrote {DOC_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
