import pytest

from app.adapters.asr import NullASRAdapter
from app.adapters.avatar_action import NullAvatarActionAdapter
from app.adapters.tts import NullTTSAdapter
from app.agent.orchestrator import AgentOrchestrator
from app.schemas import AgentReply, ClientEvent


class RecordingEventBus:
    def __init__(self):
        self.events = []

    async def publish(self, session_id, event, payload):
        self.events.append((session_id, event, payload))


class FakeMemory:
    async def load_session(self, session_id):
        return {"id": session_id, "user_id": "", "history": [], "context": {}}

    async def save_session(self, session_id, history, context, user_id=""):
        self.saved = {
            "session_id": session_id,
            "history": history,
            "context": context,
            "user_id": user_id,
        }

    async def load_user_profile(self, user_id):
        return {}

    async def update_user_profile(self, user_id, updates):
        self.updated = {"user_id": user_id, "updates": updates}

    async def close(self):
        pass


class FakeLLM:
    def __init__(self, reply_text="OK", fail=False):
        self.reply_text = reply_text
        self.fail = fail
        self.calls = []
        self.closed = False

    async def chat(self, messages, tools=None):
        self.calls.append({"messages": messages, "tools": tools})
        if self.fail:
            raise RuntimeError("invalid api key")
        return AgentReply(reply_text=self.reply_text)

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_session_config_connects_deepseek_key_and_uses_session_llm():
    bus = RecordingEventBus()
    base_llm = FakeLLM(reply_text="base")
    session_llm = FakeLLM(reply_text="deepseek")

    agent = AgentOrchestrator(
        event_bus=bus,
        llm=base_llm,
        asr=NullASRAdapter(),
        tts=NullTTSAdapter(),
        avatar=NullAvatarActionAdapter(),
        memory=FakeMemory(),
        session_llm_factory=lambda api_key: session_llm,
    )

    await agent.handle_event(
        "session-a",
        ClientEvent(event="session.config", payload={"deepseek_api_key": "sk-deepseek"}),
    )
    await agent.handle_event(
        "session-a",
        ClientEvent(event="audio.transcript", payload={"text": "你好"}),
    )

    connection_events = [event for event in bus.events if event[1] == "llm.connection"]
    assert connection_events[-1][2] == {
        "ok": True,
        "provider": "deepseek",
        "message": "DeepSeek 连接成功",
    }
    assert len(session_llm.calls) == 2
    assert len(base_llm.calls) == 0
    assert any(event[1] == "agent.reply" and event[2]["reply_text"] == "deepseek" for event in bus.events)


@pytest.mark.asyncio
async def test_session_config_reports_deepseek_connection_failure():
    bus = RecordingEventBus()
    failing_llm = FakeLLM(fail=True)

    agent = AgentOrchestrator(
        event_bus=bus,
        llm=FakeLLM(reply_text="base"),
        asr=NullASRAdapter(),
        tts=NullTTSAdapter(),
        avatar=NullAvatarActionAdapter(),
        memory=FakeMemory(),
        session_llm_factory=lambda api_key: failing_llm,
    )

    await agent.handle_event(
        "session-a",
        ClientEvent(event="session.config", payload={"deepseek_api_key": "bad-key"}),
    )

    connection_events = [event for event in bus.events if event[1] == "llm.connection"]
    assert connection_events[-1][2]["ok"] is False
    assert connection_events[-1][2]["provider"] == "deepseek"
    assert "invalid api key" in connection_events[-1][2]["message"]
    assert failing_llm.closed is True
