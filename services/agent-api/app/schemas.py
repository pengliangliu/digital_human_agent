from typing import Any, Literal

from pydantic import BaseModel, Field


class ClientEvent(BaseModel):
    event: str
    payload: dict[str, Any] = Field(default_factory=dict)


class VisionState(BaseModel):
    user_visible: bool = False
    face_center_x: float | None = None
    face_center_y: float | None = None
    yaw: float | None = None
    pitch: float | None = None
    distance_m: float | None = None
    confidence: float = 0.0


class AvatarAction(BaseModel):
    type: Literal[
        "look_at",
        "head_pose",
        "gesture",
        "expression",
        "speech_start",
        "speech_end",
        "lip_sync",
        "pose",
        "bone_pose",
        "morph_target",
        "viseme",
        "animation_clip",
        "motion_sequence",
        "try_on",
        "load_avatar",
    ]
    priority: Literal["realtime", "normal", "blocking"] = "normal"
    duration_ms: int | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class AgentReply(BaseModel):
    reply_text: str
    emotion: str = "neutral"
    intent: str = "chat"
    actions: list[dict[str, Any]] = Field(default_factory=list)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    memory_updates: dict[str, Any] = Field(default_factory=dict)


AVAILABLE_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "recommend_outfits",
            "description": "可选扩展：当用户明确提出造型或服装需求时，按偏好给出候选建议",
            "parameters": {
                "type": "object",
                "properties": {
                    "style": {"type": "string", "description": "风格偏好：casual/formal/sporty/commute"},
                    "color_preference": {"type": "string", "description": "颜色偏好：light/dark/bright"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "try_on",
            "description": "可选扩展：当用户明确提出展示需求时，让数字人加载指定造型资产",
            "parameters": {
                "type": "object",
                "properties": {
                    "garment_id": {"type": "string", "description": "造型资产ID"},
                    "layer_id": {"type": "string", "description": "资产层级：upper/lower/outer"},
                },
                "required": ["garment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_profile",
            "description": "获取当前用户画像和明确记录的偏好信息",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
