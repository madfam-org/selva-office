"""Several credentials (accounts) for one vendor, as distinct providers.

Selva may hold more than one Anthropic account. Each extra account is its
own provider, named ``anthropic-<suffix>`` (for example ``anthropic-ops``),
declared in the org config::

    providers:
      anthropic-ops:
        adapter: anthropic
        api_key_env: ANTHROPIC_API_KEY_OPS

The rules this module encodes, used by the factory, the grant guard, the
router and the cost model:

- The built-in ``anthropic`` provider (``ANTHROPIC_API_KEY``) keeps its
  behaviour exactly as before. Nothing here changes how it registers,
  routes or is metered.
- An extra credential is a member of the ``anthropic`` *family*: same
  vendor, same models, same prices, same data-residency class. It is a
  different *payer*, so it has its own grant and its own ledger rows
  (the ledger's ``provider`` column carries the credential name).
- An extra credential is FAIL-CLOSED: it is registered only when its name
  is listed in ``PROVIDER_GRANTS_REQUIRED_FOR``, so it can never spend
  outside a grant of its own. The grant guard re-checks this per call.
- It is never added to any global routing list. It is reachable only where
  routing names it explicitly (an org override or a server-set
  ``provider_allowlist``), so every tenant that does not name it routes
  exactly as before.

A third account is configuration only: an org-config entry, the key in the
Secret, the name in ``PROVIDER_GRANTS_REQUIRED_FOR`` and a grant in Vault.
"""

from __future__ import annotations

import re

#: Vendor families that may carry extra credentials. Only Anthropic today.
ANTHROPIC = "anthropic"

#: ``anthropic-<suffix>``: lowercase letters, digits and dashes.
_CREDENTIAL_NAME = re.compile(r"^anthropic-[a-z0-9][a-z0-9-]{0,30}$")


def provider_family(name: str) -> str:
    """The vendor family of a provider name (``anthropic-ops`` -> ``anthropic``)."""
    lowered = name.strip().lower()
    if lowered == ANTHROPIC or lowered.startswith(ANTHROPIC + "-"):
        return ANTHROPIC
    return lowered


def is_extra_credential(name: str) -> bool:
    """True for an additional account of a vendor family (not the built-in one)."""
    return provider_family(name) != name.strip().lower()


def valid_credential_name(name: str) -> bool:
    """True when ``name`` is a well-formed extra Anthropic credential name."""
    return bool(_CREDENTIAL_NAME.match(name))
