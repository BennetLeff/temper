"""R7: the message array is validated locally, before anything is sent."""

from __future__ import annotations

import pytest

from temper_harness.provider.messages import (
    ChatMessage,
    MessageArrayError,
    ToolCall,
    ToolDefinition,
    build_wire_request,
    validate_messages,
)

STRICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["net", "layer"],
    "properties": {
        "net": {"type": "string", "enum": ["GATE_HS", "GND"]},
        "layer": {"$ref": "#/$defs/layer"},
    },
    "$defs": {"layer": {"oneOf": [{"const": "F.Cu"}, {"const": "B.Cu"}]}},
}


def _call(call_id: str, name: str = "place") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments='{"net":"GND"}')


def test_an_empty_array_is_rejected() -> None:
    with pytest.raises(MessageArrayError):
        validate_messages([])


def test_a_simple_conversation_passes() -> None:
    validate_messages(
        [
            ChatMessage(role="system", content="you are an agent"),
            ChatMessage(role="user", content="place the part"),
            ChatMessage(role="assistant", content="ok"),
        ]
    )


def test_an_assistant_turn_with_no_tool_calls_is_valid() -> None:
    validate_messages([ChatMessage(role="assistant", content="done")])


def test_parallel_tool_calls_then_matching_results_in_order() -> None:
    validate_messages(
        [
            ChatMessage(role="user", content="place and check"),
            ChatMessage(role="assistant", tool_calls=(_call("a"), _call("b"))),
            ChatMessage(role="tool", tool_call_id="a", content="ok"),
            ChatMessage(role="tool", tool_call_id="b", content="ok"),
            ChatMessage(role="assistant", content="finished"),
        ]
    )


def test_a_tool_result_matching_no_call_is_rejected() -> None:
    """The local check that stops a provider 400 being read as model failure."""
    with pytest.raises(MessageArrayError, match="matches no pending"):
        validate_messages(
            [
                ChatMessage(role="assistant", tool_calls=(_call("a"),)),
                ChatMessage(role="tool", tool_call_id="ghost", content="ok"),
            ]
        )


def test_a_duplicate_tool_call_id_is_rejected() -> None:
    with pytest.raises(MessageArrayError, match="duplicate tool call id"):
        validate_messages(
            [
                ChatMessage(role="assistant", tool_calls=(_call("a"), _call("a"))),
                ChatMessage(role="tool", tool_call_id="a", content="ok"),
            ]
        )


def test_an_unanswered_tool_call_at_the_end_is_rejected() -> None:
    with pytest.raises(MessageArrayError, match="ends with unanswered"):
        validate_messages([ChatMessage(role="assistant", tool_calls=(_call("a"),))])


def test_moving_on_with_a_pending_tool_call_is_rejected() -> None:
    with pytest.raises(MessageArrayError, match="still unanswered"):
        validate_messages(
            [
                ChatMessage(role="assistant", tool_calls=(_call("a"),)),
                ChatMessage(role="assistant", content="never mind"),
            ]
        )


def test_a_tool_message_may_not_carry_tool_calls() -> None:
    with pytest.raises(MessageArrayError, match="must not carry tool_calls"):
        validate_messages(
            [
                ChatMessage(role="assistant", tool_calls=(_call("a"),)),
                ChatMessage(role="tool", tool_call_id="a", tool_calls=(_call("b"),)),
            ]
        )


def test_a_tool_message_requires_an_id() -> None:
    with pytest.raises(MessageArrayError, match="requires a tool_call_id"):
        validate_messages([ChatMessage(role="tool", content="ok")])


def test_system_and_user_require_content() -> None:
    with pytest.raises(MessageArrayError, match="requires content"):
        validate_messages([ChatMessage(role="user")])


def test_an_unknown_role_is_rejected() -> None:
    with pytest.raises(MessageArrayError, match="unknown role"):
        validate_messages([ChatMessage(role="wizard", content="hi")])


def test_assistant_may_carry_tool_calls_with_null_content() -> None:
    wire = ChatMessage(role="assistant", tool_calls=(_call("a"),)).to_wire()
    assert wire["role"] == "assistant"
    assert "content" not in wire
    assert wire["tool_calls"][0]["function"]["name"] == "place"


def test_validation_happens_before_anything_is_sent() -> None:
    """build_wire_request validates, so a bad array never reaches an adapter."""
    with pytest.raises(MessageArrayError):
        build_wire_request(
            model="deepseek-v4.1-flash",
            messages=[
                ChatMessage(role="assistant", tool_calls=(_call("a"),)),
                ChatMessage(role="tool", tool_call_id="ghost", content="ok"),
            ],
        )


# -- tool definitions pass through unchanged ---------------------------------


def test_tool_schema_keywords_survive_the_round_trip() -> None:
    """If the client filtered to a known keyword set, the model would be asked
    to satisfy a schema it never saw."""
    tool = ToolDefinition(name="place", description="place a part", parameters=STRICT_SCHEMA)
    wire = tool.to_wire()["function"]["parameters"]
    assert wire == STRICT_SCHEMA
    assert wire["additionalProperties"] is False
    assert "$defs" in wire
    assert wire["properties"]["layer"] == {"$ref": "#/$defs/layer"}


def test_a_caller_mutating_its_schema_cannot_change_what_was_sent() -> None:
    original = {"type": "object", "properties": {"net": {"type": "string"}}}
    tool = ToolDefinition(name="place", description="d", parameters=original)
    original["properties"]["net"]["type"] = "integer"
    assert tool.to_wire()["function"]["parameters"]["properties"]["net"]["type"] == "string"


def test_the_schema_digest_is_stable_and_content_addressed() -> None:
    a = ToolDefinition(name="place", description="d", parameters=STRICT_SCHEMA)
    b = ToolDefinition(name="place", description="d", parameters=STRICT_SCHEMA)
    c = ToolDefinition(name="place", description="d", parameters={"type": "object"})
    assert a.digest() == b.digest()
    assert a.digest() != c.digest()
    assert len(a.digest()) == 64
