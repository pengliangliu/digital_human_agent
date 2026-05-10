from abc import ABC, abstractmethod


class VADProcessor(ABC):
    @abstractmethod
    def is_speech(self, audio_frame: bytes) -> bool:
        ...

    @abstractmethod
    def reset(self) -> None:
        ...


class WebRTCVAD(VADProcessor):
    def __init__(self, aggressiveness: int = 2, frame_duration_ms: int = 30) -> None:
        import webrtcvad

        self._vad = webrtcvad.Vad(aggressiveness)
        self._frame_ms = frame_duration_ms

    def is_speech(self, audio_frame: bytes) -> bool:
        try:
            return self._vad.is_speech(audio_frame, sample_rate=16000)
        except Exception:
            return False

    def reset(self) -> None:
        pass


class EnergyVAD(VADProcessor):
    def __init__(self, threshold: float = 0.02) -> None:
        self._threshold = threshold

    def is_speech(self, audio_frame: bytes) -> bool:
        import struct

        samples = struct.unpack(f"{len(audio_frame) // 2}h", audio_frame)
        if not samples:
            return False
        energy = sum(abs(s) for s in samples) / len(samples) / 32768.0
        return energy > self._threshold

    def reset(self) -> None:
        pass
