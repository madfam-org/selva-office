"""Credential redaction for connection URLs / DSNs in logs and error messages.

Connection strings such as ``redis://:<password>@host:6379/8`` or
``postgresql://user:<password>@host/db`` carry the credential in the URL
userinfo. Logging one verbatim hands the password to anyone with log access
(``kubectl logs``, any log shipper). This module provides:

* :func:`redact_url` -- mask the password of ONE connection URL while keeping
  scheme, username, host, port, path (DB index) and query. Use it at every call
  site that logs or echoes a URL.
* :func:`redact_text` -- mask every ``scheme://user:pass@`` (and the
  percent-encoded ``scheme%3A%2F%2Fuser%3Apass%40``) occurrence inside an
  arbitrary string, e.g. an exception message.
* :func:`redact_credentials_processor` -- a structlog processor that applies
  :func:`redact_text` to every string in the event dict. ``configure_logging``
  installs it as defense in depth, so a call site that forgets
  :func:`redact_url` still cannot leak the password.

Rules (fail towards over-masking, never under-masking):

* ``user:pass@`` -> ``user:***@`` (username kept: it is not a secret and helps
  debugging).
* ``:pass@`` (password-only, the Redis form) -> ``:***@``.
* ``token@`` (userinfo without a colon) -> ``***@``: several clients put the
  whole credential in the username slot (e.g. ``https://<token>@host``).
* An unencoded ``@`` inside the password is handled: the authority's LAST
  ``@`` separates userinfo from host, exactly like ``urllib.parse``.
"""

from __future__ import annotations

import re
from collections.abc import MutableMapping
from typing import Any

MASK = "***"

# scheme://<authority> where authority runs until whitespace or / ? #.
# The greedy authority group backtracks to the LAST "@" before the path, so a
# raw "@" inside a password is masked together with the rest of it.
_URL_USERINFO_RE = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*://)(?P<userinfo>[^\s/?#]*)@",
)

# Percent-encoded URL (e.g. a DSN passed as a query-string value):
# scheme%3A%2F%2F<encoded authority...>. The value ends at whitespace, "&",
# quotes or a raw delimiter; the authority itself ends at %2F / %3F / %23.
_ENCODED_URL_RE = re.compile(
    r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*)%3A%2F%2F(?P<rest>[^\s&/?#\"'<>]*)",
    re.IGNORECASE,
)
_ENCODED_AUTHORITY_END_RE = re.compile(r"%2F|%3F|%23", re.IGNORECASE)
_ENCODED_AT_RE = re.compile(r"%40", re.IGNORECASE)
_ENCODED_COLON_RE = re.compile(r"%3A", re.IGNORECASE)

_MAX_DEPTH = 6


def _mask_userinfo(userinfo: str) -> str:
    user, sep, _password = userinfo.partition(":")
    if sep:
        return f"{user}:{MASK}"
    return MASK


def _sub_plain(match: re.Match[str]) -> str:
    return f"{match.group('scheme')}{_mask_userinfo(match.group('userinfo'))}@"


def _sub_encoded(match: re.Match[str]) -> str:
    scheme = match.group("scheme")
    rest = match.group("rest")
    end = _ENCODED_AUTHORITY_END_RE.search(rest)
    authority, tail = (rest[: end.start()], rest[end.start() :]) if end else (rest, "")
    ats = list(_ENCODED_AT_RE.finditer(authority))
    if not ats:
        return match.group(0)
    last_at = ats[-1]
    userinfo = authority[: last_at.start()]
    hostport = authority[last_at.start() :]  # keeps the "%40" separator
    colon = _ENCODED_COLON_RE.search(userinfo)
    masked = f"{userinfo[: colon.start()]}%3A{MASK}" if colon else MASK
    return f"{scheme}%3A%2F%2F{masked}{hostport}{tail}"


def redact_text(text: str) -> str:
    """Mask every credential-bearing URL userinfo found inside ``text``."""
    if "@" not in text and "%40" not in text:  # fast path: no userinfo possible
        return text
    if "%" in text:
        text = _ENCODED_URL_RE.sub(_sub_encoded, text)
    return _URL_USERINFO_RE.sub(_sub_plain, text)


def redact_url(url: str | None) -> str:
    """Return ``url`` with its userinfo password masked; safe to log.

    Keeps scheme, username, host, port, path (e.g. the Redis DB index) and
    query: ``redis://:pw@redis.data.svc.cluster.local:6379/8`` ->
    ``redis://:***@redis.data.svc.cluster.local:6379/8``.

    A value with no ``scheme://`` but an ``@`` (a misconfigured DSN such as
    ``user:pw@host/db``) is masked up to its last ``@``. ``None`` -> ``""``.
    """
    if not url:
        return ""
    redacted = redact_text(url)
    if "://" not in redacted and "@" in redacted:
        _userinfo, _at, host = redacted.rpartition("@")
        return f"{MASK}@{host}"
    return redacted


def _redact_value(value: Any, depth: int) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if depth >= _MAX_DEPTH or value is None or isinstance(value, bool | int | float):
        return value
    if isinstance(value, dict):
        return {k: _redact_value(v, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(v, depth + 1) for v in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(v, depth + 1) for v in value)
    # Arbitrary objects are rendered with repr() by the JSON/console
    # renderers. Only substitute the redacted repr when it actually contained
    # a credential, so every other value renders byte-for-byte as before.
    try:
        rendered = repr(value)
    except Exception:  # noqa: BLE001 -- a broken __repr__ must not kill logging
        return value
    redacted = redact_text(rendered)
    return redacted if redacted != rendered else value


def redact_credentials_processor(
    logger: Any,
    method_name: str,
    event_dict: MutableMapping[str, Any],
) -> MutableMapping[str, Any]:
    """structlog processor: mask ``scheme://user:pass@`` in every event value.

    Runs for structlog-native events and for stdlib ``logging`` records routed
    through ``ProcessorFormatter`` (whose message is already %-formatted into
    ``event``), so ``logger.info("Connected to %s", url)`` is covered too.
    """
    for key, value in list(event_dict.items()):
        event_dict[key] = _redact_value(value, 0)
    return event_dict
