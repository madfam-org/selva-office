"""A cheap, blunt server-side check for obvious direct identifiers.

Defense in depth for the pseudonymized-task exception
(:class:`madfam_inference.tenant_policy.TaskException`). The CLIENT
pseudonymizes the payload and attests it; this is the gateway's own last look
before a cloud provider sees the text. It finds only identifiers with a fixed
shape:

- e-mail addresses;
- phone numbers (10 to 15 digits, optional ``+`` / ``00`` country code and the
  usual separators);
- Mexican CURP (18 characters);
- Mexican RFC with homoclave (12 or 13 characters);

and it flags any non-text content, because an image cannot be checked.

It cannot find a NAME, and it does not try to: that is the client's
pseudonymization, and a heuristic name detector would refuse ordinary prose
while still missing names. It returns the KINDS it found, never the matched
text, so no caller can log an identifier by accident.

Every pattern is bounded (no unbounded nested repetition), so the scan stays
linear in the size of the payload.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

EMAIL = "email"
PHONE = "phone"
CURP = "curp"
RFC = "rfc"
NON_TEXT_CONTENT = "non_text_content"

#: Labels for refusal messages. They describe the kind, never the match.
KIND_LABELS: dict[str, str] = {
    EMAIL: "an email address",
    PHONE: "a phone number",
    CURP: "a CURP",
    RFC: "an RFC",
    NON_TEXT_CONTENT: "non-text content (an image cannot be checked for identifiers)",
}

# One local-part character before the "@" is enough to recognise the shape,
# and keeps the per-position cost constant (a variable-length local part
# would rescan every long word on every position).
_EMAIL = re.compile(
    r"[A-Za-z0-9._%+\-]@[A-Za-z0-9\-]{1,63}(?:\.[A-Za-z0-9\-]{1,63}){0,8}\.[A-Za-z]{2,24}"
)
# CURP and RFC both carry six consecutive digits; text without them skips
# both patterns.
_SIX_DIGITS = re.compile(r"\d{6}")
_NON_DIGITS = re.compile(r"\D+")

# 4 letters, birth date, sex (H/M, or X), 5 letters, 1 alphanumeric, 1 digit.
# The state code and date are not validated: a near-CURP is still a CURP.
_CURP = re.compile(
    r"(?<![A-Z0-9])[A-Z]{4}\d{6}[HMX][A-Z]{5}[A-Z0-9]\d(?![A-Z0-9])",
    re.IGNORECASE,
)

# 3 letters (legal entity) or 4 (person), a valid YYMMDD, a 3-character
# homoclave. Inside a CURP the trailing lookahead fails, so a CURP is reported
# once, as a CURP.
_RFC = re.compile(
    r"(?<![A-ZÑ&0-9])[A-ZÑ&]{3,4}\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
    r"[A-Z0-9]{3}(?![A-Z0-9])",
    re.IGNORECASE,
)

# Dates and clock times read as phone numbers once their separators are
# ignored ("2026-10-07 10:30" is ten digits), so they are masked out before
# the phone scan.
_DATE_OR_TIME = re.compile(
    r"(?<!\d)(?:"
    r"\d{4}-\d{1,2}-\d{1,2}"  # 2026-10-07
    r"|\d{1,2}[-/.]\d{1,2}[-/.]\d{4}"  # 07/10/2026, 07-10-2026, 07.10.2026
    r"|\d{1,2}:\d{2}(?::\d{2})?"  # 10:30, 10:30:00
    r")(?!\d)"
)

# 10 to 15 digits, each pair of digits separated by at most two of
# space ( ) . - — "777 123 4567", "(777) 123-4567", "+52 1 777 123 4567",
# "55-1234-5678", "7771234567". Not glued to a word or to other digits.
_PHONE_CANDIDATE = re.compile(r"(?<![\w+])(?:\+|00)?\d(?:[\s().\-]{0,2}\d){9,14}(?!\w)")
_DIGIT_GROUP = re.compile(r"\d+")


def _is_phone(candidate: str) -> bool:
    """Accept a candidate only if it is shaped like a phone number.

    A list of small numbers ("8 9 7 10 9 8 7 9 10 8") also has ten digits;
    a phone number has at most one single-digit group (the mobile "1" after
    a country code).
    """
    groups = _DIGIT_GROUP.findall(candidate)
    digits = sum(len(group) for group in groups)
    single_digit_groups = sum(1 for group in groups if len(group) == 1)
    return 10 <= digits <= 15 and single_digit_groups <= 1


def _kinds_in(text: str) -> set[str]:
    # Each pattern sits behind a C-level prefilter, so ordinary prose (no
    # "@", no six-digit run, fewer than ten digits) costs a few linear scans.
    kinds: set[str] = set()
    if "@" in text and _EMAIL.search(text):
        kinds.add(EMAIL)
    if _SIX_DIGITS.search(text):
        if _CURP.search(text):
            kinds.add(CURP)
        if _RFC.search(text):
            kinds.add(RFC)
    if len(_NON_DIGITS.sub("", text)) >= 10:
        masked = _DATE_OR_TIME.sub("#", text)
        if any(_is_phone(match.group(0)) for match in _PHONE_CANDIDATE.finditer(masked)):
            kinds.add(PHONE)
    return kinds


def _strings(value: Any) -> Iterator[str]:
    """Yield every string value nested anywhere in ``value`` (keys excluded)."""
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list | tuple):
            stack.extend(item)


def _has_non_text_block(messages: Any) -> bool:
    """True when any message carries a content block that is not text."""
    if not isinstance(messages, list):
        return False
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, str):
                continue
            if isinstance(block, dict) and block.get("type") == "text":
                continue
            return True
    return False


def find_direct_identifiers(messages: Any) -> list[str]:
    """Return the sorted KINDS of direct identifier found in ``messages``.

    ``messages`` is the request's message list as received: any nesting of
    dicts, lists and strings, system prompt included. Every string value is
    scanned — content, text blocks, ``name`` fields, tool-call arguments.
    The result holds kind names from :data:`KIND_LABELS`, never the text that
    matched; an empty list means nothing obvious was found, not that the
    payload is anonymous.
    """
    found: set[str] = set()
    if _has_non_text_block(messages):
        found.add(NON_TEXT_CONTENT)
    for text in _strings(messages):
        found.update(_kinds_in(text))
    return sorted(found)
