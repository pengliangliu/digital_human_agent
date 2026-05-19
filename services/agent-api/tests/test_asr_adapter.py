import sys
from types import SimpleNamespace

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
