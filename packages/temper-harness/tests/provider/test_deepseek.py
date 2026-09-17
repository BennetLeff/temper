"""The wire decoder and the live adapter, driven by captured bytes.

Every decoding assertion here runs against what the provider actually sent, and
every adapter assertion runs against a scripted HTTP layer that returns those same
bytes. Neither touches the network, which is the point: the live path's behaviour
is testable without being live, so a recorded success is evidence about it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from temper_harness.provider.deepseek import (
    DONE_SENTINEL,
    LiveTransport,
    decode_completion,
    decode_stream_payloads,
    is_event_stream,
    iter_sse_payloads,
    wire_body,
)
from temper_harness.provider.errors import (
    CredentialMissing,
    EndpointRejected,
    IncompleteStream,
    MalformedResponse,
    PreConnectionUnavailable,
    RequestRejected,
    ServerError,
    ToolSchemaRejected,
)
from temper_harness.provider.interface import (
    BufferedTransport,
    EndpointPolicy,
    ReasoningDelta,
    Request,
    StreamEnd,
    TextDelta,
    ToolCallDelta,
    UsageReported,
    reassemble_tool_calls,
)
from temper_harness.provider.messages import ChatMessage, ToolDefinition
from temper_harness.provider.usage import normalize_usage
from temper_harness.schema_registry import build_validator
from temper_harness.store.recorder import RecordingStore
from temper_harness.store.recordings import canonical_request_bytes, request_hash

CAPTURED = Path(__file__).resolve().parents[1] / "fixtures" / "captured"
ENTRIES: dict[str, dict[str, Any]] = {
    entry["name"]: entry
    for entry in json.loads((CAPTURED / "manifest.json").read_text(encoding="utf-8"))["probes"]
}

#: A key shaped like nothing a provider issues. The redaction canary scans for a
#: credential *shape*, so a test fixture that looked like a key would show up in
#: its report as a false positive.
TEST_KEY = "not-a-real-credential"


def response_bytes(name: str) -> bytes:
    suffix = "sse" if ENTRIES[name]["stream"] else "json"
    return (CAPTURED / f"{name}.response.{suffix}").read_bytes()


def request_of(name: str) -> dict[str, Any]:
    return json.loads((CAPTURED / f"{name}.request.json").read_text(encoding="utf-8"))


def response_of(name: str) -> dict[str, Any]:
    return json.loads(response_bytes(name))


def sse_payloads(name: str) -> list[bytes]:
    return [
        line[len(b"data: ") :]
        for line in response_bytes(name).split(b"\n")
        if line.startswith(b"data: ")
    ]


def successful_nonstreams() -> list[str]:
    return sorted(
        name
        for name, entry in ENTRIES.items()
        if entry["http_status"] == 200 and not entry["stream"]
    )


def rebuild_request(body: dict[str, Any]) -> Request:
    """The client's types, reconstructed from a captured wire body."""
    from temper_harness.provider.messages import ToolCall

    messages = [
        ChatMessage(
            role=message["role"],
            content=message.get("content"),
            reasoning_content=message.get("reasoning_content"),
            tool_calls=tuple(
                ToolCall(
                    id=call["id"],
                    name=call["function"]["name"],
                    arguments=call["function"]["arguments"],
                )
                for call in message.get("tool_calls", ())
            ),
            tool_call_id=message.get("tool_call_id"),
        )
        for message in body["messages"]
    ]
    tools = tuple(
        ToolDefinition(
            name=tool["function"]["name"],
            description=tool["function"]["description"],
            parameters=tool["function"]["parameters"],
        )
        for tool in body.get("tools", ())
    )
    return Request(
        model=body["model"],
        messages=messages,
        tools=tools,
        temperature=body.get("temperature"),
        max_tokens=body.get("max_tokens"),
        served_from="live",
        stream=body.get("stream", False),
    )


# -- decoding captured successes --------------------------------------------


@pytest.mark.parametrize("name", successful_nonstreams())
def test_every_captured_success_decodes_into_the_committed_envelope(name: str) -> None:
    """The decoder and the schema must agree on real bytes, not on examples.

    A per-response validation at runtime was rejected on purpose: an enum that
    rejects a newly-introduced finish_reason would make the transport brittle. The
    check belongs in CI over the corpus, and live drift belongs to the canary.
    """
    envelope = decode_completion(response_bytes(name), served_from="live")
    build_validator("envelope.schema.json").validate(envelope)


def test_the_decoded_tool_calls_keep_the_providers_ids_indices_and_arguments() -> None:
    envelope = decode_completion(response_bytes("parallel_tools"), served_from="live")
    captured = response_of("parallel_tools")["choices"][0]["message"]["tool_calls"]

    assert [call["id"] for call in envelope["tool_calls"]] == [call["id"] for call in captured]
    assert [call["index"] for call in envelope["tool_calls"]] == [0, 1]
    assert [call["name"] for call in envelope["tool_calls"]] == ["place", "check"]
    # The argument string is the provider's, byte for byte: re-encoding it would
    # normalize the escapes the fidelity oracle compares.
    assert [call["arguments"] for call in envelope["tool_calls"]] == [
        call["function"]["arguments"] for call in captured
    ]


def test_a_tool_call_turn_decodes_content_as_an_empty_string_not_null() -> None:
    envelope = decode_completion(response_bytes("parallel_tools"), served_from="live")
    assert envelope["content"] == ""
    assert envelope["finish_reason"] == "tool_calls"


def test_system_fingerprint_is_carried() -> None:
    envelope = decode_completion(response_bytes("plain"), served_from="live")
    assert envelope["system_fingerprint"] == response_of("plain")["system_fingerprint"]


def test_the_decoded_usage_reconciles_against_the_providers_own_total() -> None:
    envelope = decode_completion(response_bytes("plain"), served_from="live")
    usage = envelope["usage"]
    assert usage is not None
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]
    assert usage["reasoning_tokens"] <= usage["completion_tokens"]


def test_an_absent_usage_block_stays_null() -> None:
    """Distinct from a block whose fields are null, and the ledger distinguishes them."""
    body = json.dumps({"id": "m", "choices": [{"message": {"role": "assistant"}}]}).encode()
    assert decode_completion(body, served_from="live")["usage"] is None


@pytest.mark.parametrize(
    "body",
    [
        b"not json at all",
        b"[]",
        b'{"id": "m"}',
        b'{"id": "m", "choices": []}',
        b'{"id": "m", "choices": [{"message": null}]}',
    ],
)
def test_a_malformed_200_body_is_a_malformed_response(body: bytes) -> None:
    with pytest.raises(MalformedResponse):
        decode_completion(body, served_from="live")


def test_a_tool_call_without_an_id_is_a_malformed_response() -> None:
    body = json.dumps(
        {"choices": [{"message": {"tool_calls": [{"function": {"name": "place"}}]}}]}
    ).encode()
    with pytest.raises(MalformedResponse, match="carries no id"):
        decode_completion(body, served_from="live")


# -- decoding captured streams ----------------------------------------------


def test_the_captured_stream_decodes_to_deltas_and_a_stream_end() -> None:
    events = list(decode_stream_payloads(sse_payloads("stream_plain"), served_from="live"))
    assert isinstance(events[-1], StreamEnd)
    assert events[-1].finish_reason == "stop"
    assert events[-1].system_fingerprint == response_of("plain")["system_fingerprint"]

    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    reasoning = "".join(e.text for e in events if isinstance(e, ReasoningDelta))
    assert text == "temper"
    assert reasoning


def test_the_usage_of_a_stream_arrives_once_and_on_the_final_chunk() -> None:
    events = list(decode_stream_payloads(sse_payloads("stream_plain"), served_from="live"))
    usage_events = [e for e in events if isinstance(e, UsageReported)]
    assert len(usage_events) == 1
    usage = usage_events[0].usage
    assert usage["total_tokens"] == usage["prompt_tokens"] + usage["completion_tokens"]


def test_buffering_the_captured_stream_produces_a_schema_valid_envelope() -> None:
    """The whole streaming path, end to end, checked against the contract."""
    captured_body = response_bytes("stream_plain")

    class _ReplayOfBytes:
        def stream(self, request: Request):
            yield from decode_stream_payloads(sse_payloads("stream_plain"), served_from="live")

        def cancel(self) -> None: ...

    terminal = next(iter(BufferedTransport(_ReplayOfBytes()).stream(_request())))
    envelope = terminal.envelope
    assert envelope["content"] == "temper"
    assert envelope["finish_reason"] == "stop"
    build_validator("envelope.schema.json").validate(envelope)
    assert captured_body  # the bytes this was decoded from are the fixture


def test_streamed_tool_calls_reassemble_through_the_decoder() -> None:
    events = list(decode_stream_payloads(sse_payloads("stream_tools"), served_from="live"))
    calls = reassemble_tool_calls([e for e in events if isinstance(e, ToolCallDelta)])
    assert [call.name for call in calls] == ["place", "check"]
    assert all(json.loads(call.arguments) for call in calls)


def test_streaming_the_capture_one_byte_at_a_time_decodes_identically() -> None:
    """The chunk boundaries are the provider's, not ours.

    A decoder that assumed one chunk per event would pass on a whole-body read and
    fail on a real socket, where a JSON object routinely spans three reads. Feeding
    the same bytes one at a time is the cheapest way to drive that boundary through
    every position in the stream.
    """
    whole = list(decode_stream_payloads(sse_payloads("stream_plain"), served_from="live"))
    bytewise = list(
        decode_stream_payloads(
            iter_sse_payloads(_lines_of(response_bytes("stream_plain"), chunk_size=1)),
            served_from="live",
        )
    )
    assert bytewise == whole


def _lines_of(raw: bytes, *, chunk_size: int) -> list[bytes]:
    """Split raw bytes into lines, but hand them over in fixed-size chunks.

    Reuses the adapter's own chunk-to-line reader so the test drives the real
    boundary logic rather than a simplified copy of it.
    """
    from temper_harness.provider.deepseek import _ByteLineReader

    reader = _ByteLineReader()
    chunks = [raw[i : i + chunk_size] for i in range(0, len(raw), chunk_size)]
    return list(reader.lines(chunks))


def test_a_chunk_boundary_inside_a_multibyte_character_reassembles() -> None:
    """No mojibake, because the split happens before any text decoding.

    Constructed rather than captured: the corpus has no multi-byte character in a
    streamed delta, and the point is the reader's behaviour at a byte boundary, not
    the provider's choice of alphabet. The framing around the payload is the
    captured framing.
    """
    payload = json.dumps(
        {
            "id": "m",
            "model": "deepseek-flash",
            "choices": [{"delta": {"content": "café"}, "finish_reason": None}],
        },
        ensure_ascii=False,
    ).encode("utf-8")
    raw = b"data: " + payload + b"\n\n" + b"data: " + DONE_SENTINEL + b"\n\n"

    events = list(
        decode_stream_payloads(iter_sse_payloads(_lines_of(raw, chunk_size=1)), served_from="live")
    )
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    assert text == "café"
    assert "\ufffd" not in text


def test_a_truncated_capture_raises_incomplete_stream() -> None:
    """The final chunk and the sentinel are both dropped, so nothing terminated it."""
    payloads = sse_payloads("stream_plain")
    truncated = [p for p in payloads if p.strip() != DONE_SENTINEL][:-1]
    with pytest.raises(IncompleteStream):
        list(decode_stream_payloads(truncated, served_from="live"))


def test_a_real_truncation_has_no_usage_to_retain_and_that_is_the_honest_answer() -> None:
    """This provider puts usage on the final chunk, so a truncation loses it.

    The plan anticipated a truncation retaining partial usage. On this provider a
    truncation cannot: the chunk that would have carried it is the one that was
    lost. So the mechanism exists (see the next test) and the real corpus produces
    None, which the ledger records as ``usage_source: unknown`` rather than zero.
    """
    payloads = sse_payloads("stream_plain")
    truncated = [p for p in payloads if p.strip() != DONE_SENTINEL][:-1]

    class _Truncating:
        def stream(self, request: Request):
            yield from decode_stream_payloads(truncated, served_from="live")

        def cancel(self) -> None: ...

    with pytest.raises(IncompleteStream) as caught:
        list(BufferedTransport(_Truncating()).stream(_request()))
    assert caught.value.partial_usage is None


def test_usage_observed_before_a_truncation_is_retained() -> None:
    """The mechanism, exercised on the shape that produces it.

    A real corpus cannot produce this yet, and a mechanism that is never exercised
    is a mechanism nobody knows works. If the provider ever moves usage off the
    final chunk, this is the path that keeps the row honest.
    """

    class _UsageThenTruncated:
        def stream(self, request: Request):
            yield UsageReported({"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7})
            raise IncompleteStream("cut mid-stream")

        def cancel(self) -> None: ...

    with pytest.raises(IncompleteStream) as caught:
        list(BufferedTransport(_UsageThenTruncated()).stream(_request()))
    assert caught.value.partial_usage == {
        "prompt_tokens": 5,
        "completion_tokens": 2,
        "total_tokens": 7,
    }


def test_a_stream_that_ends_with_a_finish_reason_but_no_sentinel_is_complete() -> None:
    """The finish reason is decisive; the sentinel only corroborates.

    A provider that stopped emitting ``[DONE]`` would otherwise make every call
    look truncated -- a loud, wrong failure across the whole run.
    """
    payloads = [p for p in sse_payloads("stream_plain") if p.strip() != DONE_SENTINEL]
    events = list(decode_stream_payloads(payloads, served_from="live"))
    assert isinstance(events[-1], StreamEnd)
    assert events[-1].finish_reason == "stop"


def test_iter_sse_payloads_joins_multiline_data_and_ignores_comments() -> None:
    lines = [
        b": heartbeat",
        b'data: {"a":',
        b"data: 1}",
        b"",
        b"data: [DONE]",
        b"",
    ]
    assert list(iter_sse_payloads(lines)) == [b'{"a":\n1}', b"[DONE]"]


def test_is_event_stream_accepts_the_charset_parameter() -> None:
    assert is_event_stream("text/event-stream; charset=utf-8")
    assert not is_event_stream("application/json")
    assert not is_event_stream(None)


# -- the live adapter -------------------------------------------------------


def _request(**overrides: Any) -> Request:
    defaults: dict[str, Any] = {
        "model": "deepseek-flash",
        "messages": [ChatMessage(role="user", content="place it")],
        "temperature": 0,
        "max_tokens": 64,
        "served_from": "live",
    }
    defaults.update(overrides)
    return Request(**defaults)


class _FakeResponse:
    """A response object, scripted. Stands in for the socket."""

    def __init__(
        self,
        *,
        status_code: int = 200,
        body: bytes = b"",
        headers: dict[str, str] | None = None,
        chunks: list[bytes] | None = None,
        location: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.content = body
        self.headers = dict(headers or {})
        if location is not None:
            self.headers["location"] = location
        self._chunks = chunks
        self.closed = False

    def iter_content(self, chunk_size: int | None = None):
        yield from (self._chunks if self._chunks is not None else [self.content])

    def close(self) -> None:
        self.closed = True


def _adapter(
    response: _FakeResponse | None = None,
    *,
    error: BaseException | None = None,
    key: str | None = TEST_KEY,
    policy: EndpointPolicy | None = None,
    store: RecordingStore | None = None,
) -> tuple[LiveTransport, list[dict[str, Any]]]:
    calls: list[dict[str, Any]] = []

    def post(url: str, **kwargs: Any) -> _FakeResponse:
        calls.append({"url": url, **kwargs})
        if error is not None:
            raise error
        assert response is not None
        return response

    transport = LiveTransport(api_key=key, post=post, policy=policy, store=store)
    return transport, calls


def test_a_missing_credential_is_a_typed_refusal_and_sends_nothing() -> None:
    transport, calls = _adapter(key="   ")
    with pytest.raises(CredentialMissing):
        list(transport.stream(_request()))
    assert calls == []
    record = CredentialMissing("x").to_record()
    assert record["retryable"] is False and record["billable"] is False
    build_validator("error.schema.json").validate(record)


def test_a_host_override_is_refused_before_any_request_is_attempted() -> None:
    with pytest.raises(EndpointRejected, match="must be"):
        _adapter(policy=EndpointPolicy(base_url="https://api.example.com"))


def test_a_non_https_scheme_is_refused_at_construction() -> None:
    with pytest.raises(EndpointRejected, match="must use https"):
        _adapter(policy=EndpointPolicy(base_url="http://api.deepseek.com"))


def test_the_request_on_the_wire_is_exactly_the_canonical_encoding() -> None:
    """Request-as-sent equals request-as-constructed: no mutation, no truncation.

    The body the transport put on the wire is the body the store would hash for it.
    That equality is what makes a recording addressable, so it is asserted against
    the same function rather than against a second serializer that might agree.
    """
    request = _request(tools=(ToolDefinition(name="place", description="d", parameters={}),))
    transport, calls = _adapter(
        _FakeResponse(body=response_bytes("plain"), headers={"content-type": "application/json"})
    )
    list(transport.stream(request))

    sent = calls[0]["data"]
    assert sent == canonical_request_bytes(wire_body(request))
    assert request_hash(wire_body(request)) == request_hash(json.loads(sent))
    assert calls[0]["allow_redirects"] is False
    assert calls[0]["stream"] is True


def test_the_credential_travels_in_a_header_and_never_in_the_body() -> None:
    transport, calls = _adapter(
        _FakeResponse(body=response_bytes("plain"), headers={"content-type": "application/json"})
    )
    list(transport.stream(_request()))
    assert calls[0]["headers"]["Authorization"] == f"Bearer {TEST_KEY}"
    assert TEST_KEY.encode() not in calls[0]["data"]


def test_a_redirect_is_refused_rather_than_followed() -> None:
    transport, _ = _adapter(_FakeResponse(status_code=302, location="https://elsewhere.example"))
    with pytest.raises(EndpointRejected, match="refusing to follow"):
        list(transport.stream(_request()))


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("invalid_model", RequestRejected),
        ("reasoning_omitted", RequestRejected),
        ("orphan_tool_result", RequestRejected),
        ("invalid_tool_schema", ToolSchemaRejected),
    ],
)
def test_a_captured_400_classifies_from_its_body_through_the_adapter(
    name: str, expected: type[Exception]
) -> None:
    """Four 400s, one status, four different causes -- and one of them is a schema.

    This is the whole reason the classifier reads the body: `invalid_tool_schema`
    is genuinely a tool-schema rejection and the other three are not, and a
    status-only classifier would have called all four the same thing.
    """
    transport, _ = _adapter(
        _FakeResponse(
            status_code=ENTRIES[name]["http_status"],
            body=response_bytes(name),
            headers={"content-type": "application/json"},
        )
    )
    with pytest.raises(expected) as caught:
        list(transport.stream(_request()))
    assert caught.value.http_status == 400
    assert caught.value.retryable is False


def test_a_connection_refusal_is_classified_as_pre_connection() -> None:
    transport, _ = _adapter(error=ConnectionRefusedError("refused"))
    with pytest.raises(PreConnectionUnavailable) as caught:
        list(transport.stream(_request()))
    assert caught.value.retryable is True
    assert caught.value.billable is False


def test_asking_for_a_stream_and_receiving_json_is_a_malformed_response() -> None:
    transport, _ = _adapter(
        _FakeResponse(body=response_bytes("plain"), headers={"content-type": "application/json"})
    )
    with pytest.raises(MalformedResponse, match="asked for a stream"):
        list(transport.stream(_request(stream=True)))


def test_asking_for_one_response_and_receiving_a_stream_is_a_malformed_response() -> None:
    transport, _ = _adapter(
        _FakeResponse(
            body=response_bytes("stream_plain"),
            headers={"content-type": "text/event-stream; charset=utf-8"},
        )
    )
    with pytest.raises(MalformedResponse, match="asked for a single response"):
        list(transport.stream(_request()))


def test_a_provenance_lie_is_refused_by_the_live_transport() -> None:
    transport, calls = _adapter()
    with pytest.raises(ValueError, match="served_from='live'"):
        list(transport.stream(_request(served_from="replay")))
    assert calls == []


def test_the_response_is_closed_even_when_it_fails() -> None:
    """A leaked response object is a leaked connection."""
    response = _FakeResponse(status_code=500, body=b"boom")
    transport, _ = _adapter(response)
    with pytest.raises(ServerError):
        list(transport.stream(_request()))
    assert response.closed is True


def test_the_adapter_records_a_successful_exchange(tmp_path: Path) -> None:
    """R8 end to end: the adapter writes the payload it received."""
    store = RecordingStore(tmp_path, mode="live", arm="canary", attempt=0)
    request = _request()
    transport, _ = _adapter(
        _FakeResponse(
            body=response_bytes("plain"),
            headers={"content-type": "application/json", "x-ds-trace-id": "trace-1"},
        ),
        store=store,
    )
    list(transport.stream(request))

    served = RecordingStore(tmp_path, mode="replay", arm="canary", attempt=0).serve(
        wire_body(request)
    )
    assert served.response_raw == response_bytes("plain")
    assert served.http_status == 200
    assert served.headers["x-ds-trace-id"] == "trace-1"


def test_the_adapter_does_not_record_a_failure(tmp_path: Path) -> None:
    """The corpus is successes; a refusal belongs in the ledger's row."""
    store = RecordingStore(tmp_path, mode="live", arm="canary", attempt=0)
    transport, _ = _adapter(
        _FakeResponse(status_code=400, body=response_bytes("invalid_model")), store=store
    )
    with pytest.raises(RequestRejected):
        list(transport.stream(_request()))
    assert not any(tmp_path.rglob("*.json")), "a failed call must not enter the replay corpus"


def test_a_cancelled_stream_stops_before_the_terminal_chunk() -> None:
    """Cooperative cancellation: the consumer stops, the transport notices."""
    transport, _ = _adapter(
        _FakeResponse(
            body=response_bytes("stream_plain"),
            headers={"content-type": "text/event-stream"},
            chunks=[response_bytes("stream_plain")],
        )
    )
    events: list[Any] = []
    for event in transport.stream(_request(stream=True)):
        events.append(event)
        transport.cancel()
    assert not any(isinstance(event, StreamEnd) for event in events)
    assert not any(isinstance(event, UsageReported) for event in events)


def test_normalizing_a_captured_block_produces_the_committed_field_names() -> None:
    """The mapping's output names are the schema's, on real bytes.

    Not an idempotence claim: a normalized record is not a provider block, and
    feeding one back would find no ``*_details`` section to read. Asserting
    idempotence would have looked like a stronger test while checking something
    that was never true.
    """
    from temper_harness.provider.usage import usage_fields

    record = normalize_usage(response_of("plain")["usage"])
    assert set(record) == set(usage_fields())
    assert all(isinstance(value, int) for value in record.values())
