"""The transport seam: events, reassembly, the buffered default, and host pinning.

Two decisions here are cheap now and rewrites later.

*Streaming is the interface, buffering is an implementation.* Retrofitting
partial output onto a request/response API is a rewrite, and the Agents View
(S5) needs to attach to a run in progress.

*Tool-call assembly is a pure function.* Arguments arrive fragmented across
chunks and are frequently split mid-escape, so reassembly by ``index`` is
testable without a provider — which is the only reason this half of U3 can be
built before U1's capture exists.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from temper_harness.provider.errors import EndpointRejected, MalformedStream, TransportError
from temper_harness.provider.messages import ChatMessage, ToolCall, ToolDefinition

OFFICIAL_HOST = "api.deepseek.com"


# -- events ------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TextDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ReasoningDelta:
    text: str


@dataclass(frozen=True, slots=True)
class ToolCallDelta:
    """A fragment of a tool call. ``arguments`` may split mid-escape."""

    index: int
    id: str | None = None
    name: str | None = None
    arguments: str = ""


@dataclass(frozen=True, slots=True)
class UsageReported:
    usage: dict[str, int | None]


@dataclass(frozen=True, slots=True)
class StreamEnd:
    """The metadata a streaming provider puts on its final chunk.

    Distinct from :class:`Terminal`, and the distinction is load-bearing. A
    streaming transport has the finish reason, the message id, the reported model,
    and the backend fingerprint at the end of the stream, but it does *not* have
    an assembled turn -- the deltas are the turn, and the consumer accumulated
    them. Emitting a partial envelope as a ``Terminal`` would be a document that
    satisfies no schema; emitting this keeps the two roles separate. A consumer
    that wants the assembled turn wraps its transport in
    :class:`BufferedTransport`.
    """

    id: str
    model: str
    finish_reason: str | None
    system_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class Terminal:
    """The single terminal event a buffered transport yields."""

    envelope: dict[str, Any]

    @property
    def finish_reason(self) -> str | None:
        return self.envelope.get("finish_reason")


Event = TextDelta | ReasoningDelta | ToolCallDelta | UsageReported | StreamEnd | Terminal


# -- request -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Request:
    model: str
    messages: list[ChatMessage]
    tools: tuple[ToolDefinition, ...] = field(default=())
    #: Accepted and **ignored while thinking mode is enabled**, which is the provider's
    #: default: the documentation states thinking mode does not support `temperature`,
    #: `presence_penalty`, or `frequency_penalty`, and that setting them neither errors nor
    #: has an effect. Do not rely on it for determinism. It takes effect only with
    #: ``thinking=False``.
    temperature: float | None = None
    max_tokens: int | None = None
    #: The provider's isolation control for KVCache, content safety, and scheduling. Two
    #: experiment arms sharing a cache would have one arm's input priced at cache-hit rates
    #: for text the other arm paid to cache -- enough to invalidate a fixed-expenditure
    #: comparison with nothing appearing in any response.
    user_id: str | None = None
    #: Thinking mode, which the provider enables by default. ``False`` is the only way to
    #: make ``temperature`` effective, and the cheapest way to cut output tokens, because
    #: reasoning tokens are billed as output.
    thinking: bool | None = None
    #: One of the documented efforts (see ``REASONING_EFFORT_MAP``). Requested effort is
    #: *mapped*, not honoured literally: ``medium`` becomes ``high``.
    reasoning_effort: str | None = None
    #: Set by the caller, and asserted by the transport rather than trusted: a live
    #: transport refuses to stamp a row "replay" and a replay transport refuses to
    #: stamp one "live". Provenance is the one field a caller must not be able to
    #: get wrong, because a recorded turn summed into a scored aggregate is exactly
    #: what R15 fails closed on.
    served_from: str = "live"
    stream: bool = False


# -- reassembly --------------------------------------------------------------


def reassemble_tool_calls(deltas: Sequence[ToolCallDelta]) -> list[ToolCall]:
    """Fold fragmented tool-call deltas into complete calls, by ``index``.

    A duplicate index is a protocol violation rather than a merge: concatenating
    two different calls into one would produce arguments that parse as valid
    JSON while meaning something the model never said.
    """
    order: list[int] = []
    ids: dict[int, str] = {}
    names: dict[int, str] = {}
    arguments: dict[int, list[str]] = {}

    for delta in deltas:
        if delta.index not in arguments:
            order.append(delta.index)
            arguments[delta.index] = []
            if delta.id is not None:
                ids[delta.index] = delta.id
            if delta.name is not None:
                names[delta.index] = delta.name
        else:
            if delta.id is not None and ids.get(delta.index) not in (None, delta.id):
                raise MalformedStream(
                    f"tool call index {delta.index} carried two different ids: "
                    f"{ids[delta.index]!r} and {delta.id!r}"
                )
        arguments[delta.index].append(delta.arguments)

    calls: list[ToolCall] = []
    for index in order:
        call_id = ids.get(index)
        if not call_id:
            raise MalformedStream(f"tool call index {index} never carried an id")
        calls.append(
            ToolCall(
                id=call_id,
                name=names.get(index, ""),
                arguments="".join(arguments[index]),
                index=index,
            )
        )

    # Two calls sharing an id is a protocol error rather than a curiosity: the
    # caller answers each call with a `tool` message keyed by id, so a duplicate
    # makes the pairing ambiguous and the provider would receive a message array
    # that cannot be reconstructed. The captures mint unique ids, so this can only
    # fire on a malformed or interleaved stream.
    seen: set[str] = set()
    for call in calls:
        if call.id in seen:
            raise MalformedStream(
                f"two tool calls in one response share the id {call.id!r}; "
                "a tool result could not say which one it answers"
            )
        seen.add(call.id)
    return calls


def validate_tool_arguments(calls: Sequence[ToolCall]) -> None:
    """Every assembled argument string must be parseable JSON.

    A tool call whose arguments do not parse is a truncated or interleaved
    stream, and it must be reported as a transport failure rather than handed to
    a caller that will blame the model.
    """
    for call in calls:
        if not call.arguments:
            continue
        try:
            json.loads(call.arguments)
        except json.JSONDecodeError as err:
            raise MalformedStream(
                f"tool call {call.id!r} arguments are not valid JSON: {err}"
            ) from err


# -- transport ---------------------------------------------------------------


@runtime_checkable
class Transport(Protocol):
    """What every provider adapter provides. There are exactly two: live, replay.

    Cancellation is Python's own: closing the event iterator unwinds the adapter's
    generator, which runs its ``finally`` and closes the HTTP response. There is
    deliberately **no** ``cancel()`` method, because a method on the transport
    cannot be per-call -- it would have to reach whichever call the instance happens
    to be serving, and an instance-level flag is reset by the other call the moment
    two streams overlap. A transport that silently cancels somebody else's stream is
    worse than one that offers no cancellation at all.

    Found by porting the concurrency fault from the prior attempt's diagnostic, and
    it is the same shape as everything else in this package's history: correct while
    calls are sequential, and wrong the first time they are not.
    """

    def stream(self, request: Request) -> Iterator[Event]: ...


def buffer_events(
    events: Iterable[Event], *, served_from: str, default_model: str = ""
) -> dict[str, Any]:
    """Fold an event stream into the committed envelope.

    A function rather than a private method, because two callers assemble a turn: a
    buffered consumer, and the oracle checking a recorded stream. A second assembly
    path would be a second definition of what a turn is, and the two would agree
    right up until one of them was edited.

    An inner :class:`Terminal` short-circuits: a transport that already assembled a
    turn has nothing to add.
    """
    text: list[str] = []
    reasoning: list[str] = []
    deltas: list[ToolCallDelta] = []
    usage: dict[str, int | None] | None = None
    finish_reason: str | None = None
    message_id = ""
    model = default_model
    system_fingerprint: str | None = None

    try:
        for event in events:
            if isinstance(event, TextDelta):
                text.append(event.text)
            elif isinstance(event, ReasoningDelta):
                reasoning.append(event.text)
            elif isinstance(event, ToolCallDelta):
                deltas.append(event)
            elif isinstance(event, UsageReported):
                usage = event.usage
            elif isinstance(event, StreamEnd):
                finish_reason = event.finish_reason
                message_id = event.id
                model = event.model
                system_fingerprint = event.system_fingerprint
            elif isinstance(event, Terminal):
                return event.envelope
    except TransportError as err:
        # The accumulator is about to be unwound, and with it the only record of
        # what this call cost. Attach it before re-raising so the ledger can write
        # an `incomplete` row carrying real usage rather than a zero.
        if err.partial_usage is None:
            err.partial_usage = usage
        raise

    calls = reassemble_tool_calls(deltas)
    validate_tool_arguments(calls)

    # Empty accumulation stays "" rather than becoming None. Captured evidence: a
    # tool-call turn reports content as an empty STRING, with no content deltas at
    # all in the streamed form. Collapsing the two would make the streaming and
    # non-streaming paths disagree about the same turn, and the loop must not be
    # able to tell which path it used. `null` still means what the provider means
    # by it -- the field was absent from the response -- and that is decided by the
    # decoder, not here.
    return {
        "id": message_id,
        "model": model,
        "finish_reason": finish_reason,
        "content": "".join(text),
        "reasoning_content": "".join(reasoning),
        "system_fingerprint": system_fingerprint,
        "tool_calls": [
            {
                "id": call.id,
                "index": call.index,
                "name": call.name,
                "arguments": call.arguments,
            }
            for call in calls
        ],
        "usage": usage,
        "served_from": served_from,
    }


def close_events(events: object) -> None:
    """Close an event iterator if it can be closed.

    The cancellation path, and it lives here rather than in each adapter so both get
    it: closing the adapter's generator runs the adapter's own ``finally``, which is
    what closes the HTTP response. Duck-typed because a test transport may hand back
    a plain list iterator.
    """
    close = getattr(events, "close", None)
    if callable(close):
        close()


class BufferedTransport:
    """Adapt a streaming transport to one terminal event.

    The S0 default. It consumes the inner stream fully before yielding, so any inner
    error surfaces before a caller sees a partial turn it might act on. That also
    means a buffered stream is all-or-nothing: there is no yield point at which a
    consumer could cancel it, which is why a caller that needs to cancel reads the
    streaming adapter directly.
    """

    def __init__(self, inner: Transport) -> None:
        self._inner = inner

    def stream(self, request: Request) -> Iterator[Event]:
        events = self._inner.stream(request)
        try:
            yield Terminal(
                buffer_events(
                    events,
                    served_from=request.served_from,
                    default_model=request.model,
                )
            )
        finally:
            close_events(events)


# -- endpoint pinning (R16) --------------------------------------------------


@dataclass(frozen=True, slots=True)
class EndpointPolicy:
    """Pins the live adapter to the official host.

    A base URL read from configuration, or a followed redirect, is enough to
    send both the API key and confidential board content to an arbitrary host —
    which is the intermediary the design rejected when it chose the official
    API over the aggregator aliases.
    """

    base_url: str = f"https://{OFFICIAL_HOST}"
    follow_redirects: bool = False

    def validate(self) -> str:
        parsed = urlparse(self.base_url)
        if parsed.scheme != "https":
            raise EndpointRejected(f"live endpoint must use https, got scheme {parsed.scheme!r}")
        if parsed.hostname != OFFICIAL_HOST:
            raise EndpointRejected(
                f"live endpoint must be {OFFICIAL_HOST!r}, got host {parsed.hostname!r}"
            )
        if self.follow_redirects:
            raise EndpointRejected("redirects must not be followed on the live endpoint")
        return self.base_url
