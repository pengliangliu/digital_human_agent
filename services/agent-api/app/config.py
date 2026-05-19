from pathlib import Path
from typing import Any

import yaml
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"
    llm_provider: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"
    deepseek_api_key: str = ""
    deepseek_base_url: str = ""
    deepseek_model: str = ""
    anthropic_api_key: str = ""
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    asr_provider: str = ""
    asr_model_size: str = ""
    asr_model_path: str = ""
    asr_device: str = ""
    asr_compute_type: str = ""
    asr_log_file: str = ""
    tts_provider: str = "edge"
    avatar_api_url: str = "http://localhost:9000"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def load_yaml(path: str) -> dict[str, Any]:
    full = _PROJECT_ROOT / path
    if full.exists():
        return yaml.safe_load(full.read_text(encoding="utf-8")) or {}
    return {}


def load_config() -> dict[str, Any]:
    cfg = load_yaml("configs/local.yaml")
    cfg.setdefault("server", {})
    cfg.setdefault("llm", {})
    cfg.setdefault("asr", {})
    cfg.setdefault("tts", {})
    cfg.setdefault("vad", {})
    cfg.setdefault("avatar", {})
    cfg.setdefault("vision", {})
    cfg.setdefault("agent", {})
    cfg.setdefault("memory", {})
    return cfg


def project_root() -> Path:
    return _PROJECT_ROOT
