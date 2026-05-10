import asyncio
from collections import defaultdict

from fastapi import WebSocket


class SessionEventBus:
    def __init__(self) -> None:
        self._sessions: dict[str, list[WebSocket]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def attach(self, session_id: str, ws: WebSocket) -> None:
        async with self._lock:
            self._sessions[session_id].append(ws)

    async def detach(self, session_id: str, ws: WebSocket) -> None:
        async with self._lock:
            try:
                self._sessions[session_id].remove(ws)
                if not self._sessions[session_id]:
                    del self._sessions[session_id]
            except (ValueError, KeyError):
                pass

    async def publish(self, session_id: str, event: str, data: dict) -> None:
        dead: list[WebSocket] = []
        async with self._lock:
            sockets = list(self._sessions.get(session_id, []))
        for ws in sockets:
            try:
                await ws.send_json({"event": event, "payload": data})
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    await self.detach(session_id, ws)

    def active_sessions(self) -> int:
        return len(self._sessions)
