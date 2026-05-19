import asyncio
import base64
from typing import Any, Callable

from app.adapters.llm import LLMAdapter
from app.adapters.asr import ASRAdapter
from app.adapters.tts import TTSAdapter
from app.adapters.avatar_action import AvatarActionAdapter
from app.agent.behavior_planner import BehaviorPlanner
from app.agent.prompts import SYSTEM_PROMPT, WELCOME_MESSAGE
from app.agent.tools import AgentTools
from app.agent.memory import SessionMemory
from app.schemas import AgentReply, ClientEvent, VisionState, AVAILABLE_TOOLS


class AgentOrchestrator:
    def __init__(
        self,
        event_bus: Any,
        llm: LLMAdapter,
        asr: ASRAdapter,
        tts: TTSAdapter,
        avatar: AvatarActionAdapter,
        memory: SessionMemory,
        session_llm_factory: Callable[[str], LLMAdapter] | None = None,
    ) -> None:
        self._event_bus = event_bus
        self._llm = llm
        self._asr = asr
        self._tts = tts
        self._avatar = avatar
        self._behavior = BehaviorPlanner()
        self._tools = AgentTools()
        self._memory = memory
        self._session_llm_factory = session_llm_factory
        self._session_llms: dict[str, LLMAdapter] = {}
        self._processing: dict[str, bool] = {}
        self._tts_enabled: dict[str, bool] = {}

    async def handle_event(self, session_id: str, event: ClientEvent) -> None:
        if event.event == "vision.state":
            await self._handle_vision(session_id, event)
        elif event.event == "audio.data":
            await self._handle_audio(session_id, event)
        elif event.event == "audio.transcript":
            await self._handle_text(session_id, event.payload.get("text", ""))
        elif event.event == "session.init":
            await self._handle_session_init(session_id)
        elif event.event == "session.config":
            await self._handle_session_config(session_id, event)

    async def _handle_session_config(self, session_id: str, event: ClientEvent) -> None:
        if "tts_enabled" in event.payload:
            self._tts_enabled[session_id] = event.payload.get("tts_enabled", True)

        api_key = event.payload.get("deepseek_api_key", "")
        if isinstance(api_key, str) and api_key.strip():
            await self._configure_session_deepseek(session_id, api_key.strip())

    async def _configure_session_deepseek(self, session_id: str, api_key: str) -> None:
        if self._session_llm_factory is None:
            await self._event_bus.publish(session_id, "llm.connection", {
                "ok": False,
                "provider": "deepseek",
                "message": "后端未启用 DeepSeek 会话配置",
            })
            return

        llm = self._session_llm_factory(api_key)
        try:
            await llm.chat([
                {"role": "system", "content": "只回复 OK。"},
                {"role": "user", "content": "ping"},
            ])
        except Exception as exc:
            await llm.close()
            await self._event_bus.publish(session_id, "llm.connection", {
                "ok": False,
                "provider": "deepseek",
                "message": f"DeepSeek 连接失败：{exc}",
            })
            return

        old_llm = self._session_llms.pop(session_id, None)
        if old_llm:
            await old_llm.close()
        self._session_llms[session_id] = llm
        await self._event_bus.publish(session_id, "llm.connection", {
            "ok": True,
            "provider": "deepseek",
            "message": "DeepSeek 连接成功",
        })

    async def _handle_vision(self, session_id: str, event: ClientEvent) -> None:
        vision = VisionState.model_validate(event.payload)
        actions = self._behavior.from_vision(vision)
        for action in actions:
            await self._avatar.send(session_id, action)
            await self._event_bus.publish(session_id, "avatar.action", action.model_dump())

    async def _handle_audio(self, session_id: str, event: ClientEvent) -> None:
        try:
            audio_b64 = event.payload.get("audio", "")
            audio_bytes = base64.b64decode(audio_b64)
            text = await self._asr.transcribe(audio_bytes)
            if text.strip():
                await self._event_bus.publish(session_id, "asr.result", {"text": text})
                await self._handle_text(session_id, text)
        except Exception as e:
            await self._event_bus.publish(session_id, "error", {"message": f"ASR error: {e}"})

    async def _handle_text(self, session_id: str, text: str) -> None:
        if self._processing.get(session_id):
            return
        self._processing[session_id] = True
        try:
            session = await self._memory.load_session(session_id)
            history: list = session.get("history", [])
            context: dict = session.get("context", {})
            user_id = session.get("user_id", "")

            profile = await self._memory.load_user_profile(user_id) if user_id else {}
            prefs = profile.get("preferences", {})

            history.append({"role": "user", "content": text})
            system_msg = self._build_system(prefs)
            messages = [system_msg] + history

            llm = self._session_llms.get(session_id, self._llm)
            reply = await llm.chat(messages, AVAILABLE_TOOLS)
            history.append({"role": "assistant", "content": reply.reply_text})

            # Execute tool calls
            for tc in reply.tool_calls:
                result = await self._tools.handle_tool_call(tc)
                await self._event_bus.publish(session_id, "tool.result", {
                    "tool": tc.name,
                    "result": result,
                })

            # Update memory
            if reply.memory_updates:
                user_id = user_id or f"user_{session_id}"
                await self._memory.update_user_profile(user_id, reply.memory_updates)

            # Trim history
            max_turns = 20
            if len(history) > max_turns * 2 + 1:
                history = history[-(max_turns * 2 + 1):]

            await self._memory.save_session(session_id, history, context, user_id)

            # Send reply to frontend
            await self._event_bus.publish(session_id, "agent.reply", reply.model_dump())

            # Generate and send actions
            for action in self._behavior.from_agent_reply(reply.model_dump()):
                await self._avatar.send(session_id, action)
                await self._event_bus.publish(session_id, "avatar.action", action.model_dump())

            # TTS
            if self._tts_enabled.get(session_id, True):
                try:
                    audio = await self._tts.synthesize(reply.reply_text)
                    audio_b64 = base64.b64encode(audio).decode("utf-8")
                    await self._event_bus.publish(session_id, "tts.audio", {
                        "audio": audio_b64,
                        "text": reply.reply_text,
                    })
                except Exception as e:
                    print(f"[tts] error: {e}")

        except Exception as e:
            await self._event_bus.publish(session_id, "error", {"message": str(e)})
        finally:
            self._processing[session_id] = False

    async def _handle_session_init(self, session_id: str) -> None:
        await self._event_bus.publish(session_id, "agent.reply", {
            "reply_text": WELCOME_MESSAGE,
            "emotion": "friendly",
            "intent": "greeting",
            "actions": [{"type": "gesture", "name": "wave", "intensity": 0.6}],
            "tool_calls": [],
        })

    def _build_system(self, prefs: dict) -> dict:
        extras = ""
        if prefs:
            extras = f"\n用户偏好：{prefs}"
        return {"role": "system", "content": SYSTEM_PROMPT + extras}

    async def close(self) -> None:
        for llm in self._session_llms.values():
            await llm.close()
        self._session_llms.clear()
        await self._llm.close()
        await self._asr.close()
        await self._tts.close()
        await self._avatar.close()
        await self._memory.close()
