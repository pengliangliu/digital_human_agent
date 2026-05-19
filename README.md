# 交互式数字人 Agent 系统

面向通用场景的交互式数字人系统。基于 FastAPI + Three.js，支持实时语音对话、摄像头人脸追踪、3D 数字人动作驱动，并可按需扩展业务工具。

## 快速开始

### 环境要求

| 依赖 | 版本要求 |
|------|----------|
| Python | >= 3.10 |
| Node.js | >= 18 |
| 浏览器 | Chrome / Edge（需摄像头和麦克风权限） |

### 安装

```bash
# 1. Python 虚拟环境
cd dagital_human_agent
python -m venv .
.\Scripts\pip.exe install -e .

# 2. 前端依赖
cd apps/web
npm install
```

### 运行

```bash
# 终端 1：启动后端
.\Scripts\python.exe run.py
# → http://localhost:8000

# 终端 2：启动前端
cd apps/web
npm run dev
# → http://localhost:5173
```

打开 `http://localhost:5173`，看到数字人场景后即可交互。

### Windows 常见问题

- 如果 PowerShell 提示无法加载 `npm.ps1`，请改用 `npm.cmd run dev` 或 `npm.cmd run build`。
- 如果 `.\\Scripts\\python.exe` 提示找不到 WindowsApps 里的 Python 3.10，说明虚拟环境引用的解释器已经失效。安装 Python 3.10+ 后在项目根目录重建虚拟环境，再执行 `.\Scripts\pip.exe install -e .[dev]`。

## 项目结构

```
dagital_human_agent/
├── run.py                          # 服务启动入口
├── pyproject.toml                  # Python 依赖
├── .env.example                    # 环境变量模板
├── configs/
│   ├── local.yaml                  # 主配置（LLM / ASR / TTS 切换）
│   └── avatar_actions.yaml         # 数字人动作白名单
├── services/agent-api/
│   └── app/
│       ├── main.py                 # FastAPI WebSocket 服务
│       ├── schemas.py              # 数据模型（ClientEvent / AvatarAction 等）
│       ├── adapters/
│       │   ├── llm.py              # LLM 适配器（OpenAI / Ollama / Anthropic / Mock）
│       │   ├── asr.py              # 语音识别适配器
│       │   ├── tts.py              # 语音合成适配器（Edge TTS 免费）
│       │   ├── vad.py              # 语音活动检测
│       │   └── avatar_action.py    # 数字人动作适配器（Null / HTTP）
│       ├── agent/
│       │   ├── orchestrator.py     # 核心编排：对话→LLM→TTS→动作
│       │   ├── behavior_planner.py # 行为规划：视觉追踪→注视，回复→表情动作
│       │   ├── prompts.py          # 数字人角色提示词
│       │   ├── tools.py            # 工具：可选扩展能力 / 用户画像
│       │   └── memory.py           # SQLite 会话记忆 + 用户偏好
│       └── vision/
│           └── tracking_state.py   # 视觉状态平滑滤波
├── apps/web/
│   └── src/
│       ├── App.tsx                 # 主界面：3D 场景 + 控制栏 + 事件日志
│       ├── api/wsClient.ts         # WebSocket 客户端
│       ├── avatar/
│       │   ├── AvatarScene.tsx     # Three.js 数字人场景（头部/身体/表情/口型）
│       │   └── avatarActions.ts    # 浏览器端动作执行器
│       ├── vision/
│       │   └── useFaceTracking.ts  # 人脸追踪 Hook
│       └── audio/
│           └── useMicrophone.ts    # 麦克风采集 Hook
└── models/avatars/                 # 数字人模型目录（预留 CHGA / .ply）
```

## 配置

### 环境变量（`.env`）

```env
# LLM — 不设置则使用 Mock 适配器回显
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-your-key
OPENAI_MODEL=gpt-4o

# 本地 LLM（预留）
# LLM_PROVIDER=ollama
# OLLAMA_HOST=http://localhost:11434
# OLLAMA_MODEL=qwen2.5:7b
```

### 切换适配器（`configs/local.yaml`）

| 模块 | 可选值 | 说明 |
|------|--------|------|
| `llm.provider` | `openai` / `ollama` / `anthropic` | 云端或本地大模型 |
| `asr.provider` | `cloud` / `local` | 语音识别 |
| `tts.provider` | `edge` / `openai` / `local` | Edge TTS 免费可用 |
| `avatar.adapter` | `null` / `http` | null 打印日志，http 对接 CHGA runtime |

## WebSocket 协议

连接：`ws://localhost:8000/ws/session/{session_id}`

### 客户端 → 服务端

| 事件 | 说明 |
|------|------|
| `session.init` | 初始化会话，返回欢迎语 |
| `vision.state` | 用户位置/朝向/置信度 |
| `audio.data` | base64 音频数据 |
| `audio.transcript` | 文字文本（跳过 ASR 直发） |
| `session.config` | 配置项（TTS 开关等） |

### 服务端 → 客户端

| 事件 | 说明 |
|------|------|
| `agent.reply` | LLM 回复（文本 + 情绪 + 动作 + 工具调用） |
| `avatar.action` | 数字人动作指令 |
| `tts.audio` | base64 合成语音 |
| `asr.result` | 语音识别结果 |
| `tool.result` | 工具调用结果 |

### AvatarAction 类型

`look_at` | `head_pose` | `gesture` | `expression` | `speech_start` | `speech_end` | `lip_sync` | `pose` | `bone_pose` | `morph_target` | `viseme` | `animation_clip` | `motion_sequence` | `try_on` | `load_avatar`

HTTP Avatar Runtime 接口使用统一动作包：

```json
{
  "session_id": "session-a",
  "type": "animation_clip",
  "priority": "normal",
  "duration_ms": 1200,
  "payload": {
    "name": "wave",
    "loop": false,
    "fade_ms": 150
  }
}
```

## API 文档

启动后端后访问 `http://localhost:8000/docs` 查看 Swagger 文档。

## 后续接入

- **CHGA / 真实数字人 Runtime**：将 `avatar.adapter` 切换为 `http`，实现 `/avatar/action` 后把 `bone_pose`、`morph_target`、`viseme`、`animation_clip` 映射到你的骨骼、表情、口型和动画系统
- **本地 LLM**：安装 Ollama，切换 `llm.provider` 为 `ollama`
- **本地 ASR**：安装 `faster-whisper`，切换 `asr.provider` 为 `local`
- **口型同步**：实现 `lip_sync` / `viseme` 动作，接入 Audio2Face 或自研 viseme 模型
