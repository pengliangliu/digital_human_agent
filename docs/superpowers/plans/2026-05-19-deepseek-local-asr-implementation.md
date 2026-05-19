# DeepSeek 本地 ASR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 接入 DeepSeek 云端大模型，并让本地 faster-whisper ASR 默认使用 CUDA int8 推理。

**Architecture:** 后端保留现有 WebSocket 和 Agent 编排链路，只把 provider 构建逻辑拆成可测试 helper。DeepSeek 复用 OpenAI-compatible adapter；本地 ASR 通过 `LocalWhisperAdapter` 接收模型、路径、设备和 compute type 配置。

**Tech Stack:** Python 3.10+, FastAPI, pydantic-settings, openai SDK, faster-whisper, pytest。

---

## File Structure

- Modify `services/agent-api/app/config.py`
  - Add DeepSeek settings and local ASR settings.
  - Let provider defaults fall back through `configs/local.yaml`.
- Modify `services/agent-api/app/main.py`
  - Add `_build_llm(settings, llm_cfg)` and `_build_asr(settings, cfg)`.
  - Keep `_build_orchestrator()` as the integration point.
- Modify `services/agent-api/app/adapters/asr.py`
  - Extend `LocalWhisperAdapter` with `model_path`, `device`, and `compute_type`.
- Create `services/agent-api/tests/test_config.py`
  - Verify new environment-backed settings.
- Create `services/agent-api/tests/test_orchestrator_builders.py`
  - Verify DeepSeek and local ASR builder selection.
- Create `services/agent-api/tests/test_asr_adapter.py`
  - Verify `LocalWhisperAdapter` passes CUDA/model configuration to `WhisperModel`.
- Modify `.env.example`
  - Document DeepSeek and local ASR environment variables.
- Modify `configs/local.yaml`
  - Document `llm.deepseek` and expanded `asr.local` fields.

Do not stage or commit unrelated existing workspace changes. Several files are already dirty before this implementation; use `git diff -- <path>` before and after editing any dirty file.

---

### Task 0: Verify Python Runtime

**Files:**
- Read: `pyproject.toml`
- No source changes.

- [ ] **Step 1: Confirm Python 3.10 runtime**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe --version
```

Expected:

```text
Python 3.10.20
```

- [ ] **Step 2: Install dev dependencies if pytest is missing**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pip install -e .[dev]
```

Expected: pip completes without errors. If network or permission blocks the install, stop and report the blocker.

- [ ] **Step 3: Run backend baseline tests**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pytest services\agent-api\tests -q
```

Expected: tests either pass or reveal pre-existing failures. If there are failures before any implementation change, record them and continue only if they do not block the DeepSeek/ASR tests.

---

### Task 1: Settings For DeepSeek And Local ASR

**Files:**
- Modify: `services/agent-api/app/config.py`
- Create: `services/agent-api/tests/test_config.py`

- [ ] **Step 1: Write failing settings tests**

Add `services/agent-api/tests/test_config.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pytest services\agent-api\tests\test_config.py -q
```

Expected: FAIL because `Settings` does not define the new DeepSeek and ASR fields.

- [ ] **Step 3: Implement minimal settings fields**

In `services/agent-api/app/config.py`, update `Settings`:

```python
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
    tts_provider: str = "edge"
    avatar_api_url: str = "http://localhost:9000"
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pytest services\agent-api\tests\test_config.py -q
```

Expected: PASS.

---

### Task 2: DeepSeek LLM Builder

**Files:**
- Modify: `services/agent-api/app/main.py`
- Create/Modify: `services/agent-api/tests/test_orchestrator_builders.py`

- [ ] **Step 1: Write failing DeepSeek builder tests**

Create `services/agent-api/tests/test_orchestrator_builders.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pytest services\agent-api\tests\test_orchestrator_builders.py -q
```

Expected: FAIL because `main._build_llm` does not exist.

- [ ] **Step 3: Implement `_build_llm` and use it**

In `services/agent-api/app/main.py`, import adapter classes at module level and add:

```python
def _build_llm(settings: Settings, llm_cfg: dict):
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
```

Then replace the inline LLM block in `_build_orchestrator()` with:

```python
llm = _build_llm(settings, llm_cfg)
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pytest services\agent-api\tests\test_orchestrator_builders.py -q
```

Expected: PASS for the DeepSeek builder tests.

---

### Task 3: Local Whisper Adapter Configuration

**Files:**
- Modify: `services/agent-api/app/adapters/asr.py`
- Create: `services/agent-api/tests/test_asr_adapter.py`

- [ ] **Step 1: Write failing LocalWhisperAdapter test**

Add `services/agent-api/tests/test_asr_adapter.py`:

```python
from types import SimpleNamespace

from app.adapters.asr import LocalWhisperAdapter


def test_local_whisper_loads_model_path_with_cuda_int8(monkeypatch):
    captured = {}

    class FakeWhisperModel:
        def __init__(self, model_ref, device, compute_type):
            captured["model_ref"] = model_ref
            captured["device"] = device
            captured["compute_type"] = compute_type

    monkeypatch.setitem(
        __import__("sys").modules,
        "faster_whisper",
        SimpleNamespace(WhisperModel=FakeWhisperModel),
    )

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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pytest services\agent-api\tests\test_asr_adapter.py -q
```

Expected: FAIL because `LocalWhisperAdapter.__init__` does not accept `model_path`, `device`, or `compute_type`.

- [ ] **Step 3: Implement minimal adapter configuration**

In `services/agent-api/app/adapters/asr.py`, update `LocalWhisperAdapter`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pytest services\agent-api\tests\test_asr_adapter.py -q
```

Expected: PASS.

---

### Task 4: Local ASR Builder Selection

**Files:**
- Modify: `services/agent-api/app/main.py`
- Modify: `services/agent-api/tests/test_orchestrator_builders.py`

- [ ] **Step 1: Write failing local ASR builder test**

Append to `services/agent-api/tests/test_orchestrator_builders.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pytest services\agent-api\tests\test_orchestrator_builders.py -q
```

Expected: FAIL because `main._build_asr` does not exist.

- [ ] **Step 3: Implement `_build_asr` and use it**

In `services/agent-api/app/main.py`, add:

```python
def _build_asr(settings: Settings, cfg: dict):
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
```

Then replace the inline ASR block in `_build_orchestrator()` with:

```python
asr = _build_asr(settings, cfg)
```

- [ ] **Step 4: Run builder tests to verify they pass**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pytest services\agent-api\tests\test_orchestrator_builders.py -q
```

Expected: PASS.

---

### Task 5: Configuration Documentation

**Files:**
- Modify: `.env.example`
- Modify: `configs/local.yaml`

- [ ] **Step 1: Update `.env.example`**

Add DeepSeek and local ASR fields:

```env
# DeepSeek (OpenAI-compatible)
DEEPSEEK_API_KEY=sk-xxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

# Local ASR Configuration
ASR_MODEL_SIZE=small
ASR_MODEL_PATH=
ASR_DEVICE=cuda
ASR_COMPUTE_TYPE=int8
```

- [ ] **Step 2: Update `configs/local.yaml`**

Under `llm`, add:

```yaml
  deepseek:
    base_url: "https://api.deepseek.com"
    model: "deepseek-v4-flash"
    temperature: 0.7
    max_tokens: 1024
```

Under `asr.local`, ensure:

```yaml
  local:
    engine: "faster-whisper"
    model_size: "small"
    model_path: ""
    device: "cuda"
    compute_type: "int8"
```

- [ ] **Step 3: Verify documentation values**

Run:

```powershell
rg -n "deepseek|ASR_MODEL_SIZE|ASR_DEVICE|compute_type" .env.example configs\local.yaml
```

Expected: the new DeepSeek and ASR keys appear in both files.

---

### Task 6: Final Verification

**Files:**
- Verify all changed implementation and test files.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pytest services\agent-api\tests\test_config.py services\agent-api\tests\test_orchestrator_builders.py services\agent-api\tests\test_asr_adapter.py -q
```

Expected: PASS.

- [ ] **Step 2: Run full backend tests**

Run:

```powershell
C:\ProgramData\Anaconda3\envs\fashion_env\python.exe -m pytest services\agent-api\tests -q
```

Expected: PASS, or only pre-existing failures already recorded in Task 0.

- [ ] **Step 3: Inspect final diff**

Run:

```powershell
git diff -- services\agent-api\app\config.py services\agent-api\app\main.py services\agent-api\app\adapters\asr.py services\agent-api\tests\test_config.py services\agent-api\tests\test_orchestrator_builders.py services\agent-api\tests\test_asr_adapter.py .env.example configs\local.yaml
```

Expected: diff only contains DeepSeek/local ASR integration changes.

- [ ] **Step 4: Do not auto-commit dirty user files**

Because several relevant files were already dirty before implementation, do not create an implementation commit unless the staged diff can be proven to exclude unrelated user edits.
