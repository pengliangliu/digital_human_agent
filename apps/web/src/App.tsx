import { useState, useRef, useCallback, useEffect, Component, ReactNode } from 'react';
import AvatarScene from './avatar/AvatarScene';
import { BrowserAvatarRuntime, AvatarAction } from './avatar/avatarActions';
import { fetchAvatarModels, type AvatarModelInfo } from './avatar/avatarModels';
import { createSessionSocket, ClientEvent } from './api/wsClient';
import { useFaceTracking } from './vision/useFaceTracking';
import { useMicrophone } from './audio/useMicrophone';
import './App.css';

const SESSION_ID = 'mirror-' + Date.now().toString(36);

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
  const [ttsEnabled, setTtsEnabled] = useState(true);
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
        setError('WebSocket 连接失败，请先启动后端：.\\venv\\Scripts\\python run.py');
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

  const handleMicToggle = () => {
    if (micEnabled) {
      mic.stop();
      setMicEnabled(false);
    } else {
      mic.start().catch((e) => {
        console.warn('[app] mic start failed:', e);
        setMicEnabled(false);
      });
      setMicEnabled(true);
    }
  };

  const handleTextSend = () => {
    const input = document.getElementById('text-input') as HTMLInputElement;
    if (!input?.value.trim()) return;
    send({ event: 'audio.transcript', payload: { text: input.value.trim() } });
    input.value = '';
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
        <p style={{ color: '#888', fontSize: 13 }}>请确保后端已启动：.\venv\Scripts\python run.py</p>
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
              {status === 'ready' ? '小镜在线' : status === 'error' ? '连接失败' : '连接中...'}
            </span>
            {avatarRuntime && (
              <span className="status-info">
                {avatarRuntime.speaking ? '说话中' : ''} {avatarRuntime.expression !== 'neutral' ? avatarRuntime.expression : ''}
              </span>
            )}
          </div>

          {replyText && <div className="reply-bubble">{replyText}</div>}
          <div className="model-status">{modelStatus}</div>
        </div>

        <div className="controls">
          <div className="control-row">
            <button className={`ctrl-btn ${micEnabled ? 'active' : ''}`} onClick={handleMicToggle}>
              {micEnabled ? '停止录音' : '开始录音'}
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
