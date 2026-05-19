from types import SimpleNamespace

from app.adapters.llm import _parse_llm_content


def test_parse_tool_calls_into_schema_models_from_json_arguments():
    raw_tool_call = SimpleNamespace(
        function=SimpleNamespace(name="try_on", arguments='{"garment_id": "top_white_001"}')
    )

    reply = _parse_llm_content("", [raw_tool_call])

    assert reply.tool_calls[0].name == "try_on"
    assert reply.tool_calls[0].arguments == {"garment_id": "top_white_001"}


def test_parse_tool_calls_accepts_dict_arguments():
    raw_tool_call = SimpleNamespace(
        function=SimpleNamespace(name="recommend_outfits", arguments={"style": "commute"})
    )

    reply = _parse_llm_content("", [raw_tool_call])

    assert reply.tool_calls[0].name == "recommend_outfits"
    assert reply.tool_calls[0].arguments == {"style": "commute"}


def test_parse_llm_json_preserves_runtime_avatar_actions():
    content = """
    {
      "reply_text": "我来展示一下动作。",
      "emotion": "friendly",
      "intent": "chat",
      "actions": [
        {"type": "bone_pose", "bones": [{"name": "Spine", "rotation": [0, 8, 0]}]},
        {"type": "morph_target", "name": "mouthSmile_L", "weight": 0.5},
        {"type": "viseme", "name": "A", "weight": 0.7},
        {"type": "animation_clip", "name": "wave", "loop": false}
      ],
      "tool_calls": [],
      "memory_updates": {}
    }
    """

    reply = _parse_llm_content(content, None)

    assert [action["type"] for action in reply.actions] == [
        "bone_pose",
        "morph_target",
        "viseme",
        "animation_clip",
    ]
