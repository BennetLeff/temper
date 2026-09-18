"""Protocol faults: the message-array and reassembly rules, at their boundaries.

These are the faults whose whole purpose is to be caught **before** a request is
sent. R7 exists because a malformed array otherwise leaves the client as a
provider 400 -- and the captured corpus contains exactly that 400, so the local
guard can be checked against a refusal the provider really produces rather than
against one we imagined.
"""

from __future__ import annotations

from typing import Any

import pytest

from temper_harness.provider.deepseek import LiveTransport, wire_body
from temper_harness.provider.errors import MalformedStream
from temper_harness.provider.interface import Request, ToolCallDelta, reassemble_tool_calls
from temper_harness.provider.messages import (
    ChatMessage,
    MessageArrayError,
    ToolCall,
    build_wire_request,
)
from tests import corpus

KEY = "not-a-real-credential"


def _call(call_id: str, name: str = "place", arguments: str = '{"reference": "R1"}') -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=arguments)


def test_a_duplicate_provider_tool_call_id_is_a_protocol_error() -> None:
    """Two indices, one id.

    Each result the caller sends back is keyed by id, so a duplicate makes the
    pairing ambiguous: the provider would receive a message array that cannot be
    reconstructed from the calls it was told about. The captures mint unique ids, so
    this can only arrive from a malformed or interleaved stream.
    """
    with pytest.raises(MalformedStream, match="share the id"):
        reassemble_tool_calls(
            [
                ToolCallDelta(index=0, id="call_same", name="place", arguments="{}"),
                ToolCallDelta(index=1, id="call_same", name="check", arguments="{}"),
            ]
        )


def test_a_full_tool_sequence_round_trips_with_ordering_intact() -> None:
    """The interleave the loop actually produces, in the order it produces it."""
    messages = [
        ChatMessage(role="system", content="you place parts"),
        ChatMessage(role="user", content="place R1 and check clearance"),
        ChatMessage(
            role="assistant",
            content="",
            reasoning_content="two calls, in this order",
            tool_calls=(_call("call_a", "place"), _call("call_b", "check")),
        ),
        ChatMessage(role="tool", tool_call_id="call_a", content="placed"),
        ChatMessage(role="tool", tool_call_id="call_b", content="passes"),
        ChatMessage(role="assistant", content="done"),
    ]
    body = build_wire_request(
        model="deepseek-flash", messages=messages, temperature=0, max_tokens=64
    )

    assert [message["role"] for message in body["messages"]] == [
        "system",
        "user",
        "assistant",
        "tool",
        "tool",
        "assistant",
    ]
    assert [
        message["tool_call_id"] for message in body["messages"] if message["role"] == "tool"
    ] == [
        "call_a",
        "call_b",
    ]
    assert [call["id"] for call in body["messages"][2]["tool_calls"]] == ["call_a", "call_b"]
    # Replayed, not dropped: the provider refuses an assistant turn without it.
    assert body["messages"][2]["reasoning_content"] == "two calls, in this order"


def test_a_malformed_message_array_raises_with_zero_network_calls() -> None:
    """The captured orphan, refused locally.

    The corpus contains the provider's own 400 for this body, so the guard is
    checked against a real refusal rather than a hypothetical one -- and the
    assertion that matters is that no request left the process.
    """
    captured = corpus.captured_body("orphan_tool_result")
    messages = [
        ChatMessage(
            role=message["role"],
            content=message.get("content"),
            tool_call_id=message.get("tool_call_id"),
        )
        for message in captured["messages"]
    ]

    calls: list[Any] = []

    def post(url: str, **kwargs: Any) -> Any:
        calls.append(kwargs)
        raise AssertionError("a malformed array must never reach the network")

    transport = LiveTransport(api_key=KEY, post=post)
    request = Request(
        model="deepseek-flash",
        messages=messages,
        temperature=0,
        max_tokens=64,
        served_from="live",
    )
    with pytest.raises(MessageArrayError):
        list(transport.stream(request))
    assert calls == []


def test_building_the_wire_body_is_where_the_refusal_happens() -> None:
    """One home for the rule: the encoder, not the adapter and not the transport."""
    with pytest.raises(MessageArrayError):
        wire_body(
            Request(
                model="deepseek-flash",
                messages=[ChatMessage(role="tool", tool_call_id="nobody", content="x")],
                served_from="live",
            )
        )


def test_a_tool_result_may_not_precede_the_call_it_answers() -> None:
    """Ordering, not just membership: a result before its call is a different array."""
    with pytest.raises(MessageArrayError, match="matches no pending"):
        build_wire_request(
            model="deepseek-flash",
            messages=[
                ChatMessage(role="tool", tool_call_id="call_a", content="placed"),
                ChatMessage(role="assistant", tool_calls=(_call("call_a"),)),
            ],
        )
