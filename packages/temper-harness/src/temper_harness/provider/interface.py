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
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse

from temper_harness.provider.errors import EndpointRejected, MalformedStream
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
class Terminal:
    """The single terminal event a buffered transport yields."""

    envelope: dict[str, Any]

    @property
    def finish_reason(self) -> str | None:
        return self.envelope.get("finish_reason")


Event = TextDelta | ReasoningDelta | ToolCallDelta | UsageReported | Terminal


# -- request -----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Request:
    model: str
    messages: list[ChatMessage]
    tools: tuple[ToolDefinition, ...] = field(default=())
    temperature: float | None = None
    served_from: str = "live"


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
    """What every provider adapter provides. There are exactly two: live, replay."""

    def stream(self, request: Request) -> Iterator[Event]: ...

    def cancel(self) -> None: ...


class BufferedTransport:
    """Adapt a streaming transport to one terminal event.

    The S0 default. It consumes the inner stream fully, so any inner error
    surfaces before a caller sees a partial turn it might act on.
    """

    def __init__(self, inner: Transport) -> None:
        self._inner = inner
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        self._inner.cancel()

    def stream(self, request: Request) -> Iterator[Event]:
        text: list[str] = []
        reasoning: list[str] = []
        deltas: list[ToolCallDelta] = []
        usage: dict[str, int | None] | None = None
        finish_reason: str | None = None
        message_id = ""
        model = request.model
        system_fingerprint: str | None = None

        for event in self._inner.stream(request):
            if self._cancelled:
                break
            if isinstance(event, TextDelta):
                text.append(event.text)
            elif isinstance(event, ReasoningDelta):
                reasoning.append(event.text)
            elif isinstance(event, ToolCallDelta):
                deltas.append(event)
            elif isinstance(event, UsageReported):
                usage = event.usage
            elif isinstance(event, Terminal):
                terminal_envelope = event.envelope
                finish_reason = terminal_envelope.get("finish_reason")
                message_id = str(terminal_envelope.get("id", ""))
                model = str(terminal_envelope.get("model", model))
                system_fingerprint = terminal_envelope.get("system_fingerprint")
                if usage is None:
                    usage = terminal_envelope.get("usage")

        calls = reassemble_tool_calls(deltas)
        validate_tool_arguments(calls)

        # Empty accumulation stays "" rather than becoming None. Captured
        # evidence: a tool-call turn reports content as an empty STRING, with no
        # content deltas at all in the streamed form. Collapsing the two would
        # make the streaming and non-streaming paths disagree about the same
        # turn, and the loop must not be able to tell which path it used. `null`
        # still means what the provider means by it -- the field was absent from
        # the response -- and that is decided by the decoder, not here.
        envelope: dict[str, Any] = {
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
            "served_from": request.served_from,
        }
        yield Terminal(envelope)


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
