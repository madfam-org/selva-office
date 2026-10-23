"""Explicit coverage metadata for financial reads; no fallback-to-zero semantics."""

from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator


class FinancialReadUnavailableError(RuntimeError):
    """A stable error whose text must not contain source records or credentials."""


class TransactionReadProof(BaseModel):
    source: Literal["dhanam.transactions"] = "dhanam.transactions"
    scope_id: str
    since: str
    until_exclusive: str
    status: Literal["complete"] = "complete"
    total: int = Field(ge=0, strict=True)
    pages_read: int = Field(ge=1, strict=True)
    page_size: int = Field(ge=1, strict=True)


class CompleteTransactionRead(BaseModel):
    """Protocol pagination proof, not an account/statement completeness attestation."""

    items: list[dict[str, Any]]
    proof: TransactionReadProof

    @model_validator(mode="after")
    def count_matches(self) -> Self:
        if len(self.items) != self.proof.total:
            raise ValueError("Transaction read count differs from source total")
        return self
