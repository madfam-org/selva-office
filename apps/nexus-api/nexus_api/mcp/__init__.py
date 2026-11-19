"""Selva's native MCP: read-only COGS tools for agents (RFC 0051 Phase A).

``POST /mcp`` on the API host (``https://api.selva.town/mcp``), Streamable
HTTP, JSON-RPC 2.0, stateless (no sessions, no SSE stream: every request gets
one JSON answer). Behind ``SELVA_MCP_ENABLED`` (default off; the route answers
404 until the owner turns it on).

Who may call
============
Janua machine tokens only (``client_credentials``, ``sub`` =
``service-account:<client>``), audience = Selva's API audience
(``JANUA_CLIENT_ID``, the same ``auth.verify_jwt`` decode as every route),
scope ``selva-cogs:read``, and the client bound to a Janua organization
(``org_id`` claim). The org is the token's; the ``org`` argument may only name
it. People (Phase B, RFC 8707 protected resource) are refused for now.

No back door
============
``inference_usage`` runs the function behind ``GET
/api/v1/billing/inference-usage`` (``services.inference_usage_report``) in an
RLS-scoped ``tenant_session`` for the token's org. There are no write tools.
``coverage.py`` lists every billing / usage / provider route as covered or
exempted with a reason; ``tests/test_mcp_coverage.py`` fails on a new route
that is neither.

Modules: ``protocol`` (JSON-RPC / MCP), ``registry`` (tool specs, argument
checks), ``tools`` (the tool), ``router`` (HTTP, auth, rate limit, audit
line), ``coverage`` (the contract).
"""
