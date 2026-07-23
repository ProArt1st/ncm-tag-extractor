from __future__ import annotations

import json
from typing import Any
from fastapi import WebSocket, WebSocketDisconnect
from server.schemas import ProgressMessageSchema


class ConnectionManager:
    """Manage active WebSocket connections and broadcast progress."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: ProgressMessageSchema) -> None:
        """Broadcast ProgressMessageSchema payload to all connected WebSocket clients."""
        if not self.active_connections:
            return
        payload = message.model_dump_json()
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(payload)
            except Exception:
                disconnected.append(connection)
        for dead_conn in disconnected:
            self.disconnect(dead_conn)


ws_manager = ConnectionManager()
