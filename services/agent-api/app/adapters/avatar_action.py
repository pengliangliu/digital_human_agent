from abc import ABC, abstractmethod
from typing import Any

from app.schemas import AvatarAction


class AvatarActionAdapter(ABC):
    @abstractmethod
    async def send(self, session_id: str, action: AvatarAction) -> None:
        ...

    @abstractmethod
    async def load_avatar(self, session_id: str, avatar_id: str, model_path: str) -> None:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class NullAvatarActionAdapter(AvatarActionAdapter):
    async def send(self, session_id: str, action: AvatarAction) -> None:
        print(f"[avatar:{session_id}] [{action.priority}] {action.type}: {action.payload}")

    async def load_avatar(self, session_id: str, avatar_id: str, model_path: str) -> None:
        print(f"[avatar:{session_id}] load_avatar: {avatar_id} -> {model_path}")

    async def close(self) -> None:
        pass


class HttpAvatarActionAdapter(AvatarActionAdapter):
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    async def send(self, session_id: str, action: AvatarAction) -> None:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                await client.post(
                    f"{self._base_url}/avatar/action",
                    json={
                        "session_id": session_id,
                        "type": action.type,
                        "name": action.payload.get("name", action.type),
                        "intensity": action.payload.get("intensity", 0.5),
                        "duration_ms": action.duration_ms or 1000,
                        **{k: v for k, v in action.payload.items() if k not in ("name", "intensity")},
                    },
                )
            except Exception as e:
                print(f"[avatar-http:{session_id}] error: {e}")

    async def load_avatar(self, session_id: str, avatar_id: str, model_path: str) -> None:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                await client.post(
                    f"{self._base_url}/avatar/load",
                    json={"avatar_id": avatar_id, "model_path": model_path},
                )
            except Exception as e:
                print(f"[avatar-http:{session_id}] load error: {e}")

    async def close(self) -> None:
        pass
