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
