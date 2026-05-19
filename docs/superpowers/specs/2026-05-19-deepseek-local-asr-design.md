# DeepSeek + Local ASR Integration Design

Date: 2026-05-19

## Summary

Add intelligent interaction by using DeepSeek as the cloud LLM and
faster-whisper as the local ASR engine. The browser continues to capture
microphone audio and send it through the existing WebSocket channel. The
backend converts audio to text locally, sends text to DeepSeek through an
OpenAI-compatible chat adapter, and returns the existing agent reply events.

## Assumptions

- The app may use the network for LLM calls to DeepSeek.
- Speech recognition should run locally where practical.
- The first production-oriented default should favor portability over maximum
  recognition accuracy.
- Chinese speech is a primary use case, so the ASR model must use a
  multilingual Whisper model, not an English-only model.
- DeepSeek API keys are configured locally by the app operator and are not
  bundled into the app.

## Goals

- Support DeepSeek via explicit configuration.
- Support local ASR with faster-whisper using CPU int8 inference.
- Default local ASR to the `small` multilingual model.
- Keep the current text interaction path intact: transcribed speech becomes the
  same `audio.transcript` style input handled by the agent.
- Keep model size and packaging choices compatible with a later portable app.

## Non-Goals

- Do not build the final desktop installer in this step.
- Do not add fully offline LLM inference in this step.
- Do not change avatar behavior beyond preserving existing action output.
- Do not add multi-provider ASR selection UI in this step.

## LLM Design

DeepSeek should be represented as a first-class provider in configuration, while
reusing the existing OpenAI-compatible adapter internally. DeepSeek's official
OpenAI-compatible base URL is `https://api.deepseek.com`.

Recommended defaults:

- `LLM_PROVIDER=deepseek`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_MODEL=deepseek-v4-flash`

`deepseek-v4-pro` can be configured later when quality matters more than speed
or cost. The older names `deepseek-chat` and `deepseek-reasoner` should not be
used as defaults because DeepSeek documents them as deprecated on 2026-07-24.

The existing `OpenAIAdapter` can be reused because DeepSeek accepts the same
chat-completions style messages and tool definitions.

## ASR Design

Use the existing `LocalWhisperAdapter` as the local ASR boundary and make it
production-ready for portable use:

- Load `faster_whisper.WhisperModel`.
- Default `model_size` to `small`.
- Default `device` to `cpu`.
- Default `compute_type` to `int8`.
- Allow `ASR_MODEL_SIZE` to choose `tiny`, `base`, `small`, or larger models.
- Allow `ASR_MODEL_PATH` to point at a local pre-downloaded model directory.

The app should start with `small` because it is a reasonable default for Chinese
short-form interaction while keeping the future portable package manageable.
`base` can be offered as a lighter option, and `medium` can be offered later for
better accuracy on stronger machines.

## Data Flow

1. Browser records microphone audio.
2. Frontend sends `audio.data` over the existing WebSocket session.
3. Backend decodes the audio payload.
4. Local ASR converts the audio bytes to text.
5. Backend publishes `asr.result` so the UI can show what was heard.
6. Backend sends the text through the existing agent text handler.
7. DeepSeek returns an `AgentReply`.
8. Backend publishes `agent.reply`, avatar actions, and optional TTS audio.

## Configuration

Add environment fields:

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL`
- `DEEPSEEK_MODEL`
- `ASR_MODEL_SIZE`
- `ASR_MODEL_PATH`
- `ASR_DEVICE`
- `ASR_COMPUTE_TYPE`

Update `configs/local.yaml` to document:

- `llm.provider: deepseek`
- `llm.deepseek.base_url`
- `llm.deepseek.model`
- `asr.provider: local`
- `asr.local.model_size`
- `asr.local.model_path`
- `asr.local.device`
- `asr.local.compute_type`

## Error Handling

- If `LLM_PROVIDER=deepseek` but no `DEEPSEEK_API_KEY` is configured, the backend
  should log a clear warning and use the mock adapter, matching the current
  OpenAI fallback behavior.
- If local ASR dependencies or model files are missing, the backend should
  publish an `error` event with an actionable message.
- If ASR returns blank text, do not call the LLM.
- If DeepSeek returns plain text rather than structured JSON, keep the current
  plain-text fallback behavior.

## Testing

Use focused tests before implementation:

- Settings load DeepSeek fields from environment variables.
- Orchestrator builder selects the DeepSeek/OpenAI-compatible adapter when
  `LLM_PROVIDER=deepseek`.
- Local ASR adapter passes configured model size, path, device, and compute type
  into `WhisperModel`.
- Blank ASR output does not call the LLM.
- LLM parsing still accepts plain text and tool calls.

## Portable App Direction

The later portable app should not require a full developer setup. The preferred
packaging path is:

- Bundle the built web frontend.
- Bundle the Python backend runtime.
- Keep DeepSeek API key in local user configuration.
- Provide either a pre-downloaded `faster-whisper-small` model directory or a
  first-run model download step.
- Keep `ASR_MODEL_PATH` configurable so the app can run without relying on the
  Hugging Face cache layout.

This keeps the first install lighter while preserving an offline ASR option.
Fully offline interaction would require replacing DeepSeek with a local LLM and
is outside this design.

## References

- DeepSeek API docs: https://api-docs.deepseek.com/
- OpenAI Whisper model table: https://github.com/openai/whisper/blob/main/README.md
- faster-whisper docs: https://github.com/SYSTRAN/faster-whisper/blob/master/README.md
