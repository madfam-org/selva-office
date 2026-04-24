"""Operations workflow graph -- inventory, pedimento, carrier tracking, notification."""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from ..event_emitter import instrumented_node
from .base import BaseGraphState
from .base import run_async as _run_async

logger = logging.getLogger(__name__)


# -- State --------------------------------------------------------------------


class OperationsState(BaseGraphState, TypedDict, total=False):
    """Extended state for the operations workflow."""

    org_id: str
    sku: str | None
    pedimento_number: str | None
    tracking_numbers: list[dict[str, Any]]
    inventory_status: dict[str, Any] | None


# -- Node functions -----------------------------------------------------------


@instrumented_node
def check_inventory(state: OperationsState) -> OperationsState:
    """Check inventory levels for the requested SKU.

    Delegates to the InventoryCheckTool which tries Dhanam, then
    PravaraMES, then returns a "not configured" fallback.
    """
    messages = state.get("messages", [])
    sku = state.get("sku") or ""

    inventory_status: dict[str, Any] | None = None
    if sku:
        try:
            from selva_tools.builtins.operations import InventoryCheckTool

            tool = InventoryCheckTool()
            result = _run_async(tool.execute(sku=sku))
            inventory_status = result.data
        except Exception:
            logger.warning("Inventory check failed for SKU %s", sku, exc_info=True)

    inv_message = AIMessage(
        content=(
            f"Inventory check for SKU '{sku}': "
            f"{'found' if inventory_status else 'skipped (no SKU provided)'}."
        ),
        additional_kwargs={"action_category": "api_call"},
    )

    return {
        **state,
        "messages": [*messages, inv_message],
        "inventory_status": inventory_status,
        "status": "checking_inventory",
    }


@instrumented_node
def process_pedimento(state: OperationsState) -> OperationsState:
    """Look up a customs pedimento document via Karafiel SAT module.

    Skips gracefully when no pedimento number is provided in the state.
    """
    messages = state.get("messages", [])
    numero = state.get("pedimento_number") or ""

    pedimento_data: dict[str, Any] | None = None
    if numero:
        try:
            from selva_tools.builtins.operations import PedimentoLookupTool

            tool = PedimentoLookupTool()
            result = _run_async(tool.execute(numero=numero))
            pedimento_data = result.data
        except Exception:
            logger.warning("Pedimento lookup failed for %s", numero, exc_info=True)

    ped_message = AIMessage(
        content=(
            f"Pedimento lookup for '{numero}': "
            f"{'found' if pedimento_data else 'skipped (no number provided)'}."
        ),
        additional_kwargs={"action_category": "api_call"},
    )

    # Merge pedimento data into result
    result_data = state.get("result") or {}
    if pedimento_data:
        result_data["pedimento"] = pedimento_data

    return {
        **state,
        "messages": [*messages, ped_message],
        "result": result_data,
        "status": "processing_pedimento",
    }


@instrumented_node
def track_shipments(state: OperationsState) -> OperationsState:
    """Track shipments for all tracking numbers in the state.

    Each entry in ``tracking_numbers`` should have ``carrier`` and
    ``tracking_number`` keys.  Results are accumulated and merged
    into the state result.
    """
    messages = state.get("messages", [])
    tracking_entries = state.get("tracking_numbers") or []

    tracking_results: list[dict[str, Any]] = []
    for entry in tracking_entries:
        carrier = entry.get("carrier", "")
        number = entry.get("tracking_number", "")
        if not carrier or not number:
            continue
        try:
            from selva_tools.builtins.operations import CarrierTrackingTool

            tool = CarrierTrackingTool()
            result = _run_async(tool.execute(carrier=carrier, tracking_number=number))
            tracking_results.append(result.data)
        except Exception:
            logger.warning("Carrier tracking failed for %s/%s", carrier, number, exc_info=True)
            tracking_results.append(
                {
                    "carrier": carrier,
                    "tracking_number": number,
                    "status": "error",
                }
            )

    track_message = AIMessage(
        content=f"Tracked {len(tracking_results)} shipment(s).",
        additional_kwargs={"action_category": "api_call"},
    )

    result_data = state.get("result") or {}
    result_data["tracking"] = tracking_results

    return {
        **state,
        "messages": [*messages, track_message],
        "result": result_data,
        "status": "tracking_shipments",
    }


@instrumented_node
def notify_ops(state: OperationsState) -> OperationsState:
    """Build and finalize the operations summary.

    Assembles inventory, pedimento, and tracking results into a
    completed result dict.
    """
    messages = state.get("messages", [])

    result_data = state.get("result") or {}
    inventory_status = state.get("inventory_status")
    if inventory_status:
        result_data["inventory"] = inventory_status

    result_data["summary"] = {
        "has_inventory": inventory_status is not None,
        "has_pedimento": "pedimento" in result_data,
        "tracking_count": len(result_data.get("tracking", [])),
    }

    notify_message = AIMessage(
        content="Operations workflow completed.",
        additional_kwargs={"action_category": "api_call"},
    )

    return {
        **state,
        "messages": [*messages, notify_message],
        "result": result_data,
        "status": "completed",
    }


# -- Graph construction -------------------------------------------------------


def build_operations_graph() -> StateGraph:
    """Construct the operations workflow state graph.

    Flow::

        check_inventory -> process_pedimento -> track_shipments -> notify_ops -> END

    This is a read-only pipeline; no interrupt points are required.
    """
    graph = StateGraph(OperationsState)

    graph.add_node("check_inventory", check_inventory)
    graph.add_node("process_pedimento", process_pedimento)
    graph.add_node("track_shipments", track_shipments)
    graph.add_node("notify_ops", notify_ops)

    graph.set_entry_point("check_inventory")
    graph.add_edge("check_inventory", "process_pedimento")
    graph.add_edge("process_pedimento", "track_shipments")
    graph.add_edge("track_shipments", "notify_ops")
    graph.add_edge("notify_ops", END)

    return graph
