"""Infra self-healing agents for the MADFAM platform (RFC 0047), v1.

v1 is diagnose-and-propose only. HARD RULE: v1 never writes to production.
Every Enclii call it can make is a read or a dry-run (``dry_run: true``); an
apply request cannot be expressed by the toolbox. A remedy is a reviewed plan
(Enclii dry-run with its plan hash, or a prepare-only PR) that a human
applies.

Pieces:

- ``alerts``   — Alertmanager webhook (v4) model, incident key, qualification.
- ``store``    — dedup, cooldown, flap counter, daily spend, kill switch, queue.
- ``budget``   — per-incident and per-day USD caps, checked before every call.
- ``tools``    — the read-only Enclii toolbox and its explicit allowlist.
- ``signatures`` — deterministic known-incident signatures (no LLM needed).
- ``agent``    — the diagnosis loop (evidence first, then a bounded LLM loop).
- ``report``   — the Telegram report text, with the plan hash.
- ``courier``  — the Courier envelope (angelia ``POST /v1/courier/send``).
"""

from .config import AutohealConfig, ConfigError

__all__ = ["AutohealConfig", "ConfigError"]
