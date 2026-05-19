import sys
from pathlib import Path

# Add services/agent-api to Python path
_svc = Path(__file__).resolve().parent / "services" / "agent-api"
sys.path.insert(0, str(_svc))

from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from app.adapters.asr import WhisperCloudAdapter, LocalWhisperAdapter, NullASRAdapter
from app.adapters.avatar_action import NullAvatarActionAdapter, HttpAvatarActionAdapter
from app.adapters.llm import OpenAIAdapter, OllamaAdapter, AnthropicAdapter, MockLLMAdapter
from app.adapters.tts import EdgeTTSAdapter, NullTTSAdapter
from app.avatar_models import discover_avatar_models
from app.config import Settings, load_config, project_root
from app.runtime.event_bus import SessionEventBus
from app.schemas import ClientEvent

load_dotenv()


def _build_llm(settings: Settings, llm_cfg: dict[str, Any]):
    llm_provider = settings.llm_provider or llm_cfg.get("provider", "openai")
    if llm_provider == "ollama":
        ollama = llm_cfg.get("ollama", {})
        return OllamaAdapter(
            host=settings.ollama_host or ollama.get("host", "http://localhost:11434"),
            model=settings.ollama_model or ollama.get("model", "qwen2.5:7b"),
            temperature=ollama.get("temperature", 0.7),
            max_tokens=ollama.get("max_tokens", 1024),
        )
    if llm_provider == "anthropic":
        anthro = llm_cfg.get("anthropic", {})
        return AnthropicAdapter(
            api_key=settings.anthropic_api_key,
            model=anthro.get("model", "claude-sonnet-4-6"),
            temperature=anthro.get("temperature", 0.7),
            max_tokens=anthro.get("max_tokens", 1024),
        )
    if llm_provider == "deepseek":
        deepseek = llm_cfg.get("deepseek", {})
        api_key = settings.deepseek_api_key
        if not api_key:
            print("[agent-api] WARNING: DEEPSEEK_API_KEY not set, using MockLLMAdapter")
            return MockLLMAdapter()
        return OpenAIAdapter(
            api_key=api_key,
            base_url=settings.deepseek_base_url or deepseek.get("base_url", "https://api.deepseek.com"),
            model=settings.deepseek_model or deepseek.get("model", "deepseek-v4-flash"),
            temperature=deepseek.get("temperature", 0.7),
            max_tokens=deepseek.get("max_tokens", 1024),
        )

    openai_cfg = llm_cfg.get("openai", {})
    api_key = settings.openai_api_key
    if not api_key:
        print("[agent-api] WARNING: OPENAI_API_KEY not set, using MockLLMAdapter")
        return MockLLMAdapter()
    return OpenAIAdapter(
        api_key=api_key,
        base_url=settings.openai_base_url or openai_cfg.get("base_url", "https://api.openai.com/v1"),
        model=settings.openai_model or openai_cfg.get("model", "gpt-4o"),
        temperature=openai_cfg.get("temperature", 0.7),
        max_tokens=openai_cfg.get("max_tokens", 1024),
    )


def _build_asr(settings: Settings, cfg: dict[str, Any]):
    asr_cfg = cfg.get("asr", {})
    asr_provider = settings.asr_provider or asr_cfg.get("provider", "cloud")
    if asr_provider == "local":
        local = asr_cfg.get("local", {})
        return LocalWhisperAdapter(
            model_size=settings.asr_model_size or local.get("model_size", "small"),
            model_path=settings.asr_model_path or local.get("model_path", ""),
            device=settings.asr_device or local.get("device", "cuda"),
            compute_type=settings.asr_compute_type or local.get("compute_type", "int8"),
        )
    if asr_provider == "cloud" and settings.openai_api_key:
        return WhisperCloudAdapter(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
    return NullASRAdapter()


def _build_orchestrator():
    from app.agent.orchestrator import AgentOrchestrator
    from app.agent.memory import SessionMemory

    settings = Settings()
    cfg = load_config()
    llm_cfg = cfg.get("llm", {})
    tts_cfg = cfg.get("tts", {})
    avatar_cfg = cfg.get("avatar", {})
    memory_cfg = cfg.get("memory", {})

    # LLM
    llm = _build_llm(settings, llm_cfg)

    # ASR
    asr = _build_asr(settings, cfg)

    # TTS
    tts_provider = settings.tts_provider or tts_cfg.get("provider", "edge")
    if tts_provider == "edge":
        tts = EdgeTTSAdapter(voice=tts_cfg.get("edge", {}).get("voice", "zh-CN-XiaoxiaoNeural"))
    else:
        tts = NullTTSAdapter()

    # Avatar
    avatar_adapter = avatar_cfg.get("adapter", "null")
    if avatar_adapter == "http":
        avatar = HttpAvatarActionAdapter(
            base_url=settings.avatar_api_url or avatar_cfg.get("http", {}).get("base_url", "http://localhost:9000")
        )
    else:
        avatar = NullAvatarActionAdapter()

    # Memory
    memory = SessionMemory(db_path=memory_cfg.get("db_path", "data/memory.db"))

    return AgentOrchestrator(
        event_bus=event_bus,
        llm=llm,
        asr=asr,
        tts=tts,
        avatar=avatar,
        memory=memory,
    )


event_bus = SessionEventBus()
agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global agent
    agent = _build_orchestrator()
    print(f"[agent-api] LLM={agent._llm.__class__.__name__} ASR={agent._asr.__class__.__name__} TTS={agent._tts.__class__.__name__}")
    yield
    await agent.close()


app = FastAPI(title="Digital Human Agent API", version="0.1.0", lifespan=lifespan)
app.mount("/models", StaticFiles(directory=project_root() / "models", check_dir=False), name="models")


@app.get("/health")
async def health():
    return {"status": "ok", "sessions": event_bus.active_sessions()}


@app.get("/api/avatars")
async def list_avatar_models():
    return {
        "items": discover_avatar_models(project_root() / "models" / "avatars"),
        "supported_formats": ["glb", "gltf", "obj", "fbx"],
    }


@app.websocket("/ws/session/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str) -> None:
    global agent
    await websocket.accept()
    await event_bus.attach(session_id, websocket)

    try:
        while True:
            payload = await websocket.receive_json()
            event = ClientEvent.model_validate(payload)
            if agent:
                await agent.handle_event(session_id=session_id, event=event)
    except WebSocketDisconnect:
        await event_bus.detach(session_id, websocket)
    except Exception as e:
        print(f"[ws:{session_id}] error: {e}")
        await event_bus.detach(session_id, websocket)


if __name__ == "__main__":
    settings = Settings()
    uvicorn.run(app, host=settings.host, port=settings.port, log_level=settings.log_level)
