"""A2A v1.0.1-compatible surface, served ALONGSIDE the legacy 0.7.0 dialect.

This module implements a second, additive Agent-to-Agent surface that speaks
the A2A **v1.0.1** wire contract so Selva agents can be observed and gated by
an external observability appservice. The legacy surface in
:mod:`selva_a2a.server` / :mod:`selva_a2a.schema` (dialect ``"0.7.0"``, card at
``/.well-known/agent.json``, REST-ish ``tasks/send``) is untouched and keeps
serving its existing consumers. Nothing here changes legacy behaviour.

The surface is inert unless the caller mounts :func:`create_a2a_v1_router`; the
nexus-api wiring keeps it behind an explicit feature gate (default OFF).

Wire contract
-------------
- Agent card at ``/.well-known/agent-card.json`` (v1.0.1 path). Protocol pinned
  to ``/v1.0.1/``; v1.0 card shape with an *ordered* ``supportedInterfaces``
  list, open-string ``protocolBinding``, no top-level ``id``, and
  ``capabilities.streaming`` (boolean) gating the SSE method.
- Task states are ProtoJSON SCREAMING_SNAKE_CASE (:class:`TaskState`). The
  v0.3 kebab-case spellings never appear on this surface.
- JSON-RPC 2.0 over HTTP POST at the versioned endpoint. Methods:
  ``message/send``, ``message/stream`` (SSE, only if ``capabilities.streaming``),
  ``tasks/get``, ``tasks/cancel``.

Points marked ``CHOICE:`` below were a defensible reading of the A2A v1.0
specification pending upstream verification. The counterpart observer
(``Moirai``) implements the SAME choice so the two sides interoperate; if the
upstream spec later disagrees, BOTH sides must change together. Points marked
``GROUNDED:`` are explicit in the observed contract.

State reachability (HONEST mapping — read this before extending)
---------------------------------------------------------------
A2A tasks are bridged into ``swarm_tasks`` rows (see
``apps/nexus-api/nexus_api/main.py`` ``_dispatch_a2a_task``). The persisted
``SwarmTask.status`` vocabulary is a *free* string, but every writer constrains
it to a small set:

- initial: ``"pending"`` (model default) / ``"queued"`` (set at dispatch,
  ``main.py``)
- worker writeback (``apps/workers/selva_workers/__main__.py`` +
  ``task_status.py``) and the ``PATCH /api/v1/swarms/tasks/{id}`` validator
  (``routers/swarms.py`` ``TaskStatusUpdate.status`` regex
  ``^(running|completed|failed|cancelled)$``) constrain it to:
  ``"running" | "completed" | "failed" | "cancelled"``.

So the A2A v1 task states **reachable today** are exactly:

- ``TASK_STATE_SUBMITTED`` — ``pending`` / ``queued``
- ``TASK_STATE_WORKING`` — ``running``
- ``TASK_STATE_COMPLETED`` — ``completed``
- ``TASK_STATE_FAILED`` — ``failed``
- ``TASK_STATE_CANCELED`` — ``cancelled``

The remaining states are DEFINED here (the v1 enum must be complete) but are
**not reachable** through Selva's current task machinery, and this surface never
fabricates a transition into them:

- ``TASK_STATE_INPUT_REQUIRED`` — Selva has **no human content-input pause**.
  The only human-pause mechanism is the LangGraph ``interrupt()`` permission
  gate (``docs/HITL_FLOW.md``), which is an *authorization* gate, not a request
  for content. There is no clarifying-question / "ask the user for more
  information" flow anywhere in the codebase.
- ``TASK_STATE_AUTH_REQUIRED`` — the closest real mechanism is the ``interrupt()``
  approval gate (``file_write`` / ``bash_execute`` / ``git_push`` /
  ``email_send`` / ``deploy`` → ``ApprovalRequest``). But that pause is held
  *inside the worker's LangGraph checkpoint* and is NEVER persisted as a
  distinct ``SwarmTask.status`` — the worker blocks in
  ``interrupt_handler.handle_interrupt`` until approved/denied, then writes only
  the terminal ``completed``/``failed`` back. Moreover, RFC 0018
  (``docs/rfcs/0018-a2a-external-tenant-model.md`` §2.1) specifies that A2A
  callers are **denied HITL approvals** ("no human on the other end"), so an
  A2A-bridged task cannot enter the approval pause at all today.
- ``TASK_STATE_REJECTED`` — no rejection path is persisted on the task record.
- ``TASK_STATE_UNSPECIFIED`` — the ProtoJSON zero value; used only as the
  fallback for a status string we do not recognise (defensive, not a real
  Selva transition).

The mapping in :func:`selva_status_to_task_state` is deliberately conservative:
it maps only the real, reachable states and falls back to
``TASK_STATE_UNSPECIFIED`` for anything unknown, rather than inventing an
``INPUT_REQUIRED`` / ``AUTH_REQUIRED`` transition that Selva never actually
makes. When Selva grows a real human-input or credential pause point, extend
the mapping here — do not add a parallel state machine.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# The protocol version this surface pins. Kept in one place so the card and any
# future version negotiation stay consistent. GROUNDED: the observer pins the
# same ``/v1.0.1/`` protocol string.
A2A_V1_PROTOCOL_VERSION = "/v1.0.1/"

# Path of the v1.0.1 agent card, relative to the router prefix. GROUNDED.
A2A_V1_AGENT_CARD_PATH = "/.well-known/agent-card.json"


class TaskState(StrEnum):
    """A2A v1 task states, ProtoJSON SCREAMING_SNAKE_CASE.

    All nine states from the A2A v1 ``TaskState`` proto enum are defined so the
    surface advertises the complete vocabulary. See the module docstring for
    which are reachable through Selva's current task machinery. GROUNDED: the
    observer decodes exactly these nine spellings; the v0.3 kebab-case
    spellings (``input-required`` etc.) MUST NOT appear on this surface.
    """

    UNSPECIFIED = "TASK_STATE_UNSPECIFIED"
    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    COMPLETED = "TASK_STATE_COMPLETED"
    FAILED = "TASK_STATE_FAILED"
    CANCELED = "TASK_STATE_CANCELED"
    REJECTED = "TASK_STATE_REJECTED"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    AUTH_REQUIRED = "TASK_STATE_AUTH_REQUIRED"


# Selva's persisted ``SwarmTask.status`` -> A2A v1 ``TaskState``.
#
# HONEST mapping: only the states Selva actually reaches are mapped (see the
# module docstring). ``INPUT_REQUIRED`` / ``AUTH_REQUIRED`` / ``REJECTED`` are
# intentionally ABSENT from the value set because no persisted Selva status
# reaches them today. Unknown/unmapped statuses fall through to
# ``UNSPECIFIED`` rather than being coerced into an interrupted state.
_SELVA_STATUS_TO_TASK_STATE: dict[str, TaskState] = {
    # initial / queued
    "pending": TaskState.SUBMITTED,
    "queued": TaskState.SUBMITTED,
    # running
    "running": TaskState.WORKING,
    # terminal
    "completed": TaskState.COMPLETED,
    "failed": TaskState.FAILED,
    "cancelled": TaskState.CANCELED,
    # US spelling tolerated defensively (some call sites/tests use it)
    "canceled": TaskState.CANCELED,
}

# Terminal A2A states. GROUNDED: duplicate terminal snapshots are tolerated as
# a no-op by both sides, so callers can compare against this set.
TERMINAL_TASK_STATES: frozenset[TaskState] = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED, TaskState.REJECTED}
)


def selva_status_to_task_state(status: str | None) -> TaskState:
    """Map a Selva ``SwarmTask.status`` string to an A2A v1 :class:`TaskState`.

    Falls back to :attr:`TaskState.UNSPECIFIED` for ``None`` or any status not
    in the known set — the surface never fabricates an ``INPUT_REQUIRED`` /
    ``AUTH_REQUIRED`` transition Selva does not actually make.
    """
    if not status:
        return TaskState.UNSPECIFIED
    return _SELVA_STATUS_TO_TASK_STATE.get(status.strip().lower(), TaskState.UNSPECIFIED)


# ---------------------------------------------------------------------------
# Card + task snapshot models
# ---------------------------------------------------------------------------


class AgentInterface(BaseModel):
    """One entry in the card's ordered ``supportedInterfaces`` list.

    CHOICE: the v1.0 card carries an ordered ``supportedInterfaces`` array of
    ``{url, protocolBinding}`` objects; ``protocolBinding`` is an open string
    (not a closed enum). The observer reads the list in order and takes the
    first binding it understands, so ORDER IS SIGNIFICANT — keep JSON-RPC first.
    """

    url: str
    protocol_binding: str = Field(serialization_alias="protocolBinding")

    model_config = {"populate_by_name": True}


class AgentCapabilities(BaseModel):
    """Card ``capabilities`` block.

    GROUNDED: ``streaming`` is a boolean that gates whether ``message/stream``
    (SSE) is offered. When ``False`` the method returns a JSON-RPC error.
    """

    streaming: bool = False


class AgentCardV1(BaseModel):
    """A2A v1.0.1 agent card served at ``/.well-known/agent-card.json``.

    CHOICE / GROUNDED (per field, see the module docstring):
    - ``protocolVersion`` pinned to ``/v1.0.1/`` (GROUNDED).
    - v1.0 card shape: NO top-level ``id`` field (CHOICE — v1.0 dropped it).
    - ``supportedInterfaces`` is an ORDERED list (CHOICE).
    - ``capabilities.streaming`` boolean gates SSE (GROUNDED).
    """

    protocol_version: str = Field(
        default=A2A_V1_PROTOCOL_VERSION,
        serialization_alias="protocolVersion",
    )
    name: str = "Selva Office"
    description: str = "AI-powered virtual office with autonomous agent swarms"
    version: str = "1.0.1"
    supported_interfaces: list[AgentInterface] = Field(
        default_factory=list,
        serialization_alias="supportedInterfaces",
    )
    capabilities: AgentCapabilities = Field(default_factory=AgentCapabilities)
    skills: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class TaskStatusV1(BaseModel):
    """The ``status`` member of a v1 Task snapshot.

    CHOICE: minimal ``{state, update}`` shape — ``state`` is the SCREAMING_SNAKE
    string, ``update`` is an optional human-readable progress line (the observer
    renders it verbatim when present).
    """

    state: TaskState
    update: str | None = None

    model_config = {"use_enum_values": True}


class TaskSnapshotV1(BaseModel):
    """A v1 Task snapshot.

    CHOICE: minimal ``{id, status: {state, update}}`` shape. ``tenant`` is
    included only when present so it can be echoed back (GROUNDED: the observer
    echoes ``tenant`` when it supplied one).
    """

    id: str
    status: TaskStatusV1
    tenant: str | None = None
    # Note: ``exclude_none`` is a ``model_dump()`` argument (passed in
    # ``_snapshot``), not a ConfigDict option — so it is NOT set here.


# ---------------------------------------------------------------------------
# Adapter callback signatures
# ---------------------------------------------------------------------------

# Create a task from an inbound ``message/send``. Receives the decoded message
# text (concatenated text parts), the raw data parts, and optional tenant.
# Returns the new task id. Async.
V1TaskCreator = Callable[["MessageSendParams"], Awaitable[str]]

# Look up a task snapshot by id. Returns (state, update-string-or-None) or
# ``None`` if the task does not exist. Async.
V1TaskGetter = Callable[[str], Awaitable[tuple[TaskState, str | None] | None]]

# Request cancellation of a task by id. Returns the resulting (state, update)
# after attempting cancellation, or ``None`` if the task does not exist. Async.
V1TaskCanceller = Callable[[str], Awaitable[tuple[TaskState, str | None] | None]]

# Provide the ordered interfaces + skills + streaming flag for the card.
V1CardProvider = Callable[[], AgentCardV1]


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 plumbing
# ---------------------------------------------------------------------------

# Standard JSON-RPC 2.0 error codes (https://www.jsonrpc.org/specification).
JSONRPC_PARSE_ERROR = -32700
JSONRPC_INVALID_REQUEST = -32600
JSONRPC_METHOD_NOT_FOUND = -32601
JSONRPC_INVALID_PARAMS = -32602
JSONRPC_INTERNAL_ERROR = -32603


def _rpc_result(req_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


class MessageSendParams:
    """Decoded params for ``message/send`` / ``message/stream``.

    A2A message Parts are proto3-oneof objects. CHOICE: each part is one of
    ``{"text": ...}`` / ``{"data": ...}`` / ``{"file": ...}``; role is
    ``ROLE_USER``. ``tenant`` (GROUNDED) is echoed back when present.

    This is a plain object (not a Pydantic model) so the adapter can read the
    already-split text/data/file parts without re-parsing the envelope.
    """

    __slots__ = ("text", "data_parts", "file_parts", "tenant", "raw")

    def __init__(
        self,
        *,
        text: str,
        data_parts: list[Any],
        file_parts: list[Any],
        tenant: str | None,
        raw: dict[str, Any],
    ) -> None:
        self.text = text
        self.data_parts = data_parts
        self.file_parts = file_parts
        self.tenant = tenant
        self.raw = raw


def _parse_message_params(params: dict[str, Any]) -> MessageSendParams:
    """Split an A2A v1 ``message/send`` params object into decoded parts.

    CHOICE: params carry ``{"message": {"role": "ROLE_USER", "parts": [...]}}``
    where each part is a proto3-oneof ``{"text"|"data"|"file": ...}``. A bare
    ``{"parts": [...]}`` (no ``message`` wrapper) is also accepted defensively.
    Raises :class:`ValueError` (→ INVALID_PARAMS) when no parts are present.
    """
    message = params.get("message")
    if not isinstance(message, dict):
        # Defensive: allow params to be the message itself.
        message = params
    parts = message.get("parts")
    if not isinstance(parts, list) or not parts:
        raise ValueError("message.parts must be a non-empty array")

    text_chunks: list[str] = []
    data_parts: list[Any] = []
    file_parts: list[Any] = []
    for part in parts:
        if not isinstance(part, dict):
            raise ValueError("each part must be an object")
        if "text" in part:
            text_chunks.append(str(part["text"]))
        elif "data" in part:
            data_parts.append(part["data"])
        elif "file" in part:
            file_parts.append(part["file"])
        else:
            raise ValueError("each part must have a text, data, or file member")

    # GROUNDED: tenant is echoed back when present. It may ride on the params
    # envelope or on the message.
    tenant = params.get("tenant")
    if tenant is None:
        tenant = message.get("tenant")
    tenant_str = str(tenant) if tenant is not None else None

    return MessageSendParams(
        text="\n".join(text_chunks),
        data_parts=data_parts,
        file_parts=file_parts,
        tenant=tenant_str,
        raw=message,
    )


def _extract_task_id(params: dict[str, Any]) -> str:
    """Pull the task id from ``tasks/get`` / ``tasks/cancel`` params.

    CHOICE: get/cancel params are ``{"id": "<task id>"}``. Raises
    :class:`ValueError` (→ INVALID_PARAMS) when absent/empty.
    """
    task_id = params.get("id")
    if not isinstance(task_id, str) or not task_id:
        raise ValueError('params must include a non-empty string "id"')
    return task_id


def _snapshot(task_id: str, state: TaskState, update: str | None, tenant: str | None) -> dict:
    """Build a serialised Task snapshot dict (enum → string)."""
    snap = TaskSnapshotV1(
        id=task_id,
        status=TaskStatusV1(state=state, update=update),
        tenant=tenant,
    )
    return snap.model_dump(mode="json", exclude_none=True)


# ---------------------------------------------------------------------------
# Router factory
# ---------------------------------------------------------------------------


def create_a2a_v1_router(
    *,
    prefix: str = "/a2a/v1",
    get_card: V1CardProvider,
    create_task: V1TaskCreator | None = None,
    get_task: V1TaskGetter | None = None,
    cancel_task: V1TaskCanceller | None = None,
    streaming: bool = False,
    stream_poll_interval_seconds: float = 2.0,
    stream_max_polls: int = 150,
) -> APIRouter:
    """Build a FastAPI router serving the A2A v1.0.1-compatible surface.

    Mounts, under ``prefix``:

    - ``GET  {prefix}/.well-known/agent-card.json`` — the v1.0.1 agent card.
    - ``POST {prefix}/`` — the JSON-RPC 2.0 endpoint (``message/send``,
      ``message/stream`` [if ``streaming``], ``tasks/get``, ``tasks/cancel``).

    This is purely additive: it never touches the legacy router. The caller is
    responsible for only mounting it when the feature gate is on.

    Parameters
    ----------
    get_card:
        Returns the :class:`AgentCardV1` to serve. Called per request so the
        card can reflect live skills. The card's ``capabilities.streaming`` is
        reconciled with the ``streaming`` argument below.
    create_task:
        Async callback creating a task from a decoded message; returns task id.
        Required for ``message/send`` / ``message/stream``.
    get_task:
        Async callback returning ``(state, update)`` or ``None`` for a task id.
        Required for ``tasks/get`` and for ``message/stream`` polling.
    cancel_task:
        Async callback requesting cancellation; returns ``(state, update)`` or
        ``None``. Required for ``tasks/cancel``.
    streaming:
        When ``True``, ``message/stream`` is offered (and the card advertises
        ``capabilities.streaming = true``). When ``False`` the method returns a
        JSON-RPC error and the card advertises ``streaming = false``.
    """
    router = APIRouter(prefix=prefix, tags=["A2A v1"])

    @router.get(A2A_V1_AGENT_CARD_PATH)
    async def agent_card_v1() -> JSONResponse:
        """Serve the v1.0.1 agent card (ordered interfaces, pinned version)."""
        card = get_card()
        # Reconcile the streaming capability with what this router actually
        # offers so the card never over-advertises.
        card.capabilities.streaming = streaming
        return JSONResponse(card.model_dump(mode="json", by_alias=True))

    async def _handle_message_send(req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        if create_task is None:
            return _rpc_error(req_id, JSONRPC_INTERNAL_ERROR, "task creation not configured")
        try:
            parsed = _parse_message_params(params)
        except ValueError as exc:
            return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, str(exc))
        try:
            task_id = await create_task(parsed)
        except Exception:
            logger.exception("A2A v1 message/send task creation failed")
            return _rpc_error(req_id, JSONRPC_INTERNAL_ERROR, "task creation error")
        # A freshly created task is SUBMITTED. GROUNDED: tenant echoed back.
        return _rpc_result(
            req_id,
            _snapshot(task_id, TaskState.SUBMITTED, None, parsed.tenant),
        )

    async def _handle_tasks_get(req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        if get_task is None:
            return _rpc_error(req_id, JSONRPC_INTERNAL_ERROR, "task lookup not configured")
        try:
            task_id = _extract_task_id(params)
        except ValueError as exc:
            return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, str(exc))
        tenant = params.get("tenant")
        tenant_str = str(tenant) if tenant is not None else None
        try:
            found = await get_task(task_id)
        except Exception:
            logger.exception("A2A v1 tasks/get lookup failed for %s", task_id)
            return _rpc_error(req_id, JSONRPC_INTERNAL_ERROR, "task lookup error")
        if found is None:
            # Not-found is a JSON-RPC error, not a fabricated snapshot.
            return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, f"task not found: {task_id}")
        state, update = found
        return _rpc_result(req_id, _snapshot(task_id, state, update, tenant_str))

    async def _handle_tasks_cancel(req_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        if cancel_task is None:
            return _rpc_error(req_id, JSONRPC_INTERNAL_ERROR, "task cancellation not configured")
        try:
            task_id = _extract_task_id(params)
        except ValueError as exc:
            return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, str(exc))
        tenant = params.get("tenant")
        tenant_str = str(tenant) if tenant is not None else None
        try:
            found = await cancel_task(task_id)
        except Exception:
            logger.exception("A2A v1 tasks/cancel failed for %s", task_id)
            return _rpc_error(req_id, JSONRPC_INTERNAL_ERROR, "task cancellation error")
        if found is None:
            return _rpc_error(req_id, JSONRPC_INVALID_PARAMS, f"task not found: {task_id}")
        state, update = found
        return _rpc_result(req_id, _snapshot(task_id, state, update, tenant_str))

    async def _stream_events(
        task_id: str, tenant: str | None
    ) -> AsyncGenerator[str, None]:
        """SSE generator: poll task state and emit snapshots until terminal.

        GROUNDED: duplicate terminal snapshots are tolerated as a no-op, so the
        generator emits one final terminal snapshot and stops; if polling never
        resolves within the bound it stops without inventing a state.
        """
        import asyncio

        last_state: TaskState | None = None
        # Emit an initial SUBMITTED snapshot immediately so the observer has the
        # task id even before the first poll resolves.
        yield f"data: {json.dumps(_snapshot(task_id, TaskState.SUBMITTED, None, tenant))}\n\n"
        last_state = TaskState.SUBMITTED

        for _ in range(stream_max_polls):
            await asyncio.sleep(stream_poll_interval_seconds)
            if get_task is None:
                return
            try:
                found = await get_task(task_id)
            except Exception:
                logger.debug("A2A v1 stream poll error for %s", task_id, exc_info=True)
                continue
            if found is None:
                continue
            state, update = found
            if state != last_state:
                yield f"data: {json.dumps(_snapshot(task_id, state, update, tenant))}\n\n"
                last_state = state
            if state in TERMINAL_TASK_STATES:
                return

    # Dispatch table for non-streaming JSON-RPC methods.
    methods: dict[str, Callable[[Any, dict[str, Any]], Awaitable[dict[str, Any]]]] = {
        "message/send": _handle_message_send,
        "tasks/get": _handle_tasks_get,
        "tasks/cancel": _handle_tasks_cancel,
    }

    @router.post("/")
    async def json_rpc(request: Request) -> Any:
        """A2A v1 JSON-RPC 2.0 endpoint."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(_rpc_error(None, JSONRPC_PARSE_ERROR, "parse error"))

        if not isinstance(body, dict):
            return JSONResponse(_rpc_error(None, JSONRPC_INVALID_REQUEST, "invalid request"))

        req_id = body.get("id")
        if body.get("jsonrpc") != "2.0" or not isinstance(body.get("method"), str):
            return JSONResponse(
                _rpc_error(req_id, JSONRPC_INVALID_REQUEST, "invalid JSON-RPC 2.0 request")
            )

        method = body["method"]
        params = body.get("params") or {}
        if not isinstance(params, dict):
            return JSONResponse(_rpc_error(req_id, JSONRPC_INVALID_PARAMS, "params must be object"))

        # message/stream is SSE and only offered when streaming is enabled.
        if method == "message/stream":
            if not streaming:
                return JSONResponse(
                    _rpc_error(req_id, JSONRPC_METHOD_NOT_FOUND, "streaming not supported")
                )
            if create_task is None:
                return JSONResponse(
                    _rpc_error(req_id, JSONRPC_INTERNAL_ERROR, "task creation not configured")
                )
            try:
                parsed = _parse_message_params(params)
            except ValueError as exc:
                return JSONResponse(_rpc_error(req_id, JSONRPC_INVALID_PARAMS, str(exc)))
            try:
                task_id = await create_task(parsed)
            except Exception:
                logger.exception("A2A v1 message/stream task creation failed")
                return JSONResponse(
                    _rpc_error(req_id, JSONRPC_INTERNAL_ERROR, "task creation error")
                )
            return StreamingResponse(
                _stream_events(task_id, parsed.tenant),
                media_type="text/event-stream",
            )

        handler = methods.get(method)
        if handler is None:
            return JSONResponse(
                _rpc_error(req_id, JSONRPC_METHOD_NOT_FOUND, f"method not found: {method}")
            )
        return JSONResponse(await handler(req_id, params))

    return router
