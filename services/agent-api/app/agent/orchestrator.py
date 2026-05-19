import asyncio
import base64
import json
from concurrent.futures import Future
from datetime import datetime, timezone
from pathlib import Path
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
        asr_log_path: str | Path | None = None,
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
        self._tts_timeout_seconds = 8
        self._vision_modes: dict[str, str] = {}
        self._asr_tasks: dict[str, asyncio.Task] = {}
        self._asr_log_path = Path(asr_log_path) if asr_log_path else None

    async def handle_event(self, session_id: str, event: ClientEvent) -> None:
        if event.event == "vision.state":
            await self._handle_vision(session_id, event)
        elif event.event == "audio.data":
            await self._start_audio_task(session_id, event)
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
        mode = "tracking" if vision.user_visible and vision.confidence >= 0.5 else "idle"
        if mode == "idle" and self._vision_modes.get(session_id) == "idle":
            return
        self._vision_modes[session_id] = mode
        for action in actions:
            await self._avatar.send(session_id, action)
            await self._event_bus.publish(session_id, "avatar.action", action.model_dump())

    async def _start_audio_task(self, session_id: str, event: ClientEvent) -> None:
        task = self._asr_tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            await self._publish_asr_status(
                session_id,
                "cancelled",
                "上一段录音识别已取消",
                status="cancelled",
            )

        await self._publish_asr_status(session_id, "queued", "录音已进入识别队列")
        task = asyncio.create_task(self._handle_audio(session_id, event))
        self._asr_tasks[session_id] = task
        task.add_done_callback(lambda finished: self._finish_audio_task(session_id, finished))

    def _finish_audio_task(self, session_id: str, task: asyncio.Task) -> None:
        if self._asr_tasks.get(session_id) is task:
            self._asr_tasks.pop(session_id, None)

    async def _handle_audio(self, session_id: str, event: ClientEvent) -> None:
        try:
            audio_b64 = event.payload.get("audio", "")
            await self._publish_asr_status(
                session_id,
                "received",
                "后端已收到录音数据",
                encoded_size=len(audio_b64) if isinstance(audio_b64, str) else 0,
            )
            await self._publish_asr_status(session_id, "decode_base64", "正在解析浏览器录音")
            audio_bytes = base64.b64decode(audio_b64)
            await self._publish_asr_status(
                session_id,
                "transcribe",
                "正在调用 ASR 识别",
                audio_size=len(audio_bytes),
            )
            status_callback, pending_statuses, reported_phases = self._make_asr_status_callback(session_id)
            text = await self._asr.transcribe(audio_bytes, status_callback=status_callback)
            for future in pending_statuses:
                await asyncio.wrap_future(future)
            if "done" not in reported_phases:
                await self._publish_asr_status(
                    session_id,
                    "done",
                    "录音识别完成",
                    text_length=len(text.strip()),
                )
            if text.strip():
                await self._event_bus.publish(session_id, "asr.result", {"text": text})
                await self._handle_text(session_id, text)
            await self._publish_asr_status(session_id, "idle", "", status="idle")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            await self._event_bus.publish(session_id, "error", {"message": f"ASR error: {e}"})
            await self._publish_asr_status(session_id, "error", f"录音识别失败：{e}", status="error")

    async def _publish_asr_status(
        self,
        session_id: str,
        phase: str,
        message: str,
        status: str = "processing",
        **extra: Any,
    ) -> None:
        payload = {"status": status, "phase": phase}
        if message:
            payload["message"] = message
        payload.update(extra)
        self._write_asr_log(session_id, phase, payload)
        await self._event_bus.publish(session_id, "asr.status", payload)

    def _write_asr_log(self, session_id: str, phase: str, payload: dict[str, Any]) -> None:
        if self._asr_log_path is None:
            return

        record = {
            "time": datetime.now(timezone.utc).isoformat(),
            "event": "asr.status",
            "session_id": session_id,
            "phase": phase,
            **payload,
        }
        try:
            self._asr_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self._asr_log_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
        except Exception as exc:
            print(f"[asr-log] write failed: {exc}")

    def _make_asr_status_callback(self, session_id: str) -> tuple[Callable[[str, str], None], list[Future], list[str]]:
        loop = asyncio.get_running_loop()
        pending_statuses: list[Future] = []
        reported_phases: list[str] = []

        def report(phase: str, message: str) -> None:
            reported_phases.append(phase)
            future = asyncio.run_coroutine_threadsafe(
                self._publish_asr_status(session_id, phase, message),
                loop,
            )
            pending_statuses.append(future)

        return report, pending_statuses, reported_phases

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
                    audio = await asyncio.wait_for(
                        self._tts.synthesize(reply.reply_text),
                        timeout=self._tts_timeout_seconds,
                    )
                    audio_b64 = base64.b64encode(audio).decode("utf-8")
                    await self._event_bus.publish(session_id, "tts.audio", {
                        "audio": audio_b64,
                        "text": reply.reply_text,
                    })
                except asyncio.TimeoutError:
                    print(f"[tts] error: timeout after {self._tts_timeout_seconds}s")
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
        for task in self._asr_tasks.values():
            task.cancel()
        self._asr_tasks.clear()
        for llm in self._session_llms.values():
            await llm.close()
        self._session_llms.clear()
        await self._llm.close()
        await self._asr.close()
        await self._tts.close()
        await self._avatar.close()
        await self._memory.close()
