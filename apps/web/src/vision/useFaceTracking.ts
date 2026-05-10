import { useEffect, useRef } from 'react';
import type { ClientEvent } from '../api/wsClient';

type SendFn = (event: ClientEvent) => void;

export function useFaceTracking(
  videoRef: React.RefObject<HTMLVideoElement | null>,
  send: SendFn,
  enabled: boolean
) {
  const intervalRef = useRef<number>(0);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    if (!enabled) return;

    const video = videoRef.current;
    if (!video || !video.readyState) {
      // Video not ready yet — wait and retry
      const retry = setTimeout(() => {
        if (video?.readyState) startTracking();
      }, 1000);
      return () => clearTimeout(retry);
    }

    startTracking();
    return () => clearInterval(intervalRef.current);

    function startTracking() {
      const cv = video!;
      const canvas = document.createElement('canvas');
      canvas.width = 320;
      canvas.height = 240;
      canvasRef.current = canvas;
      const ctx = canvas.getContext('2d', { willReadFrequently: true });
      if (!ctx) return;

      let prevCx = 0.5;
      let prevCy = 0.42;
      let prevYaw = 0;
      let prevPitch = 0;
      const SMOOTH = 0.35;

      function track() {
        if (!cv || cv.readyState < 2) return;
        if (cv.videoWidth === 0) return;

        canvas.width = cv.videoWidth;
        canvas.height = cv.videoHeight;
        ctx!.drawImage(cv, 0, 0);

        // Simple face-position estimation via skin-color center-of-mass
        // Sample the central region of the frame
        const w = cv.videoWidth;
        const h = cv.videoHeight;
        const sampleW = Math.floor(w * 0.6);
        const sampleH = Math.floor(h * 0.7);
        const sx = Math.floor((w - sampleW) / 2);
        const sy = Math.floor((h - sampleH) / 4);
        const imageData = ctx!.getImageData(sx, sy, sampleW, sampleH);
        const pixels = imageData.data;

        let sumX = 0, sumY = 0, count = 0;
        for (let y = 0; y < sampleH; y += 2) {
          for (let x = 0; x < sampleW; x += 2) {
            const idx = (y * sampleW + x) * 4;
            const r = pixels[idx];
            const g = pixels[idx + 1];
            const b = pixels[idx + 2];
            // Skin-color heuristic: warm-toned pixels
            if (r > 95 && g > 40 && b > 20 &&
                r > g && r > b &&
                Math.abs(r - g) > 15) {
              sumX += x;
              sumY += y;
              count++;
            }
          }
        }

        let userVisible = count > 50;
        let faceCenterX: number;
        let faceCenterY: number;
        let yaw: number;
        let pitch: number;
        let confidence: number;

        if (userVisible) {
          // Normalize face center to 0..1
          const cx = (sx + sumX / count) / w;
          const cy = (sy + sumY / count) / h;
          faceCenterX = prevCx + (cx - prevCx) * SMOOTH;
          faceCenterY = prevCy + (cy - prevCy) * SMOOTH;

          // Map face position to yaw/pitch
          // faceCenterX < 0.5 (face on left) → positive yaw → head turns left
          yaw = prevYaw + ((0.5 - faceCenterX) * 60 - prevYaw) * SMOOTH;
          pitch = prevPitch + ((faceCenterY - 0.42) * -40 - prevPitch) * SMOOTH;
          confidence = Math.min(count / 2000, 1.0);

          prevCx = faceCenterX;
          prevCy = faceCenterY;
          prevYaw = yaw;
          prevPitch = pitch;
        } else {
          faceCenterX = prevCx;
          faceCenterY = prevCy;
          yaw = 0;
          pitch = 0;
          confidence = 0;
        }

        send({
          event: 'vision.state',
          payload: {
            user_visible: userVisible,
            face_center_x: faceCenterX,
            face_center_y: faceCenterY,
            yaw,
            pitch,
            distance_m: 0.8 + (1 - Math.abs(faceCenterY - 0.5) * 2) * 0.5,
            confidence,
          },
        });
      }

      intervalRef.current = window.setInterval(track, 80);
    }
  }, [enabled, send]);
}
