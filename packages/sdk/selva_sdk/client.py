"""Async and sync AutoSwarm API clients."""

from __future__ import annotations

import asyncio
import contextlib
import time
from typing import Any

import httpx

from .exceptions import AuthenticationError, AutoSwarmError, NotFoundError, TaskTimeoutError
from .models import AgentResponse, DispatchRequest, TaskResponse

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


class AutoSwarm:
    """Async AutoSwarm API client."""

    def __init__(
        self,
        base_url: str = "http://localhost:4300",
        token: str = "dev-token",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> AutoSwarm:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()

    def _handle_response(self, resp: httpx.Response) -> None:
        """Raise typed exceptions for non-2xx responses."""
        if resp.status_code in (401, 403):
            raise AuthenticationError(
                f"Authentication failed: {resp.status_code}", resp.status_code
            )
        if resp.status_code == 404:
            raise NotFoundError("Resource not found", 404)
        if resp.status_code >= 400:
            detail = resp.text
            with contextlib.suppress(Exception):
                detail = resp.json().get("detail", detail)
            raise AutoSwarmError(f"API error {resp.status_code}: {detail}", resp.status_code)

    async def dispatch(
        self,
        description: str,
        graph_type: str = "coding",
        assigned_agent_ids: list[str] | None = None,
        required_skills: list[str] | None = None,
        payload: dict[str, Any] | None = None,
        workflow_id: str | None = None,
    ) -> TaskResponse:
        """Dispatch a new swarm task and return the created task."""
        req = DispatchRequest(
            description=description,
            graph_type=graph_type,
            assigned_agent_ids=assigned_agent_ids or [],
            required_skills=required_skills or [],
            payload=payload or {},
            workflow_id=workflow_id,
        )
        resp = await self._client.post(
            "/api/v1/swarms/dispatch",
            json=req.model_dump(exclude_none=True),
        )
        self._handle_response(resp)
        return TaskResponse.model_validate(resp.json())

    async def list_agents(self) -> list[AgentResponse]:
        """List all agents in the organization."""
        resp = await self._client.get("/api/v1/agents/")
        self._handle_response(resp)
        return [AgentResponse.model_validate(a) for a in resp.json()]

    async def get_task(self, task_id: str) -> TaskResponse:
        """Retrieve a single task by ID."""
        resp = await self._client.get(f"/api/v1/swarms/tasks/{task_id}")
        self._handle_response(resp)
        return TaskResponse.model_validate(resp.json())

    async def wait_for_task(
        self,
        task_id: str,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> TaskResponse:
        """Poll a task until it reaches a terminal status or the timeout elapses."""
        start = asyncio.get_event_loop().time()
        while True:
            task = await self.get_task(task_id)
            if task.status in _TERMINAL_STATUSES:
                return task
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed >= timeout:
                raise TaskTimeoutError(f"Task {task_id} did not complete within {timeout}s")
            await asyncio.sleep(poll_interval)


class AutoSwarmSync:
    """Synchronous wrapper around the async AutoSwarm client."""

    def __init__(
        self,
        base_url: str = "http://localhost:4300",
        token: str = "dev-token",
    ) -> None:
        self._async = AutoSwarm(base_url=base_url, token=token)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        asyncio.run(self._async.close())

    def __enter__(self) -> AutoSwarmSync:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def dispatch(
        self,
        description: str,
        graph_type: str = "coding",
        **kwargs: Any,
    ) -> TaskResponse:
        """Dispatch a new swarm task (blocking)."""
        return asyncio.run(self._async.dispatch(description, graph_type, **kwargs))

    def list_agents(self) -> list[AgentResponse]:
        """List all agents (blocking)."""
        return asyncio.run(self._async.list_agents())

    def get_task(self, task_id: str) -> TaskResponse:
        """Retrieve a single task by ID (blocking)."""
        return asyncio.run(self._async.get_task(task_id))

    def wait_for_task(
        self,
        task_id: str,
        poll_interval: float = 2.0,
        timeout: float = 300.0,
    ) -> TaskResponse:
        """Poll a task until terminal status (blocking)."""
        start = time.monotonic()
        while True:
            task = asyncio.run(self._async.get_task(task_id))
            if task.status in _TERMINAL_STATUSES:
                return task
            elapsed = time.monotonic() - start
            if elapsed >= timeout:
                raise TaskTimeoutError(f"Task {task_id} did not complete within {timeout}s")
            time.sleep(poll_interval)
