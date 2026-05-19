import asyncio
import json
import time

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


class SlowTTS:
    async def synthesize(self, text: str, voice: str = "") -> bytes:
        await asyncio.sleep(1)
        return b"wav"

    async def close(self):
        pass


class SlowASR:
    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000, status_callback=None) -> str:
        await asyncio.sleep(1)
        return "slow transcript"

    async def close(self):
        pass


class ReportingASR:
    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000, status_callback=None) -> str:
        if status_callback:
            status_callback("decoding_audio", "正在解码浏览器音频")
            status_callback("loading_model", "正在加载本地 Whisper 模型")
            status_callback("transcribing", "正在运行 Whisper 推理")
        return "voice transcript"

    async def close(self):
        pass


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


@pytest.mark.asyncio
async def test_tts_timeout_does_not_block_agent_reply():
    bus = RecordingEventBus()
    agent = AgentOrchestrator(
        event_bus=bus,
        llm=FakeLLM(reply_text="reply"),
        asr=NullASRAdapter(),
        tts=SlowTTS(),
        avatar=NullAvatarActionAdapter(),
        memory=FakeMemory(),
    )
    agent._tts_timeout_seconds = 0.01

    started = time.perf_counter()
    await agent.handle_event("session-a", ClientEvent(event="audio.transcript", payload={"text": "hello"}))
    elapsed = time.perf_counter() - started

    assert elapsed < 0.2
    assert any(event[1] == "agent.reply" and event[2]["reply_text"] == "reply" for event in bus.events)
    assert not any(event[1] == "tts.audio" for event in bus.events)
    assert agent._processing["session-a"] is False


@pytest.mark.asyncio
async def test_repeated_idle_vision_only_publishes_idle_once():
    bus = RecordingEventBus()
    agent = AgentOrchestrator(
        event_bus=bus,
        llm=FakeLLM(reply_text="reply"),
        asr=NullASRAdapter(),
        tts=NullTTSAdapter(),
        avatar=NullAvatarActionAdapter(),
        memory=FakeMemory(),
    )
    event = ClientEvent(
        event="vision.state",
        payload={
            "user_visible": False,
            "face_center_x": 0.5,
            "face_center_y": 0.42,
            "yaw": 0,
            "pitch": 0,
            "distance_m": 0.8,
            "confidence": 0,
        },
    )

    await agent.handle_event("session-a", event)
    await agent.handle_event("session-a", event)

    idle_events = [
        event
        for event in bus.events
        if event[1] == "avatar.action" and event[2]["payload"].get("name") == "idle_scan"
    ]
    assert len(idle_events) == 1


@pytest.mark.asyncio
async def test_audio_data_runs_asr_in_background_without_blocking_text():
    bus = RecordingEventBus()
    agent = AgentOrchestrator(
        event_bus=bus,
        llm=FakeLLM(reply_text="text reply"),
        asr=SlowASR(),
        tts=NullTTSAdapter(),
        avatar=NullAvatarActionAdapter(),
        memory=FakeMemory(),
    )

    started = time.perf_counter()
    await agent.handle_event("session-a", ClientEvent(event="audio.data", payload={"audio": "ZmFrZQ=="}))
    elapsed = time.perf_counter() - started
    await agent.handle_event("session-a", ClientEvent(event="audio.transcript", payload={"text": "typed text"}))

    assert elapsed < 0.2
    assert any(event[1] == "asr.status" and event[2]["status"] == "processing" for event in bus.events)
    assert any(event[1] == "agent.reply" and event[2]["reply_text"] == "text reply" for event in bus.events)


@pytest.mark.asyncio
async def test_audio_data_publishes_asr_stage_statuses():
    bus = RecordingEventBus()
    agent = AgentOrchestrator(
        event_bus=bus,
        llm=FakeLLM(reply_text="voice reply"),
        asr=ReportingASR(),
        tts=NullTTSAdapter(),
        avatar=NullAvatarActionAdapter(),
        memory=FakeMemory(),
    )

    await agent.handle_event("session-a", ClientEvent(event="audio.data", payload={"audio": "ZmFrZQ=="}))
    for _ in range(20):
        if any(event[1] == "asr.status" and event[2].get("phase") == "idle" for event in bus.events):
            break
        await asyncio.sleep(0.01)

    status_phases = [
        event[2].get("phase")
        for event in bus.events
        if event[1] == "asr.status"
    ]

    assert status_phases == [
        "queued",
        "received",
        "decode_base64",
        "transcribe",
        "decoding_audio",
        "loading_model",
        "transcribing",
        "done",
        "idle",
    ]


@pytest.mark.asyncio
async def test_audio_data_writes_asr_statuses_to_log_file(tmp_path):
    log_path = tmp_path / "asr.log"
    bus = RecordingEventBus()
    agent = AgentOrchestrator(
        event_bus=bus,
        llm=FakeLLM(reply_text="voice reply"),
        asr=ReportingASR(),
        tts=NullTTSAdapter(),
        avatar=NullAvatarActionAdapter(),
        memory=FakeMemory(),
        asr_log_path=log_path,
    )

    await agent.handle_event("session-a", ClientEvent(event="audio.data", payload={"audio": "ZmFrZQ=="}))
    for _ in range(20):
        if any(event[1] == "asr.status" and event[2].get("phase") == "idle" for event in bus.events):
            break
        await asyncio.sleep(0.01)

    records = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    phases = [record["phase"] for record in records]

    assert phases == [
        "queued",
        "received",
        "decode_base64",
        "transcribe",
        "decoding_audio",
        "loading_model",
        "transcribing",
        "done",
        "idle",
    ]
    assert records[0]["session_id"] == "session-a"
    assert records[0]["event"] == "asr.status"
