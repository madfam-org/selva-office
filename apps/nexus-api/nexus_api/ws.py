"""WebSocket connection manager for real-time approval notifications."""

from __future__ import annotations

import logging
import time
from collections import deque
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts messages.

    Connections are keyed by a ``client_id`` (typically the authenticated
    user's ``sub`` claim or a session identifier).
    """

    def __init__(self) -> None:
        self.active_connections: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, client_id: str) -> None:
        """Accept an incoming WebSocket and register it under *client_id*."""
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info("WebSocket connected: %s (total: %d)", client_id, len(self.active_connections))

    def disconnect(self, client_id: str) -> None:
        """Remove a connection by *client_id*."""
        self.active_connections.pop(client_id, None)
        logger.info(
            "WebSocket disconnected: %s (total: %d)", client_id, len(self.active_connections)
        )

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to every connected client.

        Broken connections are silently pruned during broadcast.
        """
        stale: list[str] = []
        for client_id, ws in self.active_connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning("Failed to send to %s; pruning connection", client_id)
                stale.append(client_id)

        for client_id in stale:
            self.disconnect(client_id)

    async def send_to(self, client_id: str, message: dict[str, Any]) -> None:
        """Send a JSON message to a specific client."""
        ws = self.active_connections.get(client_id)
        if ws is not None:
            try:
                await ws.send_json(message)
            except Exception:
                logger.warning("Failed to send to %s; pruning connection", client_id)
                self.disconnect(client_id)

    async def send_approval_request(self, request: dict[str, Any]) -> None:
        """Broadcast an approval request notification to all connected clients."""
        await self.broadcast({"type": "approval_request", "payload": request})

    async def send_approval_response(self, response: dict[str, Any]) -> None:
        """Broadcast an approval response notification to all connected clients."""
        await self.broadcast({"type": "approval_resolved", "payload": response})


class MessageRateLimiter:
    """Sliding-window rate limiter for WebSocket messages.

    Each client is tracked independently.  Messages older than
    *window_seconds* are purged on every ``check()`` call so that
    memory stays bounded even for long-lived connections.
    """

    def __init__(self, max_messages: int = 30, window_seconds: float = 60.0) -> None:
        self._max = max_messages
        self._window = window_seconds
        self._messages: dict[str, deque[float]] = {}

    def check(self, client_id: str) -> bool:
        """Return ``True`` if the message is allowed, ``False`` if rate-limited."""
        now = time.monotonic()
        q = self._messages.setdefault(client_id, deque())
        # Purge expired entries
        while q and (now - q[0]) > self._window:
            q.popleft()
        if len(q) >= self._max:
            return False
        q.append(now)
        return True

    def remove(self, client_id: str) -> None:
        """Clean up state for a disconnected client."""
        self._messages.pop(client_id, None)


# Singleton instance shared across the application.
manager = ConnectionManager()

# Event stream WebSocket manager (observability).
event_manager = ConnectionManager()
