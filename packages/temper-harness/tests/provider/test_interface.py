"""Tool-call reassembly, buffered assembly, and host pinning."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from temper_harness.provider.errors import EndpointRejected, MalformedStream
from temper_harness.provider.interface import (
    OFFICIAL_HOST,
    BufferedTransport,
    EndpointPolicy,
    Event,
    ReasoningDelta,
    Request,
    StreamEnd,
    Terminal,
    TextDelta,
    ToolCallDelta,
    UsageReported,
    reassemble_tool_calls,
    validate_tool_arguments,
)
from temper_harness.provider.messages import ChatMessage
from temper_harness.schema_registry import build_validator

USAGE = {
    "prompt_tokens": 12,
    "completion_tokens": 7,
    "reasoning_tokens": None,
    "cached_input_tokens": None,
    "total_tokens": 19,
}


def test_arguments_split_mid_escape_reassemble() -> None:
    """The chunk boundary that matters.

    ``\\`` + ``u00e9`` is one escape split across two chunks; naive per-chunk
    decoding produces mojibake or an unparseable fragment.
    """
    calls = reassemble_tool_calls(
        [
            ToolCallDelta(index=0, id="call-1", name="place", arguments='{"x": "a\\'),
            ToolCallDelta(index=0, arguments='u00e9"}'),
        ]
    )
    assert len(calls) == 1
    assert calls[0].arguments == '{"x": "a\\u00e9"}'
    validate_tool_arguments(calls)  # parses


def test_multiple_calls_reassemble_by_index() -> None:
    calls = reassemble_tool_calls(
        [
            ToolCallDelta(index=0, id="a", name="place", arguments='{"net":'),
            ToolCallDelta(index=1, id="b", name="check", arguments='{"rule":'),
            ToolCallDelta(index=0, arguments=' "GND"}'),
            ToolCallDelta(index=1, arguments=' "clearance"}'),
        ]
    )
    assert [c.id for c in calls] == ["a", "b"]
    assert calls[0].arguments == '{"net": "GND"}'
    assert calls[1].arguments == '{"rule": "clearance"}'


def test_one_index_carrying_two_ids_is_a_protocol_error() -> None:
    """Merging two different calls would produce valid JSON meaning the wrong thing."""
    with pytest.raises(MalformedStream, match="two different ids"):
        reassemble_tool_calls(
            [
                ToolCallDelta(index=0, id="a", name="place"),
                ToolCallDelta(index=0, id="b", name="place"),
            ]
        )


def test_an_index_that_never_carried_an_id_is_a_protocol_error() -> None:
    with pytest.raises(MalformedStream, match="never carried an id"):
        reassemble_tool_calls([ToolCallDelta(index=0, arguments="{}")])


def test_truncated_arguments_are_reported_as_a_transport_failure() -> None:
    """Not handed to a caller that would blame the model for bad arguments."""
    calls = reassemble_tool_calls(
        [ToolCallDelta(index=0, id="a", name="place", arguments='{"net": "GN')]
    )
    with pytest.raises(MalformedStream, match="not valid JSON"):
        validate_tool_arguments(calls)


def test_empty_arguments_are_tolerated() -> None:
    validate_tool_arguments(reassemble_tool_calls([ToolCallDelta(index=0, id="a", name="noop")]))


class _FakeTransport:
    """A scripted inner transport. Stands in for the fixture adapter U1 will build."""

    def __init__(
        self,
        events: list[Event],
        terminal_usage: dict[str, int | None] | None = USAGE,
    ) -> None:
        self._events = events
        self._terminal_usage = terminal_usage
        self.cancelled = False

    def stream(self, request: Request) -> Iterator[Event]:
        yield from self._events
        if self._terminal_usage is not None:
            yield UsageReported(self._terminal_usage)
        yield StreamEnd(
            id="msg-1",
            model=request.model,
            finish_reason="tool_calls",
            system_fingerprint="fp-probe",
        )

    def cancel(self) -> None:
        self.cancelled = True


def _request() -> Request:
    return Request(
        model="deepseek-flash",
        messages=[ChatMessage(role="user", content="place it")],
    )


def test_buffered_transport_yields_exactly_one_terminal_event() -> None:
    inner = _FakeTransport(
        [
            TextDelta("pla"),
            TextDelta("cing"),
            ReasoningDelta("thinking"),
            UsageReported(USAGE),
        ]
    )
    events = list(BufferedTransport(inner).stream(_request()))
    assert len(events) == 1
    assert isinstance(events[0], Terminal)


def test_the_buffered_envelope_keeps_every_field_explicit() -> None:
    """A field omitted here is invisible to every later layer.

    The assembled envelope is validated against the committed schema, because
    "explicit" is only useful if the result is a document the rest of the system
    can actually consume.
    """
    inner = _FakeTransport([TextDelta("placing"), UsageReported(USAGE)])
    terminal = next(iter(BufferedTransport(inner).stream(_request())))
    envelope = terminal.envelope

    assert envelope["id"] == "msg-1"
    assert envelope["model"] == "deepseek-flash"
    assert envelope["content"] == "placing"
    # "" not None: the provider reports an empty STRING for content on a
    # tool-call turn, and collapsing it to null would make the streamed and
    # non-streamed views of the same turn disagree.
    assert envelope["reasoning_content"] == ""
    assert envelope["finish_reason"] == "tool_calls"
    assert envelope["system_fingerprint"] == "fp-probe"
    assert envelope["tool_calls"] == []
    assert envelope["usage"] == USAGE
    assert envelope["served_from"] == "live"
    assert terminal.finish_reason == "tool_calls"
    build_validator("envelope.schema.json").validate(envelope)


def test_a_provider_stream_that_never_reports_usage_leaves_it_null() -> None:
    """R4 at the envelope boundary: absent is null, not an empty zero block."""
    inner = _FakeTransport([TextDelta("hi")], terminal_usage=None)
    terminal = next(iter(BufferedTransport(inner).stream(_request())))
    assert terminal.envelope["usage"] is None


def test_buffered_transport_assembles_fragmented_tool_calls() -> None:
    inner = _FakeTransport(
        [
            ToolCallDelta(index=0, id="c1", name="place", arguments='{"net":'),
            ToolCallDelta(index=0, arguments=' "GND"}'),
        ]
    )
    terminal = next(iter(BufferedTransport(inner).stream(_request())))
    calls = terminal.envelope["tool_calls"]
    assert len(calls) == 1
    assert calls[0]["id"] == "c1"
    assert calls[0]["arguments"] == '{"net": "GND"}'


def test_cancel_reaches_the_inner_transport() -> None:
    inner = _FakeTransport([])
    transport = BufferedTransport(inner)
    transport.cancel()
    assert inner.cancelled is True


# -- endpoint pinning --------------------------------------------------------


def test_the_official_endpoint_is_accepted() -> None:
    assert EndpointPolicy().validate() == f"https://{OFFICIAL_HOST}"


def test_a_host_override_is_refused() -> None:
    """A configured base URL is enough to send the key and board content elsewhere."""
    with pytest.raises(EndpointRejected, match="must be"):
        EndpointPolicy(base_url="https://api.example.com").validate()


def test_a_non_https_scheme_is_refused() -> None:
    with pytest.raises(EndpointRejected, match="must use https"):
        EndpointPolicy(base_url=f"http://{OFFICIAL_HOST}").validate()


def test_following_redirects_is_refused() -> None:
    with pytest.raises(EndpointRejected, match="redirects"):
        EndpointPolicy(follow_redirects=True).validate()
