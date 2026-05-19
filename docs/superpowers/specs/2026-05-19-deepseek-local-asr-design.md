# DeepSeek + 本地 ASR 集成设计

日期：2026-05-19

## 概要

本方案为数字人 Agent 增加智能交互能力：使用 DeepSeek 作为云端大模型，
使用 faster-whisper 作为本地语音识别引擎。浏览器继续采集麦克风音频，并
通过现有 WebSocket 通道发送给后端。后端在本地把音频转换成文字，再通过
OpenAI 兼容的聊天适配器发送给 DeepSeek，最后沿用现有事件格式返回 Agent
回复。

## 假设

- 应用可以联网调用 DeepSeek。
- 语音识别尽量在本地运行。
- 第一版面向可移植应用的默认方案，应优先考虑体积和稳定性，而不是追求最高
  识别准确率。
- 中文语音是主要使用场景，所以 ASR 必须使用多语言 Whisper 模型，不能使用
  English-only 模型。
- DeepSeek API Key 由本机用户配置，不能打包进应用。

## 目标

- 通过显式配置支持 DeepSeek。
- 通过 faster-whisper 支持本地 ASR，并默认使用 CPU int8 推理。
- 本地 ASR 默认使用 `small` 多语言模型。
- 保持当前文本交互链路不变：语音转写后的文字进入同一套 Agent 文本处理逻辑。
- 为后续可移植 app 保留模型体积和模型路径配置能力。

## 非目标

- 本步骤不制作最终桌面安装包。
- 本步骤不增加完全离线的大模型推理。
- 本步骤不调整数字人动作逻辑，只保持已有动作输出兼容。
- 本步骤不增加多 ASR 服务切换 UI。

## LLM 设计

DeepSeek 在配置中作为一个独立 provider 暴露，但内部复用现有
OpenAI-compatible adapter。DeepSeek 官方 OpenAI 兼容接口的 base URL 是
`https://api.deepseek.com`。

推荐默认配置：

- `LLM_PROVIDER=deepseek`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_MODEL=deepseek-v4-flash`

如果后续更看重效果而不是速度或成本，可以改成 `deepseek-v4-pro`。旧模型名
`deepseek-chat` 和 `deepseek-reasoner` 不应作为默认值，因为 DeepSeek 文档标
注它们将在 2026-07-24 废弃。

现有 `OpenAIAdapter` 可以复用，因为 DeepSeek 接受同类 chat-completions
消息和工具定义格式。

## ASR 设计

沿用现有 `LocalWhisperAdapter` 作为本地 ASR 边界，并补齐可移植应用需要的
配置能力：

- 加载 `faster_whisper.WhisperModel`。
- 默认 `model_size` 为 `small`。
- 默认 `device` 为 `cpu`。
- 默认 `compute_type` 为 `int8`。
- 允许通过 `ASR_MODEL_SIZE` 选择 `tiny`、`base`、`small` 或更大的模型。
- 允许通过 `ASR_MODEL_PATH` 指向本地预下载模型目录。

应用默认从 `small` 开始，因为它对中文短句交互的可用性和体积比较均衡。
`base` 可作为更轻量选项，`medium` 后续可作为高配置机器上的更高准确率选项。

## 数据流

1. 浏览器录制麦克风音频。
2. 前端通过现有 WebSocket session 发送 `audio.data`。
3. 后端解码音频 payload。
4. 本地 ASR 将音频转换成文字。
5. 后端发布 `asr.result`，方便 UI 展示识别结果。
6. 后端把识别文字交给现有 Agent 文本处理逻辑。
7. DeepSeek 返回 `AgentReply`。
8. 后端发布 `agent.reply`、数字人动作事件，以及可选的 TTS 音频。

## 配置

新增环境变量：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`
- `ASR_MODEL_SIZE`
- `ASR_MODEL_PATH`
- `ASR_DEVICE`
- `ASR_COMPUTE_TYPE`

更新 `configs/local.yaml`，记录以下配置：

- `llm.provider: deepseek`
- `llm.deepseek.base_url`
- `llm.deepseek.model`
- `asr.provider: local`
- `asr.local.model_size`
- `asr.local.model_path`
- `asr.local.device`
- `asr.local.compute_type`

## 错误处理

- 如果 `LLM_PROVIDER=deepseek` 但未配置 `DEEPSEEK_API_KEY`，后端应打印清晰警告，
  并使用 mock adapter，行为与当前 OpenAI 缺少 API Key 时一致。
- 如果本地 ASR 依赖或模型文件缺失，后端应发布带有可操作提示的 `error` 事件。
- 如果 ASR 返回空文本，不调用 LLM。
- 如果 DeepSeek 返回普通文本而不是结构化 JSON，继续使用当前纯文本 fallback
  行为。

## 测试

实现前先补充聚焦测试：

- Settings 可以从环境变量读取 DeepSeek 字段。
- `LLM_PROVIDER=deepseek` 时，orchestrator builder 会选择 DeepSeek/OpenAI 兼容
  适配器。
- Local ASR adapter 会把配置的 model size、model path、device 和 compute type
  传给 `WhisperModel`。
- ASR 输出空文本时不会调用 LLM。
- LLM 解析逻辑仍然支持纯文本回复和 tool calls。

## 可移植 App 方向

后续可移植 app 不应要求用户安装完整开发环境。推荐打包方向：

- 打包构建后的 Web 前端。
- 打包 Python 后端运行时。
- DeepSeek API Key 保存在用户本机配置中。
- 提供预下载的 `faster-whisper-small` 模型目录，或提供首次启动下载模型的步骤。
- 保持 `ASR_MODEL_PATH` 可配置，让应用不依赖 Hugging Face 默认缓存目录结构。

这样可以让第一版安装包更轻，同时保留离线语音识别能力。完全离线智能交互需
要把 DeepSeek 换成本地 LLM，不属于本设计范围。

## 参考

- DeepSeek API docs: https://api-docs.deepseek.com/
- OpenAI Whisper model table: https://github.com/openai/whisper/blob/main/README.md
- faster-whisper docs: https://github.com/SYSTRAN/faster-whisper/blob/master/README.md
