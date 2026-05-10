import { useEffect, useRef, useCallback } from 'react';
import type { ClientEvent } from '../api/wsClient';

type SendFn = (event: ClientEvent) => void;

type MicState = {
  isRecording: boolean;
  start: () => Promise<void>;
  stop: () => void;
};

export function useMicrophone(send: SendFn, enabled: boolean): MicState {
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const isRecordingRef = useRef(false);
  const sendRef = useRef(send);
  sendRef.current = send;

  const stop = useCallback(() => {
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop();
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
    }
    isRecordingRef.current = false;
  }, []);

  const start = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { sampleRate: 16000, channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
      streamRef.current = stream;
      isRecordingRef.current = true;

      const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      recorderRef.current = recorder;

      recorder.ondataavailable = async (e) => {
        if (e.data.size === 0) return;
        // Convert blob to base64
        const buf = await e.data.arrayBuffer();
        const bytes = new Uint8Array(buf);
        let binary = '';
        for (let i = 0; i < bytes.length; i++) {
          binary += String.fromCharCode(bytes[i]);
        }
        const b64 = btoa(binary);
        sendRef.current({
          event: 'audio.data',
          payload: { audio: b64 },
        });
      };

      recorder.start(1000); // 1-second chunks
    } catch (err) {
      console.error('[mic] access denied:', err);
    }
  }, []);

  useEffect(() => {
    return () => {
      stop();
    };
  }, [stop]);

  return {
    get isRecording() {
      return isRecordingRef.current;
    },
    start,
    stop,
  };
}
