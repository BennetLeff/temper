"""The replay adapter, and the claim that it is the live path with other bytes.

The differential here is the point of the module. A replay adapter with its own
parser could pass every test in this file while saying nothing about the live
path -- and this repo has already paid twice for a pair of implementations that
agreed with each other and with nothing else. So the assertion is not "replay
decodes correctly", it is "replay and live produce the same typed view from the
same bytes".
"""

from __future__ import annotations

import json
import socket
from pathlib import Path
from typing import Any

import pytest

from temper_harness.provider.deepseek import (
    decode_completion,
    decode_stream_payloads,
    iter_sse_payloads,
    wire_body,
)
from temper_harness.provider.errors import MalformedResponse, RequestRejected
from temper_harness.provider.interface import (
    Event,
    ReasoningDelta,
    Request,
    StreamEnd,
    Terminal,
    TextDelta,
    ToolCallDelta,
    reassemble_tool_calls,
)
from temper_harness.provider.replay import ReplayTransport
from temper_harness.store import RecordingNotFound, RecordingStore
from tests.corpus import captured_request

CAPTURED = Path(__file__).resolve().parents[1] / "fixtures" / "captured"
ENTRIES: dict[str, dict[str, Any]] = {
    entry["name"]: entry
    for entry in json.loads((CAPTURED / "manifest.json").read_text(encoding="utf-8"))["probes"]
}

ARM = "tier-a"
ATTEMPT = 0
MODEL = "deepseek-flash"


def response_bytes(name: str) -> bytes:
    suffix = "sse" if ENTRIES[name]["stream"] else "json"
    return (CAPTURED / f"{name}.response.{suffix}").read_bytes()


def headers_of(name: str) -> dict[str, str]:
    meta = json.loads((CAPTURED / f"{name}.meta.json").read_text(encoding="utf-8"))
    return dict(meta["headers"])


def captured_body(name: str) -> dict[str, Any]:
    return json.loads((CAPTURED / f"{name}.request.json").read_text(encoding="utf-8"))


def _live_store(root: Path) -> RecordingStore:
    return RecordingStore(root, mode="live", arm=ARM, attempt=ATTEMPT)


def _replay(root: Path) -> ReplayTransport:
    return ReplayTransport(RecordingStore(root, mode="replay", arm=ARM, attempt=ATTEMPT))


def record_one(
    root: Path,
    name: str,
    *,
    http_status: int | None = None,
    headers: dict[str, str] | None = None,
    request: Request | None = None,
) -> None:
    """Write one captured exchange into the corpus under test.

    ``headers`` defaults to the captured allowlisted set, which is what the live
    adapter would have passed. Overriding it is how the contradictory-content-type
    cases get built: the store records whatever it is handed, and the adapter is
    what refuses a body that does not match its content type.
    """
    _live_store(root).record(
        request=wire_body(request or captured_request(name)),
        response_raw=response_bytes(name),
        headers=headers if headers is not None else headers_of(name),
        provider="deepseek",
        model=MODEL,
        http_status=ENTRIES[name]["http_status"] if http_status is None else http_status,
    )


def terminal_of(events: list[Event]) -> dict[str, Any]:
    terminals = [event for event in events if isinstance(event, Terminal)]
    assert len(terminals) == 1, f"expected exactly one terminal event, got {len(terminals)}"
    return terminals[0].envelope


def sse_payloads(name: str) -> list[bytes]:
    return [
        line[len(b"data: ") :]
        for line in response_bytes(name).split(b"\n")
        if line.startswith(b"data: ") and line != b"data: [DONE]"
    ]


# -- the differential -------------------------------------------------------


def test_the_replayed_typed_view_is_identical_to_the_live_decode(tmp_path: Path) -> None:
    """Same bytes, same decoder, same document -- differing only in provenance.

    If this passes and the decoded envelope is schema-valid, then a recorded run
    exercises the real decoder. If replay had its own parser, this comparison could
    not be written at all.
    """
    record_one(tmp_path, "parallel_tools")
    served = terminal_of(list(_replay(tmp_path).stream(captured_request("parallel_tools"))))

    assert served == decode_completion(response_bytes("parallel_tools"), served_from="replay")
    assert served["served_from"] == "replay"
    assert served["tool_calls"]


def test_a_replayed_stream_yields_the_same_events_as_the_live_decode(tmp_path: Path) -> None:
    record_one(tmp_path, "stream_plain")
    served = list(_replay(tmp_path).stream(captured_request("stream_plain")))
    expected = list(
        decode_stream_payloads(
            iter_sse_payloads(response_bytes("stream_plain").split(b"\n")), served_from="live"
        )
    )

    # StreamEnd carries no provenance, so the two sequences are directly comparable.
    assert served == expected
    assert isinstance(served[-1], StreamEnd)
    assert "".join(e.text for e in served if isinstance(e, TextDelta)) == "temper"
    assert any(isinstance(e, ReasoningDelta) for e in served)


def test_a_replayed_tool_stream_reassembles_the_same_calls(tmp_path: Path) -> None:
    record_one(tmp_path, "stream_tools")
    events = list(_replay(tmp_path).stream(captured_request("stream_tools")))

    calls = reassemble_tool_calls([e for e in events if isinstance(e, ToolCallDelta)])
    assert [call.name for call in calls] == ["place", "check"]
    assert [json.loads(call.arguments) for call in calls] == [
        json.loads(call["function"]["arguments"])
        for call in json.loads(
            (CAPTURED / "parallel_tools.response.json").read_text(encoding="utf-8")
        )["choices"][0]["message"]["tool_calls"]
    ]


def test_a_replayed_exchange_carries_the_recorded_headers(tmp_path: Path) -> None:
    """Provenance a caller may need: the provider's own correlation id."""
    record_one(tmp_path, "plain")
    meta = json.loads((CAPTURED / "plain.meta.json").read_text(encoding="utf-8"))
    served = _replay(tmp_path).stream(captured_request("plain"))
    list(served)  # drive the generator so the lookup happens
    recording = RecordingStore(tmp_path, mode="replay", arm=ARM, attempt=ATTEMPT).serve(
        wire_body(captured_request("plain"))
    )
    assert recording.headers["x-ds-trace-id"] == meta["headers"]["x-ds-trace-id"]


# -- refusals ---------------------------------------------------------------


def test_replay_refuses_a_provenance_lie(tmp_path: Path) -> None:
    """A recorded turn must not enter a scored aggregate as live (R15)."""
    record_one(tmp_path, "plain")
    base = captured_request("plain")
    lying = Request(
        model=base.model,
        messages=base.messages,
        tools=base.tools,
        temperature=base.temperature,
        max_tokens=base.max_tokens,
        served_from="live",
        stream=False,
    )
    with pytest.raises(ValueError, match="served_from='replay'"):
        list(_replay(tmp_path).stream(lying))


def test_replay_of_a_recorded_failure_reproduces_the_failure(tmp_path: Path) -> None:
    """A recording holds its status line, so a 400 replays as a 400.

    Without ``http_status`` on the recording, a replayed refusal would arrive as a
    200 whose body happens to be an error document, and the error taxonomy would
    classify the past as a completion.
    """
    record_one(tmp_path, "invalid_model")
    with pytest.raises(RequestRejected) as caught:
        list(_replay(tmp_path).stream(captured_request("invalid_model")))
    assert caught.value.http_status == 400


def test_a_stream_request_against_a_non_sse_recording_is_refused(tmp_path: Path) -> None:
    """The contradiction can only come from a corpus assembled by hand.

    The store cannot produce it: a body's ``stream`` field is set by the encoder
    from the request, so a recorded stream body is only ever looked up by a stream
    request. The guard exists for a recording that was copied, hand-edited, or
    written by a future caller, and overriding the content type is how that shape is
    built here.
    """
    record_one(tmp_path, "stream_plain", headers={"content-type": "application/json"})
    with pytest.raises(MalformedResponse, match="asked to replay a stream"):
        list(_replay(tmp_path).stream(captured_request("stream_plain")))


def test_a_single_response_request_against_an_sse_recording_is_refused(tmp_path: Path) -> None:
    record_one(
        tmp_path,
        "plain",
        headers={"content-type": "text/event-stream; charset=utf-8"},
    )
    with pytest.raises(MalformedResponse, match="asked to replay a single response"):
        list(_replay(tmp_path).stream(captured_request("plain")))


def test_a_miss_is_a_typed_refusal_not_an_empty_turn(tmp_path: Path) -> None:
    record_one(tmp_path, "plain")
    with pytest.raises(RecordingNotFound):
        list(_replay(tmp_path).stream(captured_request("parallel_tools")))


def test_a_replay_store_refuses_to_serve_in_live_mode(tmp_path: Path) -> None:
    """Mode exclusivity at the wiring level: the adapter cannot bypass the store."""
    from temper_harness.store import ModeViolationError

    record_one(tmp_path, "plain")
    with pytest.raises(ModeViolationError):
        list(ReplayTransport(_live_store(tmp_path)).stream(captured_request("plain")))


# -- offline by construction ------------------------------------------------


def test_replay_takes_no_network_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Poisoned sockets and a poisoned HTTP client, and replay still works.

    Stronger than asserting an absence: with every route to the network raising, a
    replay path that reached for it would not merely be wrong, it would fail. Both
    shapes are driven, because a stream and a single response take different
    branches in the adapter.
    """
    record_one(tmp_path, "plain")
    record_one(tmp_path, "stream_plain")

    def explode(*args: object, **kwargs: object) -> None:
        raise AssertionError("replay reached for the network")

    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(socket, "create_connection", explode)
    monkeypatch.setattr("requests.post", explode)

    transport = _replay(tmp_path)
    assert terminal_of(list(transport.stream(captured_request("plain"))))["content"]
    assert list(transport.stream(captured_request("stream_plain")))
