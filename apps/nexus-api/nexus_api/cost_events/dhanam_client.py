"""POST ``cost.event.v1`` batches to Dhanam with a Janua machine token.

``POST {DHANAM_API_URL}/v1/cost-events`` with ``{"events": [...]}`` (1–500),
``Authorization: Bearer`` a Janua ``client_credentials`` token (audience
``dhanam-api``, scope ``dhanam-cost-events:write``). Dhanam validates the batch
all-or-nothing and is idempotent on ``(source, id)``; its writer grant binds
this client to ONE space and the source ``selva``.

What each answer means here (the Karafiel emitter's mapping):

* 2xx — every event is stored (created / updated / unchanged).
* 400 — nothing stored. Only per-index error CODES are kept (the field a
  message names), never a message or a payload.
* 401 — forget the token, take a fresh one, retry ONCE; twice is ``unauthorized``.
* 403 — no writer grant binds this client to source ``selva``: operator problem.
* 409 — an event id already belongs to another space: operator problem.
* 429 / 5xx / network / Janua down — ``transient``: back off, retry next sweep.

Nothing logged here carries a token, a secret or a response body.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import httpx

from .config import SCOPE, CostEventsConfig

logger = logging.getLogger(__name__)

MAX_BATCH = 500
TIMEOUT_SECONDS = 30.0
#: Replace a cached token this long before it expires.
TOKEN_REFRESH_MARGIN_S = 60.0
USER_AGENT = "selva-nexus-api/cost-events"

OK = "ok"
REJECTED = "rejected"
UNAUTHORIZED = "unauthorized"
FORBIDDEN = "forbidden"
CONFLICT = "conflict"
TRANSIENT = "transient"
UNEXPECTED = "unexpected"

#: Outcomes after which no further batch is attempted in the same run.
STOPS_RUN = frozenset({UNAUTHORIZED, FORBIDDEN, CONFLICT, TRANSIENT, UNEXPECTED})
#: Outcomes an operator must fix (the sweep exits non-zero on them).
ALERTS = frozenset({UNAUTHORIZED, FORBIDDEN, CONFLICT, UNEXPECTED})

_CODE_RE = re.compile(r"[^a-z0-9_.]")


@dataclass
class BatchResult:
    outcome: str
    status_code: int | None = None
    error_code: str = ""
    #: 400 only: batch index → sorted error codes for that event.
    index_errors: dict[int, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.outcome == OK


class TokenUnavailableError(RuntimeError):
    """Janua did not issue a token. The message carries a code, never a secret."""


def error_code(message: str) -> str:
    """The stable part of one Dhanam validation message: the field it names."""
    text = (message or "").strip().lower()
    if text.startswith("unknown field"):
        return "unknown_field"
    if text.startswith("duplicate"):
        return "duplicate_id"
    head = text.split(" ", 1)[0] if text else "unspecified"
    return _CODE_RE.sub("", head)[:40] or "unspecified"


def _index_errors(response: httpx.Response) -> dict[int, list[str]]:
    try:
        body = response.json()
    except ValueError:
        return {}
    errors = body.get("errors") if isinstance(body, dict) else None
    out: dict[int, list[str]] = {}
    for entry in errors if isinstance(errors, list) else []:
        if not isinstance(entry, dict) or not isinstance(entry.get("index"), int):
            continue
        raw = entry.get("errors")
        messages: list[Any] = raw if isinstance(raw, list) else []
        codes = {error_code(str(m)) for m in messages} or {"unspecified"}
        out[entry["index"]] = sorted(set(out.get(entry["index"], [])) | codes)
    return out


def _seconds(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


class DhanamCostEventsClient:
    """One client per run. ``transport`` is injectable for tests (``httpx.MockTransport``)."""

    def __init__(
        self,
        cfg: CostEventsConfig,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._cfg = cfg
        self._transport = transport
        self._clock = clock
        self._token: tuple[str, float] | None = None

    def __repr__(self) -> str:
        return f"DhanamCostEventsClient(url={self._cfg.events_url!r})"

    def _http(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=TIMEOUT_SECONDS,
            transport=self._transport,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        )

    async def _get_token(self) -> str:
        cached = self._token
        if cached is not None and self._clock() < cached[1]:
            return cached[0]
        self._token = None
        try:
            async with self._http() as http:
                response = await http.post(
                    self._cfg.token_url,
                    data={"grant_type": "client_credentials", "scope": SCOPE},
                    auth=httpx.BasicAuth(self._cfg.client_id, self._cfg.client_secret),
                )
        except httpx.HTTPError as exc:
            # The exception holds the request, and the request the credentials.
            raise TokenUnavailableError(f"janua_unreachable_{type(exc).__name__}") from None
        if not response.is_success:
            raise TokenUnavailableError(f"janua_http_{response.status_code}")
        try:
            payload = response.json()
        except ValueError:
            raise TokenUnavailableError("janua_not_json") from None
        token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(token, str) or not token.strip():
            raise TokenUnavailableError("janua_no_access_token")
        lifetime = _seconds(payload.get("expires_in")) or 0.0
        self._token = (token.strip(), self._clock() + max(lifetime - TOKEN_REFRESH_MARGIN_S, 0.0))
        return token.strip()

    async def post_batch(self, events: list[dict[str, Any]]) -> BatchResult:
        """Send 1–500 events. Failures become a ``BatchResult``, never an exception."""
        if not events or len(events) > MAX_BATCH:
            raise ValueError(f"a batch holds 1–{MAX_BATCH} events")
        response: httpx.Response | None = None
        for attempt in (1, 2):
            try:
                token = await self._get_token()
            except TokenUnavailableError as exc:
                logger.warning("Dhanam cost events: no Janua token (%s)", exc)
                return BatchResult(TRANSIENT, error_code="token_unavailable")
            try:
                async with self._http() as http:
                    response = await http.post(
                        self._cfg.events_url,
                        json={"events": events},
                        headers={"Authorization": f"Bearer {token}"},
                    )
            except httpx.HTTPError as exc:
                logger.warning("Dhanam cost events: network error (%s)", type(exc).__name__)
                return BatchResult(TRANSIENT, error_code="network")
            if response.status_code != 401:
                break
            self._token = None
            if attempt == 2:
                logger.error(
                    "ALERT Dhanam cost events: 401 twice — Janua issues the token but "
                    "Dhanam refuses it (audience, org binding or key rotation)"
                )
                return BatchResult(UNAUTHORIZED, status_code=401, error_code="http_401")
        assert response is not None
        return self._interpret(response, len(events))

    def _interpret(self, response: httpx.Response, count: int) -> BatchResult:
        status = response.status_code
        if 200 <= status < 300:
            return BatchResult(OK, status_code=status)
        if status == 400:
            index_errors = _index_errors(response)
            codes = sorted({c for cs in index_errors.values() for c in cs})
            logger.warning(
                "Dhanam cost events: batch of %d rejected (400), %d invalid: %s",
                count,
                len(index_errors),
                ",".join(codes) or "no detail",
            )
            return BatchResult(
                REJECTED, status_code=400, error_code="http_400", index_errors=index_errors
            )
        if status in (403, 409):
            logger.error(
                "ALERT Dhanam cost events: HTTP %d — %s. Run stopped; rows stay pending.",
                status,
                "no writer grant binds this client to source selva"
                if status == 403
                else "an event id already belongs to another space",
            )
            return BatchResult(
                FORBIDDEN if status == 403 else CONFLICT,
                status_code=status,
                error_code=f"http_{status}",
            )
        if status == 429 or status >= 500:
            logger.warning("Dhanam cost events: HTTP %d, retrying on a later sweep", status)
            return BatchResult(TRANSIENT, status_code=status, error_code=f"http_{status}")
        logger.error("ALERT Dhanam cost events: unexpected HTTP %d; run stopped", status)
        return BatchResult(UNEXPECTED, status_code=status, error_code=f"http_{status}")
