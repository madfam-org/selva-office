"""A2A protocol client for calling external A2A-compatible agents."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import httpx

from .schema import AgentCard, TaskRequest, TaskResponse

logger = logging.getLogger(__name__)


class A2AClient:
    """Async client for discovering and invoking external A2A agents.

    Usage::

        client = A2AClient()
        card = await client.discover("https://other-agent.example.com/a2a")
        resp = await client.send_task(
            "https://other-agent.example.com/a2a",
            TaskRequest(description="Review this PR"),
        )
    """

    def __init__(self, timeout: float = 30.0) -> None:
        self._timeout = timeout

    async def discover(self, agent_url: str) -> AgentCard:
        """Fetch the AgentCard from ``<agent_url>/.well-known/agent.json``."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{agent_url}/.well-known/agent.json")
            resp.raise_for_status()
            return AgentCard(**resp.json())

    async def send_task(
        self,
        agent_url: str,
        task: TaskRequest,
        token: str | None = None,
    ) -> TaskResponse:
        """Send a one-shot task to a remote agent."""
        headers = self._auth_headers(token)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{agent_url}/tasks/send",
                json=task.model_dump(),
                headers=headers,
            )
            resp.raise_for_status()
            return TaskResponse(**resp.json())

    async def get_task(
        self,
        agent_url: str,
        task_id: str,
        token: str | None = None,
    ) -> TaskResponse:
        """Poll the status of a previously submitted task."""
        headers = self._auth_headers(token)
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{agent_url}/tasks/{task_id}",
                headers=headers,
            )
            resp.raise_for_status()
            return TaskResponse(**resp.json())

    async def send_subscribe(
        self,
        agent_url: str,
        task: TaskRequest,
        token: str | None = None,
    ) -> AsyncIterator[str]:
        """Send a task and stream SSE events.

        Yields raw SSE ``data:`` lines as strings.
        """
        headers = self._auth_headers(token)
        async with (
            httpx.AsyncClient(timeout=self._timeout) as client,
            client.stream(
                "POST",
                f"{agent_url}/tasks/sendSubscribe",
                json=task.model_dump(),
                headers=headers,
            ) as resp,
        ):
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: "):
                    yield line[6:]

    @staticmethod
    def _auth_headers(token: str | None) -> dict[str, str]:
        if token:
            return {"Authorization": f"Bearer {token}"}
        return {}
