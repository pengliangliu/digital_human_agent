from abc import ABC, abstractmethod
from pathlib import Path

from app.config import project_root


class TTSAdapter(ABC):
    @abstractmethod
    async def synthesize(self, text: str, voice: str = "") -> bytes:
        """Return WAV audio bytes."""

    @abstractmethod
    async def close(self) -> None:
        ...


class EdgeTTSAdapter(TTSAdapter):
    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural") -> None:
        self._voice = voice

    async def synthesize(self, text: str, voice: str = "") -> bytes:
        import edge_tts
        import io

        v = voice or self._voice
        communicate = edge_tts.Communicate(text, v)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    async def close(self) -> None:
        pass


class OpenAITTSAdapter(TTSAdapter):
    def __init__(self, api_key: str, base_url: str, voice: str = "alloy") -> None:
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._voice = voice

    async def synthesize(self, text: str, voice: str = "") -> bytes:
        v = voice or self._voice
        resp = await self._client.audio.speech.create(model="tts-1", voice=v, input=text, response_format="wav")
        return resp.content

    async def close(self) -> None:
        await self._client.close()


class LocalTTSAdapter(TTSAdapter):
    def __init__(self, engine: str = "cosyvoice") -> None:
        self._engine = engine

    async def synthesize(self, text: str, voice: str = "") -> bytes:
        return b""

    async def close(self) -> None:
        pass


class NullTTSAdapter(TTSAdapter):
    async def synthesize(self, text: str, voice: str = "") -> bytes:
        return b""

    async def close(self) -> None:
        pass
