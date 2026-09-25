"""WebSocket connection manager for real-time digital twin telemetry streaming."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, Set, Union
from fastapi import WebSocket, WebSocketDisconnect

from backend.schemas.websocket import WebSocketMessage

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manages active WebSocket client connections and broadcasts live telemetry packets."""

    def __init__(self) -> None:
        self._active_connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    @property
    def active_connections_count(self) -> int:
        """Return total number of connected clients."""
        return len(self._active_connections)

    async def connect(self, websocket: WebSocket) -> None:
        """Accept an incoming WebSocket connection and register client."""
        await websocket.accept()
        async with self._lock:
            self._active_connections.add(websocket)
        logger.info("WebSocket client connected. Active connections: %d", len(self._active_connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Unregister a disconnected WebSocket client."""
        async with self._lock:
            self._active_connections.discard(websocket)
        logger.info("WebSocket client disconnected. Active connections: %d", len(self._active_connections))

    async def broadcast(self, message: Union[Dict[str, Any], WebSocketMessage]) -> None:
        """Broadcast a JSON message packet to all connected clients."""
        if not self._active_connections:
            return

        payload = message.model_dump() if isinstance(message, WebSocketMessage) else message
        dead_connections: Set[WebSocket] = set()

        async with self._lock:
            connections = list(self._active_connections)

        for connection in connections:
            try:
                await connection.send_json(payload)
            except Exception as exc:
                logger.warning("Failed to send WebSocket message to client: %s", exc)
                dead_connections.add(connection)

        if dead_connections:
            async with self._lock:
                for dead in dead_connections:
                    self._active_connections.discard(dead)
            logger.info("Pruned %d dead WebSocket connections", len(dead_connections))

    def broadcast_from_thread(
        self,
        message: Union[Dict[str, Any], WebSocketMessage],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        """Schedule a broadcast coroutine from an external worker thread onto the main event loop."""
        if not self._active_connections:
            return
        if loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)


# Global WebSocket Manager singleton
ws_manager = WebSocketManager()
