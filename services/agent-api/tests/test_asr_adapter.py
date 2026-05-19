import sys
from types import SimpleNamespace

import numpy as np

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
