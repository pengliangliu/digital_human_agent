from app import main
from app.config import Settings


class FakeOpenAIAdapter:
    def __init__(self, api_key, base_url, model, temperature=0.7, max_tokens=1024):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens


def test_build_llm_uses_deepseek_openai_compatible_adapter(monkeypatch):
    monkeypatch.setattr(main, "OpenAIAdapter", FakeOpenAIAdapter)
    settings = Settings(
        _env_file=None,
        llm_provider="deepseek",
        deepseek_api_key="sk-deepseek",
    )

    llm = main._build_llm(
        settings,
        {
            "deepseek": {
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "temperature": 0.2,
                "max_tokens": 512,
            }
        },
    )

    assert llm.api_key == "sk-deepseek"
    assert llm.base_url == "https://api.deepseek.com"
    assert llm.model == "deepseek-v4-flash"
    assert llm.temperature == 0.2
    assert llm.max_tokens == 512


def test_build_llm_uses_mock_when_deepseek_key_missing():
    settings = Settings(_env_file=None, llm_provider="deepseek")

    llm = main._build_llm(settings, {"deepseek": {}})

    assert isinstance(llm, main.MockLLMAdapter)


class FakeLocalWhisperAdapter:
    def __init__(self, model_size, model_path, device, compute_type):
        self.model_size = model_size
        self.model_path = model_path
        self.device = device
        self.compute_type = compute_type


def test_build_asr_uses_local_whisper_cuda_config(monkeypatch):
    monkeypatch.setattr(main, "LocalWhisperAdapter", FakeLocalWhisperAdapter)
    settings = Settings(_env_file=None, asr_provider="local")

    asr = main._build_asr(
        settings,
        {
            "asr": {
                "local": {
                    "model_size": "small",
                    "model_path": "D:/models/faster-whisper-small",
                    "device": "cuda",
                    "compute_type": "int8",
                }
            }
        },
    )

    assert asr.model_size == "small"
    assert asr.model_path == "D:/models/faster-whisper-small"
    assert asr.device == "cuda"
    assert asr.compute_type == "int8"


def test_build_deepseek_session_llm_factory_uses_runtime_api_key(monkeypatch):
    monkeypatch.setattr(main, "OpenAIAdapter", FakeOpenAIAdapter)
    settings = Settings(_env_file=None, deepseek_base_url="https://custom.deepseek.test")

    factory = main._build_deepseek_session_llm_factory(
        settings,
        {
            "deepseek": {
                "base_url": "https://api.deepseek.com",
                "model": "deepseek-v4-flash",
                "temperature": 0.1,
                "max_tokens": 128,
            }
        },
    )
    llm = factory("sk-from-frontend")

    assert llm.api_key == "sk-from-frontend"
    assert llm.base_url == "https://custom.deepseek.test"
    assert llm.model == "deepseek-v4-flash"
    assert llm.temperature == 0.1
    assert llm.max_tokens == 128
