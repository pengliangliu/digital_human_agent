from app.agent.behavior_planner import BehaviorPlanner


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
