import collections
import time
from typing import Any

from app.schemas import VisionState


class TrackingStateManager:
    def __init__(self, smoothing_alpha: float = 0.3, min_confidence: float = 0.5, idle_timeout: float = 3.0) -> None:
        self._alpha = smoothing_alpha
        self._min_confidence = min_confidence
        self._idle_timeout = idle_timeout
        self._smoothed: dict[str, float | None] = {
            "yaw": None, "pitch": None, "face_center_x": None, "face_center_y": None, "distance_m": None,
        }
        self._last_seen = 0.0

    def smooth(self, raw: VisionState) -> VisionState:
        now = time.time()

        if raw.user_visible and raw.confidence >= self._min_confidence:
            self._last_seen = now
            self._smooth_field("yaw", raw.yaw)
            self._smooth_field("pitch", raw.pitch)
            self._smooth_field("face_center_x", raw.face_center_x)
            self._smooth_field("face_center_y", raw.face_center_y)
            self._smooth_field("distance_m", raw.distance_m)
        elif now - self._last_seen > self._idle_timeout:
            for k in self._smoothed:
                self._smoothed[k] = None

        return VisionState(
            user_visible=raw.user_visible and raw.confidence >= self._min_confidence,
            face_center_x=self._smoothed["face_center_x"],
            face_center_y=self._smoothed["face_center_y"],
            yaw=self._smoothed["yaw"],
            pitch=self._smoothed["pitch"],
            distance_m=self._smoothed["distance_m"],
            confidence=raw.confidence,
        )

    def _smooth_field(self, key: str, value: float | None) -> None:
        if value is None:
            return
        prev = self._smoothed[key]
        if prev is None:
            self._smoothed[key] = value
        else:
            self._smoothed[key] = self._alpha * value + (1 - self._alpha) * prev

    def reset(self) -> None:
        for k in self._smoothed:
            self._smoothed[k] = None
        self._last_seen = 0.0
