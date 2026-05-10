import asyncio

import pytest

from app.runtime.event_bus import SessionEventBus


class FailingSocket:
    async def send_json(self, payload):
        raise RuntimeError("socket closed")


@pytest.mark.asyncio
async def test_publish_removes_dead_socket_without_deadlocking():
    bus = SessionEventBus()
    socket = FailingSocket()

    await bus.attach("mirror-1", socket)
    await asyncio.wait_for(bus.publish("mirror-1", "avatar.action", {"type": "look_at"}), timeout=0.2)

    assert bus.active_sessions() == 0
