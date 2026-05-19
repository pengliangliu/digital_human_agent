from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class ASRAdapter(ABC):
    @abstractmethod
    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class WhisperCloudAdapter(ASRAdapter):
    def __init__(self, api_key: str, base_url: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        import io
        import wave

        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
        buf.seek(0)
        buf.name = "audio.wav"

        resp = await self._client.audio.transcriptions.create(model="whisper-1", file=buf, language="zh")
        return resp.text

    async def close(self) -> None:
        await self._client.close()


class LocalWhisperAdapter(ASRAdapter):
    def __init__(
        self,
        model_size: str = "small",
        model_path: str = "",
        device: str = "cuda",
        compute_type: str = "int8",
    ) -> None:
        self._model_size = model_size
        self._model_path = model_path
        self._device = device
        self._compute_type = compute_type
        self._model = None

    def _load(self) -> None:
        if self._model is None:
            from faster_whisper import WhisperModel

            model_ref = self._model_path or self._model_size
            self._model = WhisperModel(model_ref, device=self._device, compute_type=self._compute_type)

    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        import io
        import wave
        import asyncio
        import numpy as np

        self._load()
        buf = io.BytesIO(audio_data)
        with wave.open(buf, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            audio_np = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

        segments, _ = await asyncio.to_thread(lambda: list(self._model.transcribe(audio_np, language="zh")))
        return " ".join(s.text for s in segments)

    async def close(self) -> None:
        self._model = None


class NullASRAdapter(ASRAdapter):
    async def transcribe(self, audio_data: bytes, sample_rate: int = 16000) -> str:
        return ""

    async def close(self) -> None:
        pass
