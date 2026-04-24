"""CLI for dispatching tasks and querying AutoSwarm."""

from __future__ import annotations

import json
import os
import sys

import click

from .client import AutoSwarmSync
from .exceptions import AutoSwarmError


def _get_client() -> AutoSwarmSync:
    """Build a sync client from environment variables."""
    base_url = os.environ.get("AUTOSWARM_API_URL", "http://localhost:4300")
    token = os.environ.get("AUTOSWARM_TOKEN", "dev-token")
    return AutoSwarmSync(base_url=base_url, token=token)


@click.group()
def cli() -> None:
    """AutoSwarm CLI — interact with the AutoSwarm Office API."""


# -- dispatch ----------------------------------------------------------------


@cli.command()
@click.argument("description")
@click.option("--graph-type", default="coding", help="Graph type for the task.")
@click.option("--agent-id", multiple=True, help="Agent IDs to assign (repeatable).")
@click.option("--skill", multiple=True, help="Required skills (repeatable).")
@click.option("--workflow-id", default=None, help="Workflow UUID for custom graphs.")
def dispatch(
    description: str,
    graph_type: str,
    agent_id: tuple[str, ...],
    skill: tuple[str, ...],
    workflow_id: str | None,
) -> None:
    """Dispatch a new swarm task."""
    client = _get_client()
    try:
        task = client.dispatch(
            description=description,
            graph_type=graph_type,
            assigned_agent_ids=list(agent_id),
            required_skills=list(skill),
            workflow_id=workflow_id,
        )
        click.echo(json.dumps(task.model_dump(), indent=2))
    except AutoSwarmError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


# -- agents ------------------------------------------------------------------


@cli.group()
def agents() -> None:
    """Agent management commands."""


@agents.command("list")
def agents_list() -> None:
    """List all agents."""
    client = _get_client()
    try:
        agent_list = client.list_agents()
        click.echo(json.dumps([a.model_dump() for a in agent_list], indent=2))
    except AutoSwarmError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


# -- tasks -------------------------------------------------------------------


@cli.group()
def tasks() -> None:
    """Task management commands."""


@tasks.command("get")
@click.argument("task_id")
def tasks_get(task_id: str) -> None:
    """Get a task by ID."""
    client = _get_client()
    try:
        task = client.get_task(task_id)
        click.echo(json.dumps(task.model_dump(), indent=2))
    except AutoSwarmError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()


@tasks.command("wait")
@click.argument("task_id")
@click.option("--timeout", default=300.0, type=float, help="Timeout in seconds.")
@click.option("--poll-interval", default=2.0, type=float, help="Poll interval in seconds.")
def tasks_wait(task_id: str, timeout: float, poll_interval: float) -> None:
    """Wait for a task to reach a terminal status."""
    client = _get_client()
    try:
        task = client.wait_for_task(task_id, poll_interval=poll_interval, timeout=timeout)
        click.echo(json.dumps(task.model_dump(), indent=2))
    except AutoSwarmError as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(1)
    finally:
        client.close()
