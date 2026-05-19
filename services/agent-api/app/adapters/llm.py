from abc import ABC, abstractmethod
from typing import Any

from app.schemas import AgentReply, ToolCall


class LLMAdapter(ABC):
    @abstractmethod
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AgentReply:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class OpenAIAdapter(LLMAdapter):
    def __init__(self, api_key: str, base_url: str, model: str, temperature: float = 0.7, max_tokens: int = 1024) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AgentReply:
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        resp = await self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        content = choice.message.content or ""

        return _parse_llm_content(content, choice.message.tool_calls)

    async def close(self) -> None:
        await self._client.close()


class OllamaAdapter(LLMAdapter):
    def __init__(self, host: str, model: str, temperature: float = 0.7, max_tokens: int = 1024) -> None:
        import httpx

        self._client = httpx.AsyncClient(base_url=host, timeout=60.0)
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AgentReply:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": self._temperature, "num_predict": self._max_tokens},
        }
        if tools:
            clean_tools = [{"type": "function", "function": t["function"]} for t in tools]
            payload["tools"] = clean_tools

        resp = await self._client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()
        content = data.get("message", {}).get("content", "")
        tool_calls_raw = data.get("message", {}).get("tool_calls", [])

        tool_calls = []
        for tc in tool_calls_raw:
            fc = tc.get("function", {})
            tool_calls.append(
                type("_TC", (), {
                    "id": tc.get("id", ""),
                    "type": "function",
                    "function": type("_F", (), {
                        "name": fc.get("name", ""),
                        "arguments": fc.get("arguments", "{}"),
                    }),
                })()
            )

        return _parse_llm_content(content, tool_calls or None)

    async def close(self) -> None:
        await self._client.aclose()


class AnthropicAdapter(LLMAdapter):
    def __init__(self, api_key: str, model: str, temperature: float = 0.7, max_tokens: int = 1024) -> None:
        import httpx

        self._client = httpx.AsyncClient(
            base_url="https://api.anthropic.com",
            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
            timeout=60.0,
        )
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AgentReply:
        system = ""
        chat_messages = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                chat_messages.append(m)

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": chat_messages,
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
        }
        if system:
            payload["system"] = system
        if tools:
            payload["tools"] = _to_anthropic_tools(tools)

        resp = await self._client.post("/v1/messages", json=payload)
        resp.raise_for_status()
        data = resp.json()

        content = ""
        tool_calls = []
        for block in data.get("content", []):
            if block["type"] == "text":
                content = block["text"]
            elif block["type"] == "tool_use":
                tool_calls.append(
                    type("_TC", (), {
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": type("_F", (), {
                            "name": block.get("name", ""),
                            "arguments": _safe_json_dumps(block.get("input", {})),
                        })(),
                    })()
                )

        return _parse_llm_content(content, tool_calls or None)

    async def close(self) -> None:
        await self._client.aclose()


def _to_anthropic_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for t in tools:
        func = t.get("function", t)
        result.append({
            "name": func.get("name", ""),
            "description": func.get("description", ""),
            "input_schema": func.get("parameters", {}),
        })
    return result


def _safe_json_dumps(obj: Any) -> str:
    import json
    return json.dumps(obj, ensure_ascii=False)


class MockLLMAdapter(LLMAdapter):
    async def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> AgentReply:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        return AgentReply(
            reply_text=f"收到：{last_user}（请设置 OPENAI_API_KEY 环境变量以启用云端大模型）",
            emotion="friendly",
            intent="chat",
            actions=[{"type": "gesture", "name": "nod", "intensity": 0.4}],
        )

    async def close(self) -> None:
        pass


def _parse_llm_content(content: str, tool_calls: list | None) -> AgentReply:
    import json
    import re

    json_match = re.search(r"\{[\s\S]*\}", content.strip())
    if json_match:
        try:
            data = json.loads(json_match.group())
            return AgentReply(
                reply_text=data.get("reply_text", content),
                emotion=data.get("emotion", "neutral"),
                intent=data.get("intent", "chat"),
                actions=_validate_actions(data.get("actions", [])),
                tool_calls=_build_tool_calls(data.get("tool_calls", [])),
                memory_updates=data.get("memory_updates", {}),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    # Plain text fallback
    tc_list = []
    if tool_calls:
        for tc in tool_calls:
            args = _coerce_tool_arguments(tc.function.arguments) if hasattr(tc.function, "arguments") else {}
            tc_list.append(
                ToolCall(
                    name=tc.function.name if hasattr(tc.function, "name") else "",
                    arguments=args,
                )
            )

    return AgentReply(
        reply_text=content,
        emotion="neutral",
        intent="chat",
        actions=[],
        tool_calls=tc_list,
    )


_VALID_GESTURES = {"nod", "shake_head", "wave", "point_left", "point_right", "idle_scan", "thinking"}
_VALID_EXPRESSIONS = {"neutral", "smile", "friendly", "surprised", "thinking", "concerned", "happy"}
_VALID_DIRECT_AVATAR_ACTIONS = {
    "lip_sync",
    "pose",
    "bone_pose",
    "morph_target",
    "viseme",
    "animation_clip",
    "motion_sequence",
    "try_on",
    "load_avatar",
}


def _validate_actions(actions: list[dict]) -> list[dict]:
    result = []
    for a in actions:
        t = a.get("type", "")
        if t == "gesture" and a.get("name") not in _VALID_GESTURES:
            continue
        if t == "expression" and a.get("name") not in _VALID_EXPRESSIONS:
            continue
        if t not in {"gesture", "expression"} and t not in _VALID_DIRECT_AVATAR_ACTIONS:
            continue
        result.append(a)
    return result


def _coerce_tool_arguments(raw: Any) -> dict[str, Any]:
    import json

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _build_tool_calls(raw: list[dict]) -> list[ToolCall]:
    result: list[ToolCall] = []
    for tc in raw:
        result.append(ToolCall(name=tc.get("name", ""), arguments=_coerce_tool_arguments(tc.get("arguments", {}))))
    return result
