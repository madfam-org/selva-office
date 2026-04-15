"""Deployment workflow graph -- validate, approve, deploy, monitor."""

from __future__ import annotations

import logging
from typing import TypedDict

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph
from langgraph.types import interrupt

from ..event_emitter import instrumented_node
from .base import BaseGraphState, check_permission
from .base import run_async as _run_async

logger = logging.getLogger(__name__)


# -- State --------------------------------------------------------------------


class DeploymentState(BaseGraphState, TypedDict, total=False):
    """Extended state for the deployment workflow."""

    service: str
    environment: str
    image_tag: str
    deploy_id: str
    deploy_status: str


# -- Node functions -----------------------------------------------------------


@instrumented_node
def validate(state: DeploymentState) -> DeploymentState:
    """Validate deployment parameters and check permissions.

    Rejects the task if the ``deploy`` permission is denied or if the
    ``service`` field is missing.
    """
    messages = state.get("messages", [])
    service = state.get("service", "")
    environment = state.get("environment", "staging")
    image_tag = state.get("image_tag", "latest")

    if not service:
        error_msg = AIMessage(content="Deployment rejected: 'service' is required.")
        return {
            **state,
            "messages": [*messages, error_msg],
            "status": "error",
        }

    from autoswarm_permissions.types import PermissionLevel

    perm = check_permission(state, "deploy")
    if perm.level == PermissionLevel.DENY:
        deny_msg = AIMessage(content="Deployment denied by permission engine.")
        return {
            **state,
            "messages": [*messages, deny_msg],
            "status": "blocked",
        }

    validate_msg = AIMessage(
        content=(
            f"Deployment validated: service={service}, "
            f"environment={environment}, image_tag={image_tag}."
        ),
        additional_kwargs={"action_category": "deploy"},
    )
    return {
        **state,
        "messages": [*messages, validate_msg],
        "status": "validated",
    }


@instrumented_node
def deploy_gate(state: DeploymentState) -> DeploymentState:
    """Interrupt execution before deployment to require human approval.

    Uses LangGraph's ``interrupt()`` to pause the graph.  The Tactician
    must approve before the deployment proceeds.
    """
    if state.get("status") in ("error", "blocked"):
        return state

    service = state.get("service", "unknown")
    environment = state.get("environment", "staging")
    image_tag = state.get("image_tag", "latest")

    approval_context = {
        "action": "deploy",
        "action_category": "deploy",
        "service": service,
        "environment": environment,
        "image_tag": image_tag,
    }

    decision = interrupt(approval_context)

    if decision.get("approved", False):
        approve_msg = AIMessage(
            content=f"Deployment approved: {service} → {environment}.",
            additional_kwargs={"action_category": "deploy"},
        )
        return {
            **state,
            "messages": [*state.get("messages", []), approve_msg],
            "status": "approved",
        }

    feedback = decision.get("feedback", "No feedback provided")
    deny_msg = AIMessage(
        content=f"Deployment denied. Feedback: {feedback}",
        additional_kwargs={"action_category": "deploy"},
    )
    return {
        **state,
        "messages": [*state.get("messages", []), deny_msg],
        "status": "denied",
    }


@instrumented_node
def deploy(state: DeploymentState) -> DeploymentState:
    """Trigger the deployment via the DeployTool.

    Skips if the deployment was denied or blocked at an earlier stage.
    """
    messages = state.get("messages", [])
    if state.get("status") in ("denied", "blocked", "error"):
        return state

    service = state.get("service", "")
    environment = state.get("environment", "staging")
    image_tag = state.get("image_tag", "latest")

    try:
        import os

        from autoswarm_tools.builtins.deploy import DeployTool

        # Inject Enclii credentials from worker config.
        from autoswarm_workers.config import get_settings

        settings = get_settings()
        if settings.enclii_deploy_token:
            os.environ.setdefault("ENCLII_DEPLOY_TOKEN", settings.enclii_deploy_token)

        tool = DeployTool()
        result = _run_async(tool.execute(
            service=service,
            environment=environment,
            image_tag=image_tag,
        ))

        if result.success:
            deploy_id = result.data.get("deploy_id", "")
            deploy_msg = AIMessage(
                content=f"Deployment triggered: {deploy_id}",
                additional_kwargs={"action_category": "deploy"},
            )
            return {
                **state,
                "messages": [*messages, deploy_msg],
                "deploy_id": deploy_id,
                "deploy_status": result.data.get("status", "pending"),
                "status": "deploying",
            }
        else:
            error_msg = AIMessage(content=f"Deployment failed: {result.error}")
            return {
                **state,
                "messages": [*messages, error_msg],
                "status": "error",
            }
    except Exception as exc:
        logger.exception("Deployment execution failed")
        error_msg = AIMessage(content=f"Deployment exception: {exc}")
        return {
            **state,
            "messages": [*messages, error_msg],
            "status": "error",
        }


@instrumented_node
def monitor(state: DeploymentState) -> DeploymentState:
    """Check deployment status via the DeployStatusTool.

    Skips if the deployment was not triggered.
    """
    messages = state.get("messages", [])
    deploy_id = state.get("deploy_id", "")

    if not deploy_id or state.get("status") in ("denied", "blocked", "error"):
        return {**state, "status": state.get("status", "completed")}

    try:
        from autoswarm_tools.builtins.deploy import DeployStatusTool

        tool = DeployStatusTool()
        result = _run_async(tool.execute(deploy_id=deploy_id))

        if result.success:
            deploy_status = result.data.get("status", "unknown")
            monitor_msg = AIMessage(
                content=f"Deploy {deploy_id} status: {deploy_status}",
                additional_kwargs={"action_category": "deploy"},
            )
            return {
                **state,
                "messages": [*messages, monitor_msg],
                "deploy_status": deploy_status,
                "status": "completed",
            }
        else:
            error_msg = AIMessage(content=f"Status check failed: {result.error}")
            return {
                **state,
                "messages": [*messages, error_msg],
                "status": "completed",
            }
    except Exception as exc:
        logger.warning("Deploy status check failed: %s", exc)
        return {**state, "status": "completed"}


# -- Graph construction -------------------------------------------------------


def build_deployment_graph() -> StateGraph:
    """Construct the deployment workflow state graph.

    Flow::

        validate -> deploy_gate (interrupt) -> deploy -> monitor -> END
    """
    graph = StateGraph(DeploymentState)

    graph.add_node("validate", validate)
    graph.add_node("deploy_gate", deploy_gate)
    graph.add_node("deploy", deploy)
    graph.add_node("monitor", monitor)

    graph.set_entry_point("validate")
    graph.add_edge("validate", "deploy_gate")
    graph.add_edge("deploy_gate", "deploy")
    graph.add_edge("deploy", "monitor")
    graph.add_edge("monitor", END)

    return graph
