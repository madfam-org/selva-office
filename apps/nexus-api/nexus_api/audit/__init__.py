"""Audit helpers for append-only ledgers.

Subpackages here wrap write/verify concerns for ledger-shape tables
(``consent_ledger``, ``secret_audit_log``, future ``deploy_audit_log``).
Every table in this package has UPDATE/DELETE revoked from the app
role at the DB level — this module does not try to modify rows, only
insert and verify them.
"""
