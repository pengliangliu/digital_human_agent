from app.agent.prompts import SYSTEM_PROMPT, WELCOME_MESSAGE


def test_default_prompt_is_general_interactive_avatar():
    identity_section = SYSTEM_PROMPT.split("## 你的能力", maxsplit=1)[0]

    assert "交互式数字人助手" in identity_section
    assert "魔镜" not in identity_section
    assert "虚拟试衣" not in identity_section
    assert "穿搭" not in identity_section
    assert "小镜" not in identity_section


def test_welcome_message_is_not_bound_to_mirror_or_fashion():
    assert "交互式数字人助手" in WELCOME_MESSAGE
    assert "魔镜" not in WELCOME_MESSAGE
    assert "虚拟试衣" not in WELCOME_MESSAGE
    assert "穿搭" not in WELCOME_MESSAGE
    assert "小镜" not in WELCOME_MESSAGE
