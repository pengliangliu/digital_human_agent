from app.agent.behavior_planner import BehaviorPlanner
from app.schemas import AvatarAction


def test_agent_reply_actions_do_not_stop_speech_before_tts_playback():
    planner = BehaviorPlanner()

    actions = planner.from_agent_reply(
        {
            "emotion": "friendly",
            "actions": [{"type": "gesture", "name": "nod", "intensity": 0.4}],
        }
    )

    action_types = [action.type for action in actions]
    assert "speech_start" not in action_types
    assert "speech_end" not in action_types
    assert "expression" in action_types
    assert "gesture" in action_types


def test_agent_reply_can_dispatch_runtime_avatar_actions():
    planner = BehaviorPlanner()

    actions = planner.from_agent_reply(
        {
            "emotion": "friendly",
            "actions": [
                {
                    "type": "bone_pose",
                    "priority": "realtime",
                    "duration_ms": 120,
                    "bones": [
                        {
                            "name": "Head",
                            "rotation": [0, 15, 0],
                            "weight": 0.8,
                        }
                    ],
                },
                {
                    "type": "morph_target",
                    "name": "mouthSmile_L",
                    "weight": 0.6,
                },
                {
                    "type": "viseme",
                    "name": "A",
                    "weight": 0.7,
                },
                {
                    "type": "animation_clip",
                    "name": "wave",
                    "loop": False,
                    "fade_ms": 150,
                },
            ],
        }
    )

    runtime_actions = actions[1:]
    assert [action.type for action in runtime_actions] == [
        "bone_pose",
        "morph_target",
        "viseme",
        "animation_clip",
    ]
    assert runtime_actions[0].priority == "realtime"
    assert runtime_actions[0].duration_ms == 120
    assert runtime_actions[0].payload == {
        "bones": [{"name": "Head", "rotation": [0, 15, 0], "weight": 0.8}]
    }
    assert runtime_actions[1].payload == {"name": "mouthSmile_L", "weight": 0.6}
    assert runtime_actions[2].payload == {"name": "A", "weight": 0.7}
    assert runtime_actions[3].payload == {"name": "wave", "loop": False, "fade_ms": 150}


def test_avatar_action_schema_accepts_runtime_action_types():
    action = AvatarAction(
        type="animation_clip",
        priority="blocking",
        duration_ms=2000,
        payload={"name": "try_on_turntable", "loop": False},
    )

    assert action.type == "animation_clip"
    assert action.priority == "blocking"
