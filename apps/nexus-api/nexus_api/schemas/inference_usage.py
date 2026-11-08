"""Response shape of the monthly inference-usage read (``GET /api/v1/billing/inference-usage``).

The same model is the ``outputSchema`` of the MCP tool ``inference_usage``
(``nexus_api.mcp``), so the HTTP read and the tool cannot drift apart.

Wording rules, enforced here and in the tests:

* The dollar figure is a LIST-PRICE ESTIMATE in USD. Each ledger row is priced
  when it is written, from the public provider price table in
  ``madfam_budget_gate.cost_model``. It is not an invoice, not cash and not
  cost of goods sold; nothing here converts it to another currency.
* Funding is ``unattributed``: the ledger has no column saying whether a call
  was paid or covered by a provider credit grant.
* Unknown is ``null``, never ``0``. The ledger stores total tokens only, so
  the input/output split is ``null``; an empty month carries
  ``status: "empty"`` and ``null`` totals.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CallerClass = Literal["service_account", "selva_worker", "person", "unrecorded"]
CompletenessStatus = Literal["complete", "partial", "empty"]
GapCode = Literal["month_open", "unpriced_rows", "no_rows"]


class UsagePeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    month: str = Field(..., description="The civil month asked for, YYYY-MM.")
    timezone: Literal["America/Mexico_City"] = Field(
        default="America/Mexico_City",
        description="Month bounds follow the cost ledger's period cut-off.",
    )
    start: datetime = Field(..., description="Inclusive start, RFC 3339 with offset.")
    end: datetime = Field(..., description="Exclusive end, RFC 3339 with offset.")
    month_closed: bool = Field(..., description="False while the month is still running.")


class PriceTable(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["madfam_budget_gate.cost_model"] = "madfam_budget_gate.cost_model"
    basis: Literal["provider_public_list_prices"] = "provider_public_list_prices"
    priced_at: Literal["ledger_write_time"] = Field(
        default="ledger_write_time",
        description="Each row was priced when it was written, with the table of that day.",
    )
    version: str | None = Field(
        default=None, description="The price table carries no version or date; null = unknown."
    )


class ListPriceEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    basis: Literal["list_price_estimate"] = "list_price_estimate"
    currency: Literal["USD"] = "USD"
    is_cash: Literal[False] = False
    price_table: PriceTable = Field(default_factory=lambda: PriceTable())
    priced_rows: int = Field(..., ge=0)
    unpriced_rows: int = Field(
        ..., ge=0, description="Rows without a USD estimate (legacy rows, or no token split)."
    )
    is_lower_bound: bool = Field(
        ..., description="True when some rows are unpriced: the sum leaves them out."
    )


class Funding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["unattributed"] = "unattributed"
    note: str = (
        "The ledger records no funding source per call, so paid inference and "
        "inference covered by a provider credit grant cannot be told apart yet."
    )


class TokenTotals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total: int | None = Field(..., description="Input + output tokens as metered; null = unknown.")
    input: None = Field(
        default=None, description="Not recorded by the ledger (total only): unknown."
    )
    output: None = Field(
        default=None, description="Not recorded by the ledger (total only): unknown."
    )


class UsageLine(BaseModel):
    """One (provider, model, caller class) group of ledger rows."""

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(..., description="null when the row did not record one.")
    model: str | None = Field(..., description="null when the row did not record one.")
    caller_class: CallerClass
    request_count: int = Field(..., ge=1)
    tokens: TokenTotals
    list_price_estimate_usd: str | None = Field(
        ..., description="Decimal string; null when no row in the group was priced."
    )
    unpriced_rows: int = Field(..., ge=0)


class Completeness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: CompletenessStatus
    gaps: list[GapCode] = Field(default_factory=list)


class InferenceUsageReport(BaseModel):
    """Inference usage of one org in one civil month, from the compute token ledger."""

    model_config = ConfigDict(extra="forbid")

    org: str
    period: UsagePeriod
    status: Literal["ok", "empty"] = Field(
        ...,
        description=(
            "'empty' = no inference rows were recorded for this org in the period. "
            "That is not proof of zero usage, so totals are null, not 0."
        ),
    )
    ledger_rows: int = Field(..., ge=0, description="Inference rows found (a count, not usage).")
    request_count: int | None = Field(..., description="Metered calls; null when empty.")
    tokens: TokenTotals
    by_line: list[UsageLine]
    list_price_estimate_usd: str | None = Field(
        ...,
        description=(
            "Sum of the rows' list-price estimates, a decimal string in USD. Not cash, "
            "not COGS. null when no row was priced."
        ),
    )
    estimate: ListPriceEstimate
    funding: Funding = Field(default_factory=lambda: Funding())
    completeness: Completeness
