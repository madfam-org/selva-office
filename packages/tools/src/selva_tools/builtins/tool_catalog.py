"""Self-introspection tools — let agents discover their own capabilities.

Phase 4 of the SELVA_TOOL_COVERAGE_PLAN. Motivating gap: at several points
during the 2026-04-17 session the swarm hit a situation where the right
next move was 'find the tool that does X', but the agent had no way to
ask 'what tools do I have that can do X?' beyond string-matching against
the static system prompt. These tools turn the tool registry into a
first-class, queryable catalog.

Queries are executed against the global ``ToolRegistry`` singleton. They
are pure reads — they never register, overwrite, or call any tool. A
``search_tools_by_capability`` query is a simple lexical rank (substring
+ docstring keyword weight) — deliberately non-semantic so the agent
gets deterministic, auditable results. A follow-up Phase 5 milestone
can layer FAISS over this if we need richer retrieval.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from ..base import BaseTool, ToolResult
from ..registry import get_tool_registry

logger = logging.getLogger(__name__)


# Category assignments — intentionally coarse. We extract the module
# name from a tool's class (``t.__class__.__module__``) and map the last
# segment to a human-friendly category label.
_CATEGORY_MAP: dict[str, str] = {
    "files": "file_ops",
    "code": "code_execution",
    "git": "vcs",
    "web": "web",
    "http_tools": "web",
    "data": "data",
    "communication": "communication",
    "email_tools": "communication",
    "marketing_tools": "communication",
    "slack": "communication",
    "whatsapp": "communication",
    "calendar_tools": "calendar",
    "database_tools": "database",
    "document_tools": "documents",
    "image_analysis": "multimodal",
    "stt": "multimodal",
    "media_tools": "multimodal",
    "artifact": "storage",
    "environment": "environment",
    "deploy": "infrastructure",
    "enclii_infra": "infrastructure",
    "argocd": "infrastructure",
    "k8s_diagnostics": "infrastructure",
    "k8s_configmap": "infrastructure",
    "k8s_secret": "infrastructure",
    "kustomize": "infrastructure",
    "backup_ops": "infrastructure",
    "dns": "infrastructure",
    "cloudflare": "infrastructure",
    "cloudflare_tunnel": "infrastructure",
    "cloudflare_r2": "infrastructure",
    "cloudflare_saas": "infrastructure",
    "vault": "infrastructure",
    "github_admin": "infrastructure",
    "npm_registry": "infrastructure",
    "webhooks": "infrastructure",
    "accounting": "accounting",
    "karafiel": "accounting",
    "legal": "legal",
    "privacy": "legal",
    "billing_tools": "billing",
    "crm_tools": "crm",
    "intelligence": "intelligence",
    "operations": "operations",
    "erp": "operations",
    "phygital_tools": "phygital",
    "pricing_intel": "pricing",
    "product_catalog": "pricing",
    "meta_harness": "meta",
    "hitl_introspection": "meta",
    "tool_catalog": "meta",
    "factory_manifest": "meta",
    "skill_performance": "meta",
    "a2a_tool": "meta",
    "extra_tools": "meta",
    "process_registry": "meta",
    "execute_code": "code_execution",
}


def _categorize(tool: BaseTool) -> str:
    mod = tool.__class__.__module__ or ""
    last = mod.rsplit(".", 1)[-1]
    return _CATEGORY_MAP.get(last, "other")


def _describe_one(tool: BaseTool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "category": _categorize(tool),
        "module": tool.__class__.__module__,
    }


class ListMyToolsTool(BaseTool):
    """List all tools available to the agent, optionally filtered."""

    name = "list_my_tools"
    description = (
        "List all tools registered in the agent's tool registry. Optional "
        "filters: ``category_filter`` (exact match on the derived category "
        "label, e.g. 'infrastructure', 'communication'); ``name_pattern`` "
        "(regex tested against the tool name). Results are sorted by name. "
        "Use this before asking the operator to add a capability — you "
        "probably already have it."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "category_filter": {"type": "string"},
                "name_pattern": {"type": "string"},
            },
            "required": [],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            reg = get_tool_registry()
            category = kwargs.get("category_filter")
            pattern_src = kwargs.get("name_pattern")
            pattern = None
            if pattern_src:
                try:
                    pattern = re.compile(str(pattern_src))
                except re.error as e:
                    return ToolResult(
                        success=False,
                        error=f"invalid name_pattern regex: {e}",
                    )
            names = reg.list_tools()
            items: list[dict[str, Any]] = []
            for n in names:
                t = reg.get(n)
                if t is None:
                    continue
                cat = _categorize(t)
                if category and cat != category:
                    continue
                if pattern and not pattern.search(n):
                    continue
                items.append(
                    {
                        "name": n,
                        "description": t.description,
                        "category": cat,
                    }
                )
            return ToolResult(
                success=True,
                output=f"found {len(items)} matching tools",
                data={"tools": items, "total_registered": len(names)},
            )
        except Exception as e:
            logger.error("list_my_tools failed: %s", e)
            return ToolResult(success=False, error=str(e))


class SearchToolsByCapabilityTool(BaseTool):
    """Rank tools by how well their name + description match a text query."""

    name = "search_tools_by_capability"
    description = (
        "Rank the registered tools by how well they match a free-text "
        "capability query. Scoring is intentionally simple: name-substring "
        "match scores higher than description-keyword match, so queries "
        "like 'send email' preferentially surface tools literally named "
        "'send_email'. Returns up to ``limit`` matches with their score."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {
                    "type": "integer",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 50,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            query = str(kwargs["query"]).strip()
            if not query:
                return ToolResult(success=False, error="empty query")
            limit = int(kwargs.get("limit", 10))
            q_lower = query.lower()
            # Tokenise on non-word chars; keep tokens of length >= 2.
            tokens = [t for t in re.split(r"\W+", q_lower) if len(t) >= 2]
            reg = get_tool_registry()
            ranked: list[tuple[float, dict[str, Any]]] = []
            for name in reg.list_tools():
                t = reg.get(name)
                if t is None:
                    continue
                desc_lower = (t.description or "").lower()
                name_lower = name.lower()
                score = 0.0
                if q_lower in name_lower:
                    score += 5.0
                if q_lower in desc_lower:
                    score += 2.0
                for tok in tokens:
                    if tok in name_lower:
                        score += 1.5
                    if tok in desc_lower:
                        score += 0.5
                if score > 0:
                    ranked.append(
                        (
                            score,
                            {
                                "name": name,
                                "description": t.description,
                                "score": round(score, 2),
                                "category": _categorize(t),
                            },
                        )
                    )
            ranked.sort(key=lambda item: (-item[0], item[1]["name"]))
            top = [item[1] for item in ranked[:limit]]
            return ToolResult(
                success=True,
                output=f"top {len(top)} matches for query={query!r}",
                data={"matches": top, "query": query},
            )
        except Exception as e:
            logger.error("search_tools_by_capability failed: %s", e)
            return ToolResult(success=False, error=str(e))


class DescribeToolTool(BaseTool):
    """Return a full description of one tool: params schema + docstring."""

    name = "describe_tool"
    description = (
        "Return the full description of a single tool by name: its "
        "description string, JSON Schema for parameters, category, and "
        "the class docstring. Use after ``search_tools_by_capability`` "
        "returns a candidate to verify the call contract before invoking."
    )

    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
            },
            "required": ["name"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        try:
            tname = str(kwargs["name"])
            reg = get_tool_registry()
            t = reg.get(tname)
            if t is None:
                return ToolResult(
                    success=False,
                    error=f"tool {tname!r} not found in registry",
                )
            try:
                schema = t.parameters_schema()
            except Exception as e:
                return ToolResult(
                    success=False,
                    error=f"tool {tname!r} parameters_schema() raised: {e}",
                )
            docstring = (t.__class__.__doc__ or "").strip() or None
            data = {
                **_describe_one(t),
                "parameters_schema": schema,
                "docstring": docstring,
            }
            return ToolResult(
                success=True,
                output=f"described {tname}",
                data=data,
            )
        except Exception as e:
            logger.error("describe_tool failed: %s", e)
            return ToolResult(success=False, error=str(e))


def get_tool_catalog_tools() -> list[BaseTool]:
    """Return the self-catalog tool set."""
    return [
        ListMyToolsTool(),
        SearchToolsByCapabilityTool(),
        DescribeToolTool(),
    ]
