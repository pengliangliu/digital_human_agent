import pytest

from app import main


class EarlyClosedWebSocket:
    async def accept(self):
        pass

    async def receive_json(self):
        raise RuntimeError('WebSocket is not connected. Need to call "accept" first.')


@pytest.mark.asyncio
async def test_session_ws_treats_pre_accept_disconnect_as_normal_close(monkeypatch, capsys):
    bus = main.SessionEventBus()
    monkeypatch.setattr(main, "event_bus", bus)
    monkeypatch.setattr(main, "agent", None)

    await main.session_ws(EarlyClosedWebSocket(), "avatar-race")

    assert bus.active_sessions() == 0
    assert "[ws:avatar-race] error" not in capsys.readouterr().out
