import pytest

from app.adapters.avatar_action import HttpAvatarActionAdapter
from app.schemas import AvatarAction


@pytest.mark.asyncio
async def test_http_avatar_adapter_forwards_canonical_action_payload(monkeypatch):
    posts = []

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            posts.append((url, json))

    import httpx

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    adapter = HttpAvatarActionAdapter("http://avatar-runtime")

    await adapter.send(
        "session-a",
        AvatarAction(
            type="morph_target",
            priority="realtime",
            duration_ms=80,
            payload={"name": "mouthSmile_L", "weight": 0.5},
        ),
    )

    assert posts == [
        (
            "http://avatar-runtime/avatar/action",
            {
                "session_id": "session-a",
                "type": "morph_target",
                "priority": "realtime",
                "duration_ms": 80,
                "payload": {"name": "mouthSmile_L", "weight": 0.5},
            },
        )
    ]
