"""Tool-name-to-action-category classifier for the HITL permission system."""

from __future__ import annotations

from .engine import PermissionEngine
from .tool_policy import BUILTIN_TOOL_CATEGORY_MAP
from .types import ActionCategory, PermissionResult

# HTTP methods that only read. Anything else on a generic HTTP tool is an
# external write and must be approved.
_READ_ONLY_HTTP_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class ActionClassifier:
    """Maps tool invocation names to permission action categories.

    Resolution order:

    1. Generic HTTP tools (``http_request``, ``graphql_query``) are
       classified from their params: reads stay ``API_CALL``, writes
       become ``EXTERNAL_WRITE``.
    2. ``TOOL_CATEGORY_MAP`` (generic tool names).
    3. ``BUILTIN_TOOL_CATEGORY_MAP`` -- the explicit per-tool policy for
       every built-in Selva tool (``selva_permissions.tool_policy``).
    4. Substring heuristics (``_FALLBACK_RULES``).
    5. ``UNCLASSIFIED_TOOL`` (ASK) for unrecognised tools.
    """

    TOOL_CATEGORY_MAP: dict[str, ActionCategory] = {
        # Shell / execution
        "bash": ActionCategory.BASH_EXECUTE,
        "shell": ActionCategory.BASH_EXECUTE,
        "terminal": ActionCategory.BASH_EXECUTE,
        "exec": ActionCategory.BASH_EXECUTE,
        # File read
        "read_file": ActionCategory.FILE_READ,
        "cat": ActionCategory.FILE_READ,
        "head": ActionCategory.FILE_READ,
        "tail": ActionCategory.FILE_READ,
        "less": ActionCategory.FILE_READ,
        # File write
        "write_file": ActionCategory.FILE_WRITE,
        "edit": ActionCategory.FILE_WRITE,
        "create_file": ActionCategory.FILE_WRITE,
        "patch": ActionCategory.FILE_WRITE,
        # Git
        "git_commit": ActionCategory.GIT_COMMIT,
        "git_push": ActionCategory.GIT_PUSH,
        # Email
        "send_email": ActionCategory.EMAIL_SEND,
        "email": ActionCategory.EMAIL_SEND,
        # CRM
        "crm_update": ActionCategory.CRM_UPDATE,
        "salesforce": ActionCategory.CRM_UPDATE,
        "hubspot": ActionCategory.CRM_UPDATE,
        # Deploy
        "deploy": ActionCategory.DEPLOY,
        "deploy_trigger": ActionCategory.DEPLOY,
        "deploy_status": ActionCategory.DEPLOY,
        "kubectl": ActionCategory.DEPLOY,
        "terraform": ActionCategory.DEPLOY,
        # Side-effecting factory-line tools whose names match no fallback
        # substring and would otherwise default to API_CALL (= ALLOW).
        # ``generate_quote`` creates a Cotiza quote record (a priced
        # commitment), so it is gated like any pricing proposal;
        # ``factory_manifest_publish`` writes files ("publish" does not
        # contain "push" or "write"). Both resolve to ASK by default.
        "generate_quote": ActionCategory.PRICING_PROPOSAL,
        "factory_manifest_publish": ActionCategory.FILE_WRITE,
        # API / HTTP
        "http_request": ActionCategory.API_CALL,
        "fetch": ActionCategory.API_CALL,
        "curl": ActionCategory.API_CALL,
    }

    # Ordered list of (substring, category) for fallback heuristics.
    # Order matters: more specific substrings should come first.
    _FALLBACK_RULES: list[tuple[str, ActionCategory]] = [
        ("push", ActionCategory.GIT_PUSH),
        ("commit", ActionCategory.GIT_COMMIT),
        ("deploy", ActionCategory.DEPLOY),
        ("write", ActionCategory.FILE_WRITE),
        ("create", ActionCategory.FILE_WRITE),
        ("edit", ActionCategory.FILE_WRITE),
        ("read", ActionCategory.FILE_READ),
        ("email", ActionCategory.EMAIL_SEND),
        ("mail", ActionCategory.EMAIL_SEND),
        ("crm", ActionCategory.CRM_UPDATE),
        ("bash", ActionCategory.BASH_EXECUTE),
        ("shell", ActionCategory.BASH_EXECUTE),
        ("exec", ActionCategory.BASH_EXECUTE),
    ]

    def classify(
        self,
        tool_name: str,
        params: dict | None = None,
    ) -> ActionCategory:
        """Classify a tool invocation into an action category.

        Args:
            tool_name: The name of the tool being invoked.
            params: Optional parameters (reserved for future context-aware
                    classification, e.g. distinguishing ``git status`` from
                    ``git push``).

        Returns:
            The ``ActionCategory`` matching the tool.
        """
        normalised = tool_name.strip().lower()

        # Generic HTTP tools: the method / operation decides read vs write.
        http_category = self._classify_http(normalised, params)
        if http_category is not None:
            return http_category

        # Exact match
        if normalised in self.TOOL_CATEGORY_MAP:
            return self.TOOL_CATEGORY_MAP[normalised]

        # Explicit per-tool policy for built-in tools.
        if normalised in BUILTIN_TOOL_CATEGORY_MAP:
            return BUILTIN_TOOL_CATEGORY_MAP[normalised]

        # Substring heuristics
        for substring, category in self._FALLBACK_RULES:
            if substring in normalised:
                return category

        # Fail closed: an unrecognised tool needs a human until it is given
        # an explicit entry in tool_policy.BUILTIN_TOOL_POLICY.
        return ActionCategory.UNCLASSIFIED_TOOL

    @staticmethod
    def _classify_http(normalised: str, params: dict | None) -> ActionCategory | None:
        """Classify generic HTTP tools from their arguments.

        Returns ``None`` for any other tool. Without params the historical
        ``API_CALL`` is kept (both tools default to a read).
        """
        if normalised == "http_request":
            method = str((params or {}).get("method") or "GET").strip().upper()
            if method in _READ_ONLY_HTTP_METHODS:
                return ActionCategory.API_CALL
            return ActionCategory.EXTERNAL_WRITE
        if normalised == "graphql_query":
            query = str((params or {}).get("query") or "")
            # Skip leading blank and comment lines before the operation type.
            lines = [ln.strip().lower() for ln in query.splitlines()]
            body = next((ln for ln in lines if ln and not ln.startswith("#")), "")
            if body.startswith(("mutation", "subscription")):
                return ActionCategory.EXTERNAL_WRITE
            return ActionCategory.API_CALL
        return None

    def classify_and_evaluate(
        self,
        tool_name: str,
        params: dict | None = None,
        engine: PermissionEngine | None = None,
    ) -> PermissionResult:
        """Classify a tool invocation and immediately evaluate its permission.

        Convenience method combining classification with engine evaluation.

        Args:
            tool_name: The name of the tool being invoked.
            params: Optional tool parameters.
            engine: A ``PermissionEngine`` instance. If ``None`` a default
                    engine is constructed.

        Returns:
            A ``PermissionResult`` for the classified action.
        """
        category = self.classify(tool_name, params)
        permission_engine = engine or PermissionEngine()
        return permission_engine.evaluate(category)
