"""Billing workflow graph -- CFDI 4.0 invoice generation via Karafiel."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, START, StateGraph

from ..event_emitter import instrumented_node
from .base import BaseGraphState
from .base import run_async as _run_async

logger = logging.getLogger(__name__)


# -- State --------------------------------------------------------------------


class BillingState(BaseGraphState, TypedDict, total=False):
    """Extended state for the billing / CFDI workflow."""

    emisor_rfc: str
    receptor_rfc: str
    conceptos: list[dict[str, Any]]
    cfdi_xml: str | None
    cfdi_uuid: str | None
    stamp_result: dict[str, Any] | None
    customer_phone: str | None
    customer_email: str | None


# -- Node functions -----------------------------------------------------------


@instrumented_node
def fetch_context(state: BillingState) -> BillingState:
    """Fetch transaction data from Dhanam and customer info from PhyndCRM.

    Populates emisor/receptor RFCs, conceptos, and customer contact info.
    Falls back to state values if adapters are unavailable.
    """
    messages = state.get("messages", [])
    payload = state.get("workflow_variables", {})

    emisor_rfc = state.get("emisor_rfc", payload.get("emisor_rfc", ""))
    receptor_rfc = state.get("receptor_rfc", payload.get("receptor_rfc", ""))
    conceptos = state.get("conceptos", payload.get("conceptos", []))
    customer_phone = state.get("customer_phone")
    customer_email = state.get("customer_email")

    # Try Dhanam adapter for transaction data.
    try:
        import os

        dhanam_url = os.environ.get("DHANAM_API_URL")
        dhanam_token = os.environ.get("DHANAM_API_TOKEN", "")
        if dhanam_url:
            from madfam_inference.adapters.billing import DhanamAdapter

            adapter = DhanamAdapter(base_url=dhanam_url, token=dhanam_token)
            task_id = state.get("task_id", "")
            txn = _run_async(adapter.get_transaction(task_id))
            if txn:
                emisor_rfc = emisor_rfc or txn.get("emisor_rfc", "")
                receptor_rfc = receptor_rfc or txn.get("receptor_rfc", "")
                conceptos = conceptos or txn.get("conceptos", [])
        else:
            raise RuntimeError("DHANAM_API_URL not set")
    except Exception:
        logger.debug("Dhanam adapter unavailable; using state/payload values")

    # Try PhyndCRM adapter for customer contact info.
    try:
        import os

        phynd_url = os.environ.get("PHYND_CRM_URL")
        phynd_token = os.environ.get("PHYND_CRM_TOKEN", "")
        if phynd_url and receptor_rfc:
            from madfam_inference.adapters.crm import PhyndCRMAdapter

            crm = PhyndCRMAdapter(base_url=phynd_url, token=phynd_token)
            profile = _run_async(crm.get_unified_profile(receptor_rfc))
            customer_phone = customer_phone or getattr(profile.contact, "phone", None)
            customer_email = customer_email or getattr(profile.contact, "email", None)
        else:
            raise RuntimeError("PHYND_CRM_URL not set or receptor_rfc empty")
    except Exception:
        logger.debug("PhyndCRM adapter unavailable; using state values for contact info")

    context_message = AIMessage(
        content=(
            f"Billing context fetched: emisor={emisor_rfc}, "
            f"receptor={receptor_rfc}, {len(conceptos)} concepto(s)."
        ),
        additional_kwargs={
            "action_category": "api_call",
            "billing_context": {
                "emisor_rfc": emisor_rfc,
                "receptor_rfc": receptor_rfc,
                "concepto_count": len(conceptos),
            },
        },
    )

    return {
        **state,
        "messages": [*messages, context_message],
        "emisor_rfc": emisor_rfc,
        "receptor_rfc": receptor_rfc,
        "conceptos": conceptos,
        "customer_phone": customer_phone,
        "customer_email": customer_email,
        "status": "fetching_context",
    }


@instrumented_node
def validate_rfcs(state: BillingState) -> BillingState:
    """Validate emisor and receptor RFCs via Karafiel.

    Sets status to ``"error"`` if either RFC is invalid.
    """
    messages = state.get("messages", [])
    emisor_rfc = state.get("emisor_rfc", "")
    receptor_rfc = state.get("receptor_rfc", "")

    if not emisor_rfc or not receptor_rfc:
        error_msg = AIMessage(
            content="RFC validation failed: emisor or receptor RFC is empty.",
        )
        return {
            **state,
            "messages": [*messages, error_msg],
            "status": "error",
            "result": {"error": "Missing emisor_rfc or receptor_rfc"},
        }

    try:
        import os

        karafiel_url = os.environ.get("KARAFIEL_API_URL")
        karafiel_token = os.environ.get("KARAFIEL_API_TOKEN", "")
        if karafiel_url:
            from madfam_inference.adapters.karafiel import KarafielAdapter

            adapter = KarafielAdapter(base_url=karafiel_url, token=karafiel_token)
            emisor_valid = _run_async(adapter.validate_rfc(emisor_rfc))
            receptor_valid = _run_async(adapter.validate_rfc(receptor_rfc))

            if not emisor_valid:
                error_msg = AIMessage(
                    content=f"RFC validation failed: emisor RFC '{emisor_rfc}' is invalid.",
                )
                return {
                    **state,
                    "messages": [*messages, error_msg],
                    "status": "error",
                    "result": {"error": f"Invalid emisor RFC: {emisor_rfc}"},
                }

            if not receptor_valid:
                error_msg = AIMessage(
                    content=f"RFC validation failed: receptor RFC '{receptor_rfc}' is invalid.",
                )
                return {
                    **state,
                    "messages": [*messages, error_msg],
                    "status": "error",
                    "result": {"error": f"Invalid receptor RFC: {receptor_rfc}"},
                }
        else:
            raise RuntimeError("KARAFIEL_API_URL not set")
    except ImportError:
        logger.debug("KarafielAdapter not available; skipping RFC validation")
    except RuntimeError:
        logger.debug("KARAFIEL_API_URL not configured; skipping RFC validation")

    valid_msg = AIMessage(
        content=f"RFCs validated: emisor={emisor_rfc}, receptor={receptor_rfc}.",
        additional_kwargs={"action_category": "api_call"},
    )

    return {
        **state,
        "messages": [*messages, valid_msg],
        "status": "rfcs_validated",
    }


@instrumented_node
def check_blacklist(state: BillingState) -> BillingState:
    """Stop billing unless the configured source explicitly returns unlisted."""
    messages = state.get("messages", [])
    receptor_rfc = state.get("receptor_rfc", "")

    try:
        import os

        from madfam_inference.adapters.karafiel import BlacklistResult, KarafielAdapter

        karafiel_url = os.environ.get("KARAFIEL_API_URL")
        karafiel_token = os.environ.get("KARAFIEL_API_TOKEN", "")
        if not karafiel_url or not receptor_rfc:
            raise RuntimeError("Screening source or subject unavailable")
        adapter = KarafielAdapter(base_url=karafiel_url, token=karafiel_token)
        screening = _run_async(adapter.check_blacklist(receptor_rfc))
        if (
            not isinstance(screening, BlacklistResult)
            or not screening.check_completed
            or screening.rfc != receptor_rfc
        ):
            raise RuntimeError("Screening lookup incomplete")
    except Exception:
        # Never publish exception text, taxpayer identifiers or a clearance
        # claim when configuration, transport or the response contract failed.
        logger.warning("Billing paused: blacklist screening unavailable")
        return {
            **state,
            "messages": [
                *messages,
                AIMessage(content="Blacklist screening is unknown. Invoice generation stopped."),
            ],
            "status": "error",
            "result": {"error": "blacklist_screening_unavailable"},
        }

    if screening.listed is True:
        return {
            **state,
            "messages": [
                *messages,
                AIMessage(content="Source reports a 69-B listing. Invoice generation blocked."),
            ],
            "status": "blocked",
            "result": {"error": "blacklist_screening_listed"},
        }

    return {
        **state,
        "messages": [
            *messages,
            AIMessage(
                content="Screening source explicitly reports no listing for the recipient.",
                additional_kwargs={"action_category": "api_call"},
            ),
        ],
        "status": "blacklist_clear",
    }


def _fiscal_execution_disabled(state: BillingState) -> BillingState:
    """Do not turn placeholders or agent input into fiscal/delivery evidence.

    This legacy graph has no tenant-bound approval, durable idempotency, or
    verified provider receipt contract. Keep generation, stamping and delivery
    disabled, including direct/resumed node calls, until those gates exist.
    A task-provided flag cannot grant this authority.
    """
    return {
        **state,
        "messages": [
            *state.get("messages", []),
            AIMessage(
                content=(
                    "Automated fiscal execution is unavailable in this workflow. "
                    "No invoice, stamp or customer delivery was performed."
                )
            ),
        ],
        "cfdi_xml": None,
        "cfdi_uuid": None,
        "stamp_result": None,
        "status": "blocked",
        "result": {"error": "fiscal_execution_not_enabled"},
    }


@instrumented_node
def generate_cfdi(state: BillingState) -> BillingState:
    """Generation remains disabled pending the reviewed fiscal execution contract."""
    return _fiscal_execution_disabled(state)


@instrumented_node
def stamp_cfdi(state: BillingState) -> BillingState:
    """A resumed stamp node cannot bypass approval or fabricate a stamp receipt."""
    return _fiscal_execution_disabled(state)


@instrumented_node
def notify_customer(state: BillingState) -> BillingState:
    """Do not send or claim delivery without verified fiscal and delivery receipts."""
    return _fiscal_execution_disabled(state)


# -- Conditional edge routing -------------------------------------------------


def _route_after_validate(state: BillingState) -> str:
    """Route to END on error, otherwise continue to check_blacklist."""
    if state.get("status") == "error":
        return END
    return "check_blacklist"


def _route_after_blacklist(state: BillingState) -> str:
    """Only an explicit completed, unlisted check may reach generation."""
    if state.get("status") == "blacklist_clear":
        return "generate_cfdi"
    return END


def _route_after_generate(state: BillingState) -> str:
    return "stamp_cfdi" if state.get("status") == "cfdi_generated" else END


def _route_after_stamp(state: BillingState) -> str:
    return "notify_customer" if state.get("status") == "stamped" else END


# -- Graph construction -------------------------------------------------------


def build_billing_graph() -> StateGraph:
    """Construct and compile the billing workflow state graph.

    Flow::

        fetch_context -> validate_rfcs --(error)--> END
                                       \\--> check_blacklist --(blocked)--> END
                                                             \\--> generate_cfdi
                                                                   -> END (disabled)

    Stamp and delivery nodes remain registered for checkpoint compatibility,
    but refuse execution even when resumed directly.
    """
    graph = StateGraph(BillingState)

    graph.add_node("fetch_context", fetch_context)
    graph.add_node("validate_rfcs", validate_rfcs)
    graph.add_node("check_blacklist", check_blacklist)
    graph.add_node("generate_cfdi", generate_cfdi)
    graph.add_node("stamp_cfdi", stamp_cfdi)
    graph.add_node("notify_customer", notify_customer)

    graph.add_edge(START, "fetch_context")
    graph.add_edge("fetch_context", "validate_rfcs")
    graph.add_conditional_edges("validate_rfcs", _route_after_validate)
    graph.add_conditional_edges("check_blacklist", _route_after_blacklist)
    graph.add_conditional_edges("generate_cfdi", _route_after_generate)
    graph.add_conditional_edges("stamp_cfdi", _route_after_stamp)
    graph.add_edge("notify_customer", END)

    return graph
