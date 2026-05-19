from app.config import Settings


def test_settings_load_deepseek_fields_from_environment(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")

    settings = Settings(_env_file=None)

    assert settings.llm_provider == "deepseek"
    assert settings.deepseek_api_key == "sk-test"
    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.deepseek_model == "deepseek-v4-flash"


def test_settings_load_local_asr_fields_from_environment(monkeypatch):
    monkeypatch.setenv("ASR_PROVIDER", "local")
    monkeypatch.setenv("ASR_MODEL_SIZE", "small")
    monkeypatch.setenv("ASR_MODEL_PATH", "D:/models/faster-whisper-small")
    monkeypatch.setenv("ASR_DEVICE", "cuda")
    monkeypatch.setenv("ASR_COMPUTE_TYPE", "int8")

    settings = Settings(_env_file=None)

    assert settings.asr_provider == "local"
    assert settings.asr_model_size == "small"
    assert settings.asr_model_path == "D:/models/faster-whisper-small"
    assert settings.asr_device == "cuda"
    assert settings.asr_compute_type == "int8"
