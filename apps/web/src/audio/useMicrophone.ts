import { useEffect, useRef, useCallback, useState } from 'react';
import type { ClientEvent } from '../api/wsClient';

type SendFn = (event: ClientEvent) => void;

type MicState = {
  isRecording: boolean;
  status: 'idle' | 'starting' | 'recording' | 'encoding' | 'error';
  error: string;
  start: () => Promise<void>;
  stop: () => void;
};

export function useMicrophone(send: SendFn, enabled: boolean): MicState {
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const isRecordingRef = useRef(false);
  const [status, setStatus] = useState<MicState['status']>('idle');
  const [error, setError] = useState('');
  const sendRef = useRef(send);
  sendRef.current = send;

  const stopTracks = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.requestData();
      recorderRef.current.stop();
      return;
    }
    stopTracks();
    isRecordingRef.current = false;
    setStatus('idle');
  }, [stopTracks]);

  const start = useCallback(async () => {
    setError('');
    setStatus('starting');
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('当前浏览器不支持麦克风录音');
      }
      if (typeof MediaRecorder === 'undefined') {
        throw new Error('当前浏览器不支持 MediaRecorder 录音');
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      isRecordingRef.current = true;
      chunksRef.current = [];

      const mimeType = selectMimeType();
      const recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
      recorderRef.current = recorder;

      recorder.ondataavailable = (e) => {
        if (e.data.size === 0) return;
        chunksRef.current.push(e.data);
      };

      recorder.onstop = async () => {
        try {
          setStatus('encoding');
          const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
          chunksRef.current = [];
          stopTracks();
          isRecordingRef.current = false;
          if (blob.size === 0) {
            setStatus('idle');
            return;
          }
          sendRef.current({
            event: 'audio.data',
            payload: { audio: await blobToBase64(blob) },
          });
          setStatus('idle');
        } catch (err) {
          const message = err instanceof Error ? err.message : '录音处理失败';
          setError(message);
          setStatus('error');
        }
      };

      recorder.onerror = () => {
        setError('浏览器录音失败');
        setStatus('error');
        stopTracks();
        isRecordingRef.current = false;
      };

      recorder.start();
      setStatus('recording');
    } catch (err) {
      console.error('[mic] access denied:', err);
      const message = err instanceof Error ? err.message : '无法访问麦克风';
      setError(message);
      setStatus('error');
      stopTracks();
      isRecordingRef.current = false;
      throw err;
    }
  }, [stopTracks]);

  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    get isRecording() {
      return isRecordingRef.current;
    },
    status,
    error,
    start,
    stop,
  };
}

function selectMimeType(): string {
  const types = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'];
  return types.find((type) => MediaRecorder.isTypeSupported(type)) || '';
}

async function blobToBase64(blob: Blob): Promise<string> {
  const buf = await blob.arrayBuffer();
  const bytes = new Uint8Array(buf);
  const chunkSize = 0x8000;
  let binary = '';
  for (let i = 0; i < bytes.length; i += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(i, i + chunkSize));
  }
  return btoa(binary);
}
