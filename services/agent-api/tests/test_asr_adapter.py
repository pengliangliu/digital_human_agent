import sys
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from app.adapters.asr import LocalWhisperAdapter


def test_local_whisper_loads_model_path_with_cuda_int8(monkeypatch):
    captured = {}

    class FakeWhisperModel:
        def __init__(self, model_ref, device, compute_type):
            captured["model_ref"] = model_ref
            captured["device"] = device
            captured["compute_type"] = compute_type

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel))

    adapter = LocalWhisperAdapter(
        model_size="small",
        model_path="D:/models/faster-whisper-small",
        device="cuda",
        compute_type="int8",
    )
    adapter._load()

    assert captured == {
        "model_ref": "D:/models/faster-whisper-small",
        "device": "cuda",
        "compute_type": "int8",
    }


def test_decode_webm_audio_with_ffmpeg_fallback(monkeypatch):
    from app.adapters import asr as asr_module

    expected_pcm = np.array([0, 32767, -32768], dtype=np.int16).tobytes()
    captured = {}

    def fake_run(cmd, input, stdout, stderr, check):
        captured["cmd"] = cmd
        captured["input"] = input
        captured["check"] = check
        return SimpleNamespace(stdout=expected_pcm)

    monkeypatch.setattr(asr_module, "_ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr(asr_module.subprocess, "run", fake_run)

    audio = asr_module._decode_audio_to_float32(b"fake-webm", sample_rate=16000)

    assert captured["input"] == b"fake-webm"
    assert captured["check"] is True
    assert captured["cmd"][:2] == ["ffmpeg", "-hide_banner"]
    assert audio.dtype == np.float32
    assert audio.tolist() == [0.0, 32767 / 32768.0, -1.0]


def test_local_whisper_reports_missing_dependency():
    adapter = LocalWhisperAdapter()

    try:
        raise ModuleNotFoundError("No module named 'faster_whisper'")
    except ModuleNotFoundError as exc:
        message = adapter._format_load_error(exc)

    assert "faster-whisper" in message
    assert "pip install" in message


def test_local_whisper_reports_cuda_failure():
    adapter = LocalWhisperAdapter(device="cuda")

    message = adapter._format_load_error(RuntimeError("CUDA failed with error code 35"))

    assert "CUDA" in message
    assert "ASR_DEVICE=cpu" in message


def test_local_whisper_reports_cuda_library_failure():
    adapter = LocalWhisperAdapter(device="cuda")

    message = adapter._format_load_error(RuntimeError("Library cublas64_12.dll is not found"))

    assert "CUDA" in message
    assert "cuBLAS" in message
    assert "ASR_DEVICE=cpu" in message


def test_local_whisper_falls_back_to_cpu_when_cuda_library_missing(monkeypatch):
    calls = []

    class FakeWhisperModel:
        def __init__(self, model_ref, device, compute_type):
            calls.append({"device": device, "compute_type": compute_type})
            if device == "cuda":
                raise RuntimeError("Library cublas64_12.dll is not found")

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel))

    adapter = LocalWhisperAdapter(device="cuda", compute_type="int8")
    adapter._load()

    assert calls == [
        {"device": "cuda", "compute_type": "int8"},
        {"device": "cpu", "compute_type": "int8"},
    ]


@pytest.mark.asyncio
async def test_local_whisper_falls_back_to_cpu_when_cuda_transcribe_fails(monkeypatch):
    from app.adapters import asr as asr_module

    calls = []
    statuses = []

    class Segment:
        text = "hello cpu"

    class FakeWhisperModel:
        def __init__(self, model_ref, device, compute_type):
            self.device = device
            calls.append(device)

        def transcribe(self, audio, language):
            if self.device == "cuda":
                raise RuntimeError("Library cublas64_12.dll is not found or cannot be loaded")
            return iter([Segment()]), object()

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel))
    monkeypatch.setattr(asr_module, "_decode_audio_to_float32", lambda audio, sample_rate: np.zeros(16, dtype=np.float32))

    adapter = LocalWhisperAdapter(device="cuda")

    text = await adapter.transcribe(b"fake-webm", status_callback=lambda phase, message: statuses.append(phase))

    assert text == "hello cpu"
    assert calls == ["cuda", "cpu"]
    assert "cuda_fallback" in statuses


@pytest.mark.asyncio
async def test_local_whisper_consumes_segments_in_worker_thread(monkeypatch):
    from app.adapters import asr as asr_module

    main_thread_id = threading.get_ident()
    segment_thread_ids = []

    class Segment:
        def __init__(self, text):
            self.text = text

    class SegmentIterator:
        def __init__(self):
            self._segments = iter([Segment("hello"), Segment("world")])

        def __iter__(self):
            return self

        def __next__(self):
            segment_thread_ids.append(threading.get_ident())
            return next(self._segments)

    class FakeWhisperModel:
        def __init__(self, model_ref, device, compute_type):
            pass

        def transcribe(self, audio, language):
            return SegmentIterator(), object()

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel))
    monkeypatch.setattr(asr_module, "_decode_audio_to_float32", lambda audio, sample_rate: np.zeros(16, dtype=np.float32))

    adapter = LocalWhisperAdapter()

    text = await adapter.transcribe(b"fake-webm")

    assert text == "hello world"
    assert segment_thread_ids
    assert all(thread_id != main_thread_id for thread_id in segment_thread_ids)


@pytest.mark.asyncio
async def test_local_whisper_reports_transcription_stages(monkeypatch):
    from app.adapters import asr as asr_module

    statuses = []

    class Segment:
        text = "你好"

    class FakeWhisperModel:
        def __init__(self, model_ref, device, compute_type):
            pass

        def transcribe(self, audio, language):
            return iter([Segment()]), object()

    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=FakeWhisperModel))
    monkeypatch.setattr(asr_module, "_decode_audio_to_float32", lambda audio, sample_rate: np.zeros(16, dtype=np.float32))

    adapter = LocalWhisperAdapter()

    text = await adapter.transcribe(b"fake-webm", status_callback=lambda phase, message: statuses.append(phase))

    assert text == "你好"
    assert statuses == ["loading_model", "decoding_audio", "transcribing", "done"]
