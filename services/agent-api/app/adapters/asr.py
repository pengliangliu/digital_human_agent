from abc import ABC, abstractmethod
import subprocess
from typing import Callable


ASRStatusCallback = Callable[[str, str], None]


class ASRAdapter(ABC):
    @abstractmethod
    async def transcribe(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        status_callback: ASRStatusCallback | None = None,
    ) -> str:
        ...

    @abstractmethod
    async def close(self) -> None:
        ...


class WhisperCloudAdapter(ASRAdapter):
    def __init__(self, api_key: str, base_url: str) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def transcribe(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        status_callback: ASRStatusCallback | None = None,
    ) -> str:
        import io
        import wave

        if status_callback:
            status_callback("preparing_audio", "正在准备上传给云端 ASR 的音频")
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(audio_data)
        buf.seek(0)
        buf.name = "audio.wav"

        if status_callback:
            status_callback("cloud_transcribing", "正在等待云端 ASR 返回结果")
        resp = await self._client.audio.transcriptions.create(model="whisper-1", file=buf, language="zh")
        if status_callback:
            status_callback("done", "云端 ASR 识别完成")
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
            try:
                from faster_whisper import WhisperModel

                model_ref = self._model_path or self._model_size
                try:
                    self._model = WhisperModel(model_ref, device=self._device, compute_type=self._compute_type)
                except Exception as exc:
                    if self._device == "cuda" and _is_cuda_runtime_error(exc):
                        print(f"[asr] CUDA unavailable, falling back to CPU: {exc}")
                        self._device = "cpu"
                        self._model = WhisperModel(model_ref, device=self._device, compute_type=self._compute_type)
                    else:
                        raise
            except Exception as exc:
                raise RuntimeError(self._format_load_error(exc)) from exc

    def _format_load_error(self, exc: Exception) -> str:
        message = str(exc)
        if isinstance(exc, ModuleNotFoundError) and "faster_whisper" in message:
            return "本地 ASR 依赖 faster-whisper 未安装，请运行 pip install -e .[local] 或 pip install faster-whisper。"
        if self._device == "cuda" and _is_cuda_runtime_error(exc):
            return f"本地 ASR CUDA 环境不可用，缺少 CUDA/cuBLAS/cuDNN 运行库：{message}。请安装匹配的 NVIDIA CUDA 运行库，或设置 ASR_DEVICE=cpu 切回 CPU。"
        return f"本地 ASR 模型加载失败：{message}"

    async def transcribe(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        status_callback: ASRStatusCallback | None = None,
    ) -> str:
        import asyncio

        return await asyncio.to_thread(self._transcribe_sync, audio_data, sample_rate, status_callback)

    def _transcribe_sync(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        status_callback: ASRStatusCallback | None = None,
    ) -> str:
        if status_callback:
            status_callback("loading_model", "正在加载本地 Whisper 模型")
        self._load()
        if status_callback:
            status_callback("decoding_audio", "正在解码浏览器音频")
        audio_np = _decode_audio_to_float32(audio_data, sample_rate)

        if status_callback:
            status_callback("transcribing", "正在运行 Whisper 推理")
        text = self._transcribe_loaded_model(audio_np, status_callback)
        if status_callback:
            status_callback("done", "Whisper 推理完成")
        return text

    def _transcribe_loaded_model(self, audio_np, status_callback: ASRStatusCallback | None = None) -> str:
        try:
            return self._collect_transcription_text(audio_np)
        except Exception as exc:
            if self._device == "cuda" and _is_cuda_runtime_error(exc):
                print(f"[asr] CUDA transcribe failed, falling back to CPU: {exc}")
                if status_callback:
                    status_callback("cuda_fallback", "CUDA 运行库不可用，正在切换 CPU 重新识别")
                self._device = "cpu"
                self._model = None
                if status_callback:
                    status_callback("loading_model", "正在加载 CPU Whisper 模型")
                self._load()
                if status_callback:
                    status_callback("transcribing", "正在使用 CPU 运行 Whisper 推理")
                return self._collect_transcription_text(audio_np)
            raise

    def _collect_transcription_text(self, audio_np) -> str:
        segments, _ = self._model.transcribe(audio_np, language="zh")
        return " ".join(s.text.strip() for s in segments if s.text.strip()).strip()

    async def close(self) -> None:
        self._model = None


def _decode_audio_to_float32(audio_data: bytes, sample_rate: int):
    import io
    import wave
    import numpy as np

    try:
        buf = io.BytesIO(audio_data)
        with wave.open(buf, "rb") as wf:
            frames = wf.readframes(wf.getnframes())
            return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    except wave.Error:
        return _decode_with_ffmpeg(audio_data, sample_rate)


def _decode_with_ffmpeg(audio_data: bytes, sample_rate: int):
    import numpy as np

    cmd = [
        _ffmpeg_executable(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "pipe:1",
    ]
    try:
        result = subprocess.run(
            cmd,
            input=audio_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("无法解码浏览器 audio/webm：未找到 ffmpeg，请安装 imageio-ffmpeg 或系统 ffmpeg。") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode("utf-8", errors="ignore").strip()
        raise RuntimeError(f"无法解码浏览器音频，ffmpeg 转码失败：{detail}") from exc

    if not result.stdout:
        raise RuntimeError("无法解码浏览器音频，ffmpeg 未输出 PCM 数据。")
    return np.frombuffer(result.stdout, dtype=np.int16).astype(np.float32) / 32768.0


def _ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _is_cuda_runtime_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(token in message for token in ("cuda", "cublas", "cudnn", "cufft", "curand", "cusolver"))


class NullASRAdapter(ASRAdapter):
    async def transcribe(
        self,
        audio_data: bytes,
        sample_rate: int = 16000,
        status_callback: ASRStatusCallback | None = None,
    ) -> str:
        return ""

    async def close(self) -> None:
        pass
