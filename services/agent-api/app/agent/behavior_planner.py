from typing import Any

from app.schemas import AvatarAction, VisionState


class BehaviorPlanner:
    def __init__(self) -> None:
        self._idle_actions = [
            AvatarAction(
                type="gesture",
                priority="normal",
                payload={"name": "idle_scan", "intensity": 0.2},
            )
        ]

    def from_vision(self, vision: VisionState) -> list[AvatarAction]:
        if not vision.user_visible or vision.confidence < 0.5:
            return self._idle_actions

        actions = [
            AvatarAction(
                type="look_at",
                priority="realtime",
                duration_ms=120,
                payload={
                    "target": "user_face",
                    "yaw": vision.yaw or 0.0,
                    "pitch": vision.pitch or 0.0,
                    "confidence": vision.confidence,
                },
            )
        ]

        # Add head pose if significant yaw/pitch
        yaw = vision.yaw or 0.0
        pitch = vision.pitch or 0.0
        if abs(yaw) > 15 or abs(pitch) > 10:
            actions.append(
                AvatarAction(
                    type="head_pose",
                    priority="realtime",
                    duration_ms=200,
                    payload={"yaw": yaw, "pitch": pitch, "roll": 0.0},
                )
            )

        return actions

    def from_agent_reply(self, reply: dict[str, Any]) -> list[AvatarAction]:
        emotion = reply.get("emotion", "neutral")
        actions: list[AvatarAction] = [
            AvatarAction(
                type="expression",
                priority="normal",
                duration_ms=5000,
                payload={"name": emotion, "intensity": 0.7},
            ),
        ]

        for action in reply.get("actions", []):
            t = action.get("type", "")
            if t == "gesture":
                actions.append(
                    AvatarAction(
                        type="gesture",
                        priority="normal",
                        duration_ms=action.get("duration_ms", 800),
                        payload={
                            "name": action.get("name", "nod"),
                            "intensity": action.get("intensity", 0.5),
                        },
                    )
                )
            elif t == "expression":
                # Update expression if explicitly specified
                actions.append(
                    AvatarAction(
                        type="expression",
                        priority="normal",
                        duration_ms=action.get("duration_ms", 3000),
                        payload={
                            "name": action.get("name", emotion),
                            "intensity": action.get("intensity", 0.6),
                        },
                    )
                )

        return actions
