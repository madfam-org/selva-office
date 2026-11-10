"""Selva inference usage → Dhanam's cost ledger (``cost.event.v1``, source ``selva``).

Dhanam owns the ecosystem cost ledger; every source pushes the same
``cost.event.v1`` contract to ``POST /v1/cost-events`` with its own Janua
``client_credentials`` token. This package is Selva's emitter:

* ``rollup`` — pure: classify each ``compute_token_ledger`` row by who paid for
  it, roll the rows up per civil day (America/Mexico_City) × org × product /
  engagement × provider × funding, and build the events.
* ``outbox`` — the durable outbox table (``cost_event_outbox``): what was built,
  what Dhanam accepted, what waits for a retry.
* ``dhanam_client`` — the Janua token and the POST, with every answer mapped to
  one outcome.
* ``runner`` — one sweep: read the ledger window, sync the outbox, send.
* ``__main__`` — the operator command (``python -m nexus_api.cost_events``).

Off unless ``SELVA_COST_EVENTS_EMIT_ENABLED=true``. The dry run works with the
flag off and sends and writes nothing. Full design: ``docs/COST_EVENTS.md``.
"""
