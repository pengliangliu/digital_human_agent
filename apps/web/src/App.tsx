import { useState, useRef, useCallback, useEffect, Component, ReactNode } from 'react';
import AvatarScene from './avatar/AvatarScene';
import { BrowserAvatarRuntime, AvatarAction } from './avatar/avatarActions';
import { fetchAvatarModels, type AvatarModelInfo } from './avatar/avatarModels';
import { createSessionSocket, ClientEvent } from './api/wsClient';
import { useFaceTracking } from './vision/useFaceTracking';
import { useMicrophone } from './audio/useMicrophone';
import './App.css';

const SESSION_ID = 'avatar-' + Date.now().toString(36);

function formatAsrStatus(payload: Record<string, unknown>) {
  const message = payload.message;
  if (typeof message === 'string' && message.trim()) return message;

  const phase = payload.phase as string;
  const phaseText: Record<string, string> = {
    queued: '录音已进入识别队列',
    received: '后端已收到录音数据',
    decode_base64: '正在解析浏览器录音',
    transcribe: '正在调用 ASR 识别',
    preparing_audio: '正在准备上传给云端 ASR 的音频',
    cloud_transcribing: '正在等待云端 ASR 返回结果',
    loading_model: '正在加载本地 Whisper 模型',
    decoding_audio: '正在解码浏览器音频',
    transcribing: '正在运行 Whisper 推理',
    done: '录音识别完成',
  };
  if (phase && phaseText[phase]) return phaseText[phase];

  const status = payload.status as string;
  return (
    status === 'processing' ? '正在识别录音，可以继续输入文字' :
    status === 'cancelled' ? '上一段录音识别已取消' :
    status === 'error' ? '录音识别失败' : ''
  );
}

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) {
      return (
        <div style={{ color: '#f44', padding: 40, background: '#111', height: '100vh', fontFamily: 'monospace' }}>
          <h2>渲染错误</h2>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 13 }}>{this.state.error.message}</pre>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11, color: '#888' }}>{this.state.error.stack?.slice(0, 600)}</pre>
          <button onClick={() => this.setState({ error: null })} style={{ marginTop: 20, padding: '8px 16px' }}>
            重试
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  const [status, setStatus] = useState('connecting');
  const [error, setError] = useState('');
  const [replyText, setReplyText] = useState('');
  const [avatarActions, setAvatarActions] = useState<AvatarAction[]>([]);
  const [avatarRuntime, setAvatarRuntime] = useState<BrowserAvatarRuntime | null>(null);
  const [visionEnabled, setVisionEnabled] = useState(true);
  const [micEnabled, setMicEnabled] = useState(false);
  const [ttsEnabled, setTtsEnabled] = useState(false);
  const [deepseekApiKey, setDeepseekApiKey] = useState('');
  const [llmStatus, setLlmStatus] = useState('请填写 DeepSeek API Key');
  const [llmConnecting, setLlmConnecting] = useState(false);
  const [asrStatus, setAsrStatus] = useState('');
  const [events, setEvents] = useState<ClientEvent[]>([]);
  const [avatarModels, setAvatarModels] = useState<AvatarModelInfo[]>([]);
  const [selectedAvatarId, setSelectedAvatarId] = useState('');
  const [modelStatus, setModelStatus] = useState('使用内置占位数字人');
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const socketRef = useRef<ReturnType<typeof createSessionSocket> | null>(null);
  const avatarRuntimeRef = useRef<BrowserAvatarRuntime | null>(null);

  const send = useCallback((event: ClientEvent) => {
    socketRef.current?.send(event);
  }, []);

  const selectedAvatarModel = avatarModels.find((item) => item.id === selectedAvatarId) || null;

  const handleModelStatus = useCallback((message: string) => {
    setModelStatus(message);
  }, []);

  useEffect(() => {
    let cancelled = false;
    fetchAvatarModels()
      .then((items) => {
        if (cancelled) return;
        setAvatarModels(items);
        if (items.length > 0) {
          setSelectedAvatarId(items[0].id);
          setModelStatus(`发现 ${items.length} 个自建模型`);
        }
      })
      .catch((e) => {
        console.warn('[app] avatar model list failed:', e);
        if (!cancelled) setModelStatus('未发现可用自建模型，使用内置占位数字人');
      });

    return () => {
      cancelled = true;
    };
  }, []);

  // Connect WebSocket
  useEffect(() => {
    let timeoutId: number;
    let disposed = false;
    try {
      const socket = createSessionSocket(SESSION_ID);
      socketRef.current = socket;

      socket.onOpen(() => {
        if (disposed) return;
        setStatus('ready');
      });
      socket.onClose(() => {
        if (disposed) return;
        setStatus('error');
        setError('WebSocket 连接已断开，请确认后端服务仍在运行。');
      });
      socket.onError(() => {
        if (disposed) return;
        setStatus('error');
        setError('WebSocket 连接失败，请先启动后端：.\\Scripts\\python.exe run.py');
      });

      socket.onMessage((event) => {
        setEvents((prev) => [...prev.slice(-30), event]);

        try {
          switch (event.event) {
            case 'agent.reply': {
              const payload = event.payload as Record<string, unknown>;
              setReplyText((payload.reply_text as string) || '');
              const rawActions = payload.actions as Array<Record<string, unknown>> | undefined;
              if (rawActions?.length) {
                setAvatarActions(rawActions.map((a: Record<string, unknown>) => ({
                  type: a.type as string,
                  priority: (a.priority as AvatarAction['priority']) || 'normal',
                  duration_ms: a.duration_ms as number | undefined,
                  payload: a.payload ? a.payload as Record<string, unknown> : a,
                })));
              }
              break;
            }
            case 'avatar.action':
              setAvatarActions((prev) => [...prev.slice(-10), event.payload as unknown as AvatarAction]);
              break;
            case 'tts.audio': {
              const payload = event.payload as Record<string, unknown>;
              const audioB64 = payload.audio as string;
              if (audioB64) {
                try {
                  const binary = atob(audioB64);
                  const bytes = new Uint8Array(binary.length);
                  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
                  const blob = new Blob([bytes], { type: 'audio/mp3' });
                  const url = URL.createObjectURL(blob);
                  const audio = new Audio(url);
                  avatarRuntimeRef.current?.apply({ type: 'speech_start', priority: 'normal', payload: {} });
                  audio.onended = () => {
                    avatarRuntimeRef.current?.apply({ type: 'speech_end', priority: 'normal', payload: {} });
                    URL.revokeObjectURL(url);
                  };
                  audio.onerror = () => {
                    avatarRuntimeRef.current?.apply({ type: 'speech_end', priority: 'normal', payload: {} });
                    URL.revokeObjectURL(url);
                  };
                  audio.play().catch(() => {
                    avatarRuntimeRef.current?.apply({ type: 'speech_end', priority: 'normal', payload: {} });
                    URL.revokeObjectURL(url);
                  });
                } catch { /* audio play error */ }
              }
              break;
            }
            case 'llm.connection': {
              const payload = event.payload as Record<string, unknown>;
              setLlmConnecting(false);
              setLlmStatus((payload.message as string) || ((payload.ok as boolean) ? 'DeepSeek 连接成功' : 'DeepSeek 连接失败'));
              break;
            }
            case 'asr.status': {
              const payload = event.payload as Record<string, unknown>;
              setAsrStatus(formatAsrStatus(payload));
              break;
            }
            case 'asr.result': {
              setAsrStatus('');
              break;
            }
            case 'error': {
              const payload = event.payload as Record<string, unknown>;
              const message = (payload.message as string) || '';
              if (message.startsWith('ASR error:')) setAsrStatus(message);
              break;
            }
          }
        } catch (e) {
          console.warn('[app] event handler error:', e);
        }
      });

      timeoutId = window.setTimeout(() => {
        if (socket.readyState() !== WebSocket.OPEN) {
          setStatus('error');
          setError('WebSocket 连接超时，请确认后端 http://localhost:8000 已启动。');
        }
      }, 1500);

      return () => {
        disposed = true;
        clearTimeout(timeoutId);
        socket.close();
      };
    } catch (e: any) {
      setError('WebSocket 连接失败: ' + (e?.message || ''));
      setStatus('error');
    }
  }, []);

  // Camera — delayed to avoid blocking initial render
  useEffect(() => {
    if (!visionEnabled || status !== 'ready') return;
    const timer = setTimeout(() => {
      navigator.mediaDevices?.getUserMedia?.({ video: { width: 320, height: 240, facingMode: 'user' } })
        .then((stream) => {
          if (videoRef.current) videoRef.current.srcObject = stream;
        })
        .catch((e) => {
          console.warn('[app] camera access denied:', e.message);
          setVisionEnabled(false);
        });
    }, 500);
    return () => {
      clearTimeout(timer);
      if (videoRef.current?.srcObject) {
        (videoRef.current.srcObject as MediaStream).getTracks().forEach((t) => t.stop());
      }
    };
  }, [visionEnabled, status]);

  useFaceTracking(videoRef, send, visionEnabled && status === 'ready');
  const mic = useMicrophone(send, micEnabled);
  const micLabel =
    mic.status === 'starting' ? '申请麦克风' :
    mic.status === 'encoding' ? '处理录音' :
    micEnabled ? '停止录音' : '开始录音';
  const micStatus =
    mic.error ||
    asrStatus ||
    (mic.status === 'starting' ? '正在请求麦克风权限...' :
      mic.status === 'recording' ? '正在录音，点击停止后发送识别' :
        mic.status === 'encoding' ? '正在处理录音，请稍候...' : '');

  const handleMicToggle = async () => {
    if (micEnabled || mic.status === 'recording') {
      setAsrStatus('录音已发送，等待识别...');
      mic.stop();
      setMicEnabled(false);
    } else {
      try {
        await mic.start();
        setMicEnabled(true);
      } catch (e) {
        console.warn('[app] mic start failed:', e);
        setMicEnabled(false);
      }
    }
  };

  const handleTextSend = () => {
    const input = document.getElementById('text-input') as HTMLInputElement;
    if (!input?.value.trim()) return;
    send({ event: 'audio.transcript', payload: { text: input.value.trim() } });
    input.value = '';
  };

  const handleDeepSeekConnect = () => {
    const apiKey = deepseekApiKey.trim();
    if (!apiKey) {
      setLlmStatus('请输入 DeepSeek API Key');
      return;
    }
    setLlmConnecting(true);
    setLlmStatus('正在连接 DeepSeek...');
    send({ event: 'session.config', payload: { deepseek_api_key: apiKey, tts_enabled: ttsEnabled } });
  };

  const onAvatarReady = useCallback((runtime: BrowserAvatarRuntime) => {
    avatarRuntimeRef.current = runtime;
    setAvatarRuntime(runtime);
  }, []);

  useEffect(() => {
    if (status === 'ready') send({ event: 'session.config', payload: { tts_enabled: ttsEnabled } });
  }, [ttsEnabled, status, send]);

  if (error) {
    return (
      <div style={{ color: '#f66', padding: 40, background: '#111', height: '100vh', fontFamily: 'monospace' }}>
        <h2>连接失败</h2>
        <p>{error}</p>
        <p style={{ color: '#888', fontSize: 13 }}>请确保后端已启动：.\Scripts\python.exe run.py</p>
        <button onClick={() => { setError(''); setStatus('connecting'); window.location.reload(); }}
          style={{ marginTop: 16, padding: '8px 20px', cursor: 'pointer' }}>
          重试
        </button>
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <div className="app">
        <div className="scene-container">
          <AvatarScene
            onAvatarReady={onAvatarReady}
            actions={avatarActions}
            model={selectedAvatarModel}
            onModelStatus={handleModelStatus}
          />
          <video ref={videoRef} autoPlay muted playsInline className="camera-preview" />
        </div>

        <div className="overlay">
          <div className="status-bar">
            <span className={`status-dot ${status === 'ready' ? 'online' : status === 'error' ? 'error' : 'connecting'}`} />
            <span className="status-text">
              {status === 'ready' ? '数字人在线' : status === 'error' ? '连接失败' : '连接中...'}
            </span>
            {avatarRuntime && (
              <span className="status-info">
                {avatarRuntime.speaking ? '说话中' : ''} {avatarRuntime.expression !== 'neutral' ? avatarRuntime.expression : ''}
              </span>
            )}
          </div>

          {replyText && <div className="reply-bubble">{replyText}</div>}
          <div className="model-status">{modelStatus}</div>
          <div className={`llm-status ${llmStatus.includes('成功') ? 'success' : llmStatus.includes('失败') ? 'error' : ''}`}>
            {llmStatus}
          </div>
          {micStatus && (
            <div className={`mic-status ${mic.error ? 'error' : ''}`}>
              {micStatus}
            </div>
          )}
        </div>

        <div className="controls">
          <div className="llm-row">
            <input
              className="api-key-input"
              type="password"
              value={deepseekApiKey}
              onChange={(e) => setDeepseekApiKey(e.target.value)}
              placeholder="DeepSeek API Key"
              autoComplete="off"
            />
            <button className="ctrl-btn" onClick={handleDeepSeekConnect} disabled={llmConnecting || status !== 'ready'}>
              {llmConnecting ? '连接中' : '连接 DeepSeek'}
            </button>
          </div>
          <div className="control-row">
            <button
              className={`ctrl-btn ${micEnabled || mic.status === 'recording' ? 'active' : ''}`}
              onClick={handleMicToggle}
              disabled={status !== 'ready' || mic.status === 'starting' || mic.status === 'encoding'}
            >
              {micLabel}
            </button>
            <button className={`ctrl-btn ${ttsEnabled ? 'active' : ''}`} onClick={() => setTtsEnabled(!ttsEnabled)}>
              {ttsEnabled ? '语音开' : '语音关'}
            </button>
            <button className={`ctrl-btn ${visionEnabled ? 'active' : ''}`} onClick={() => setVisionEnabled(!visionEnabled)}>
              {visionEnabled ? '追踪开' : '追踪关'}
            </button>
            <select
              className="model-select"
              value={selectedAvatarId}
              onChange={(e) => setSelectedAvatarId(e.target.value)}
              title={modelStatus}
            >
              <option value="">内置占位数字人</option>
              {avatarModels.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.format})
                </option>
              ))}
            </select>
          </div>
          <div className="text-row">
            <input id="text-input" type="text" placeholder="输入文字与数字人对话..." onKeyDown={(e) => e.key === 'Enter' && handleTextSend()} />
            <button className="ctrl-btn send-btn" onClick={handleTextSend}>发送</button>
          </div>
        </div>

        <div className="debug-panel">
          <h4>事件日志 ({events.length}) {status}</h4>
          <div className="event-list">
            {events.slice(-5).reverse().map((e, i) => (
              <div key={i} className="event-item">
                <span className="event-type">{e.event}</span>
                <span className="event-data">{JSON.stringify(e.payload).slice(0, 80)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </ErrorBoundary>
  );
}
