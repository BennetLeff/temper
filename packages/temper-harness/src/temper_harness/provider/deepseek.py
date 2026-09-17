"""The DeepSeek wire format. The only module that knows it.

Every shape here was read off a captured byte rather than a document, and three
of the shapes are not what a reasonable person would have guessed:

* ``usage`` carries ``reasoning_tokens`` one level down, inside
  ``completion_tokens_details``, and that number is a *subset* of
  ``completion_tokens`` rather than an addition to it.
* A streamed response puts the complete usage block on its **final** chunk, next
  to the finish reason, and terminates with an SSE ``data: [DONE]`` record. Nothing
  is accumulated across chunks.
* Tool-call fragments arrive character by character, and a continuation fragment
  carries only ``index`` and ``arguments`` -- no id, no name, no type. The first
  fragment for an index announces them.

The adapter's job is to turn bytes into the committed envelope and nothing more.
It does not retry, does not interpret a failure as a model outcome, and does not
normalize an absent field into a zero (R4).

Two guards live here rather than in a caller, because they are the two ways this
layer could silently do the wrong thing:

* provenance is asserted, not accepted -- a live transport refuses to stamp a row
  ``replay`` and a replay transport refuses to stamp one ``live``, so no caller can
  make recorded bytes look like measured spend (R15);
* every exception on the send path is classified via :func:`classify_exception`,
  so nothing propagates raw (R6).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any

import requests

from temper_harness.provider.errors import (
    CredentialMissing,
    EndpointRejected,
    IncompleteStream,
    MalformedResponse,
    MalformedStream,
    classify_exception,
    classify_http_response,
)
from temper_harness.provider.interface import (
    OFFICIAL_HOST,
    EndpointPolicy,
    Event,
    ReasoningDelta,
    Request,
    StreamEnd,
    Terminal,
    TextDelta,
    ToolCallDelta,
    UsageReported,
)
from temper_harness.provider.messages import build_wire_request
from temper_harness.provider.usage import normalize_usage
from temper_harness.store.recorder import RecordingStore
from temper_harness.store.recordings import canonical_request_bytes

PROVIDER = "deepseek"

#: The model this harness targets. NOT ``deepseek-v4.1-flash``: that id belongs to
#: a different provider's catalogue and the official API rejects it, naming
#: ``deepseek-flash`` and ``deepseek-v4-pro`` in the refusal. Pinned once, here.
MODEL = "deepseek-flash"
ALTERNATE_MODEL = "deepseek-v4-pro"

#: Where the credential is read from. Never a file in the repository (R11).
API_KEY_ENV = "DEEPSEEK_API_KEY"

COMPLETIONS_PATH = "/chat/completions"
PROVIDER_MODELS_PATH = "/models"

#: The SSE sentinel that ends a streamed response. An OpenAI-compatible
#: convention, and the only indication that a stream finished deliberately.
DONE_SENTINEL = b"[DONE]"

_EVENT_STREAM_CONTENT_TYPE = "text/event-stream"


# -- the request -------------------------------------------------------------


def wire_body(request: Request) -> dict[str, Any]:
    """The request body as we send it, validated before anything is sent (R7).

    ``build_wire_request`` runs the message-array checks, so a malformed array
    raises locally instead of becoming a provider 400 -- which the captures show
    is exactly what the provider returns for one, and which a classifier could
    easily misread as a model failure.
    """
    body = build_wire_request(
        model=request.model,
        messages=request.messages,
        tools=list(request.tools) or None,
        temperature=request.temperature,
    )
    if request.stream:
        body["stream"] = True
    return body


# -- decoding ----------------------------------------------------------------


def iter_sse_payloads(lines: Iterable[bytes]) -> Iterator[bytes]:
    """Yield each SSE event's data payload from raw lines.

    Written against the SSE specification rather than against this provider's
    current behaviour, because the failure mode of a too-narrow parser is a
    silently truncated turn: multi-line ``data:`` fields are joined with a
    newline, comments and other field names are ignored, and a payload with no
    terminating blank line still yields rather than being dropped.

    Nothing here assumes the payload is JSON, so a non-JSON body becomes a
    malformed-stream error at the point of parsing rather than a decode error in
    the transport.
    """
    buffer = b""
    for raw_line in lines:
        line = raw_line.rstrip(b"\r")
        if not line:
            if buffer:
                yield buffer
                buffer = b""
            continue
        if line.startswith(b":"):
            continue  # a comment; some proxies use these as heartbeats
        if line.startswith(b"data:"):
            value = line[len(b"data:") :]
            if value.startswith(b" "):
                value = value[1:]
            buffer = value if not buffer else buffer + b"\n" + value
    if buffer:
        yield buffer


def _tool_calls_of(message: Mapping[str, Any]) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []
    for position, raw in enumerate(message.get("tool_calls") or ()):
        function = raw.get("function") or {}
        call_id = raw.get("id")
        if not isinstance(call_id, str) or not call_id:
            raise MalformedResponse(
                f"tool call {position} carries no id; the envelope requires one and "
                "an id-less call cannot be answered"
            )
        calls.append(
            {
                "id": call_id,
                "index": int(raw.get("index", position)),
                "name": str(function.get("name", "")),
                "arguments": str(function.get("arguments", "")),
            }
        )
    return calls


def decode_completion(body: bytes, *, served_from: str) -> dict[str, Any]:
    """Decode a non-streaming body into the committed envelope."""
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise MalformedResponse(f"a 200 response body is not JSON: {err}") from err
    if not isinstance(payload, Mapping):
        raise MalformedResponse(
            f"a 200 response body is not a JSON object: {type(payload).__name__}"
        )

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise MalformedResponse("a 200 response body carries no choices")
    choice = choices[0]
    message = choice.get("message") if isinstance(choice, Mapping) else None
    if not isinstance(message, Mapping):
        raise MalformedResponse("a 200 response body's first choice carries no message")

    raw_usage = payload.get("usage")
    return {
        "id": str(payload.get("id", "")),
        "model": str(payload.get("model", "")),
        "finish_reason": choice.get("finish_reason"),
        "content": message.get("content"),
        "reasoning_content": message.get("reasoning_content"),
        "system_fingerprint": payload.get("system_fingerprint"),
        "tool_calls": _tool_calls_of(message),
        # An absent usage block stays `None`, which is not the same fact as a
        # block whose fields are null: the first says the provider reported
        # nothing, the second that it reported a shape with gaps. The ledger's
        # `usage_source` distinguishes them, and collapsing them here would make
        # that distinction unavailable downstream.
        "usage": normalize_usage(raw_usage) if raw_usage is not None else None,
        "served_from": served_from,
    }


def decode_stream_payloads(payloads: Iterable[bytes], *, served_from: str) -> Iterator[Event]:
    """Turn SSE data payloads into events, ending with a :class:`StreamEnd`.

    Yields deltas rather than an assembled turn, because that is what a stream
    is; :class:`~temper_harness.provider.interface.BufferedTransport` turns the
    deltas into a single terminal envelope for a caller that does not want them.
    """
    message_id = ""
    model = ""
    system_fingerprint: str | None = None
    finish_reason: str | None = None
    saw_sentinel = False

    for payload in payloads:
        if payload.strip() == DONE_SENTINEL:
            saw_sentinel = True
            continue
        try:
            chunk = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise MalformedStream(f"a stream chunk is not JSON: {err}") from err
        if not isinstance(chunk, Mapping):
            raise MalformedStream("a stream chunk is not a JSON object")

        message_id = str(chunk.get("id", message_id))
        model = str(chunk.get("model", model))
        if chunk.get("system_fingerprint") is not None:
            system_fingerprint = str(chunk["system_fingerprint"])

        choices = chunk.get("choices")
        if not isinstance(choices, list) or not choices:
            raise MalformedStream("a stream chunk carries no choices")
        choice = choices[0]
        delta = choice.get("delta") if isinstance(choice, Mapping) else None
        if not isinstance(delta, Mapping):
            raise MalformedStream("a stream chunk's first choice carries no delta")

        # `null` means "no delta for this field", which is not an empty string. The
        # captured stream uses `null` for whichever of content/reasoning_content
        # is not being emitted this chunk, and a decoder that treated null as ""
        # would be harmless here but wrong for any field where it is not.
        content = delta.get("content")
        if isinstance(content, str) and content:
            yield TextDelta(content)
        reasoning = delta.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning:
            yield ReasoningDelta(reasoning)

        for raw in delta.get("tool_calls") or ():
            if not isinstance(raw, Mapping):
                raise MalformedStream("a tool call fragment is not a JSON object")
            index = raw.get("index")
            if not isinstance(index, int):
                raise MalformedStream("a tool call fragment carries no integer index")
            function = raw.get("function") or {}
            call_id = raw.get("id")
            yield ToolCallDelta(
                index=index,
                id=call_id if isinstance(call_id, str) else None,
                name=function.get("name") if isinstance(function.get("name"), str) else None,
                arguments=str(function.get("arguments") or ""),
            )

        if choice.get("finish_reason") is not None:
            finish_reason = str(choice["finish_reason"])

        if chunk.get("usage") is not None:
            usage = normalize_usage(chunk["usage"])
            if any(value is not None for value in usage.values()):
                yield UsageReported(usage)

    # A stream that ends without a finish reason is truncated: the connection
    # dropped, or a proxy cut it. This must be an error rather than an empty turn,
    # because an empty turn is a successful stop with no content and a truncated
    # stream is a failure -- and the difference is invisible in the bytes without
    # the finish reason. The sentinel is corroborating, not decisive: a provider
    # that stopped emitting it would otherwise make every call look truncated.
    if finish_reason is None and not saw_sentinel:
        raise IncompleteStream(
            "the stream ended without a finish reason or a [DONE] sentinel; "
            "the turn is truncated, not empty"
        )

    yield StreamEnd(
        id=message_id,
        model=model,
        finish_reason=finish_reason,
        system_fingerprint=system_fingerprint,
    )


def is_event_stream(content_type: str | None) -> bool:
    return bool(content_type) and _EVENT_STREAM_CONTENT_TYPE in (content_type or "").lower()


class _ByteLineReader:
    """Split a byte-chunk stream into lines while retaining every byte.

    Two jobs that have to happen together. The raw bytes are kept because R8
    requires a recording to hold the provider's payload, and the events are a lossy
    projection of it. The line splitting happens on bytes rather than on decoded
    text because a chunk boundary can fall inside a multi-byte character -- and for
    this provider, whose tool-call arguments arrive one character at a time, that
    is the ordinary case rather than a rare one.
    """

    def __init__(self) -> None:
        self._raw = bytearray()
        self._pending = b""

    @property
    def raw(self) -> bytes:
        return bytes(self._raw)

    def lines(self, chunks: Iterable[bytes]) -> Iterator[bytes]:
        for chunk in chunks:
            self._raw.extend(chunk)
            self._pending += chunk
            while True:
                index = self._pending.find(b"\n")
                if index < 0:
                    break
                yield self._pending[:index]
                self._pending = self._pending[index + 1 :]
        if self._pending:
            yield self._pending
            self._pending = b""


# -- the live adapter --------------------------------------------------------


class LiveTransport:
    """The only adapter that touches the network.

    Pinned at construction: a host override, a non-HTTPS scheme, or a policy that
    would follow redirects all raise :class:`EndpointRejected` before a single
    byte can be sent (R16). A followed redirect is enough to hand both the
    credential and the board content to a host the design never agreed to talk to.
    """

    def __init__(
        self,
        *,
        api_key: str | None,
        policy: EndpointPolicy | None = None,
        timeout: float = 120.0,
        post: Callable[..., Any] | None = None,
        store: RecordingStore | None = None,
    ) -> None:
        self._policy = policy or EndpointPolicy()
        self._endpoint = f"{self._policy.validate()}{COMPLETIONS_PATH}"
        self._api_key = api_key or ""
        self._timeout = timeout
        # Injectable only so a test can drive the adapter from captured bytes. The
        # default is the real client, and nothing else in this module branches on
        # which one it got.
        self._post = post or requests.post
        # Recording is the adapter's job because the adapter is where the bytes
        # are: a caller sees a typed view, and R8 requires the lossless payload be
        # retained. `store=None` is the no-capture case, not a degraded one.
        self._store = store
        self._cancelled = False

    # -- admission -------------------------------------------------------

    def _admit(self) -> None:
        """The one admission predicate S0 ships, and deliberately the only one.

        A private method rather than an injectable policy object: there is exactly
        one rule, and a seam with one implementation is a guess about the shape of
        the second. S3 introduces the interface when it has a second.

        A missing credential is a typed refusal rather than an unauthenticated
        request, because that request would come back 401 and be recorded as a
        provider rejection of a request we should never have made.
        """
        if not self._api_key.strip():
            raise CredentialMissing(
                f"no credential is configured; set {API_KEY_ENV} before issuing a live call"
            )

    def _require_provenance(self, served_from: str) -> None:
        if served_from != "live":
            raise ValueError(
                f"a live transport records served_from='live', not {served_from!r}; "
                "provenance is not the caller's to choose (R15)"
            )

    # -- transport -------------------------------------------------------

    def cancel(self) -> None:
        """Ask the in-flight stream to stop at its next chunk.

        Cooperative, and deliberately so: the generator owning the HTTP response
        is what closes it, and closing a response out from under a reader is how a
        partial chunk gets parsed as a whole one.
        """
        self._cancelled = True

    def stream(self, request: Request) -> Iterator[Event]:
        self._admit()
        self._require_provenance(request.served_from)
        self._cancelled = False

        body = wire_body(request)
        try:
            response = self._post(
                self._endpoint,
                data=canonical_request_bytes(body),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                allow_redirects=False,
                timeout=self._timeout,
                stream=True,
            )
        except BaseException as err:  # noqa: BLE001 - classified, never propagated raw
            raise classify_exception(err) from err

        try:
            if 300 <= response.status_code < 400:
                raise EndpointRejected(
                    f"the provider answered {response.status_code} for a redirect to "
                    f"{response.headers.get('location')!r}; refusing to follow (R16)",
                    http_status=response.status_code,
                )
            if response.status_code >= 300:
                raise classify_http_response(response.status_code, response.content)

            content_type = response.headers.get("content-type")
            if request.stream:
                if not is_event_stream(content_type):
                    raise MalformedResponse(
                        f"asked for a stream and received {content_type!r}; "
                        "a body we cannot parse as events would otherwise look like a turn"
                    )
                reader = _ByteLineReader()
                payloads = iter_sse_payloads(reader.lines(response.iter_content(chunk_size=None)))
                for event in decode_stream_payloads(payloads, served_from=request.served_from):
                    if self._cancelled:
                        # A cancelled stream is not recorded: the bytes are a
                        # fragment, and a corpus entry that replays as a truncated
                        # turn is worse than no entry. The ledger row the caller
                        # writes is where a cancellation is accounted for.
                        return
                    yield event
                self._record(body, reader.raw, response)
                return

            if is_event_stream(content_type):
                raise MalformedResponse(
                    f"asked for a single response and received {content_type!r}"
                )
            payload = response.content
            envelope = decode_completion(payload, served_from=request.served_from)
            # Recorded before the caller sees the turn, and deliberately: a live
            # corpus that is silently missing entries is indistinguishable from a
            # complete one, which is the vacuous-scan failure this repo gates
            # against. A store that cannot write should fail the call loudly.
            self._record(body, payload, response)
            yield Terminal(envelope)
        finally:
            response.close()

    def _record(self, body: dict[str, Any], payload: bytes, response: Any) -> None:
        if self._store is None or response.status_code >= 300:
            return
        self._store.record(
            request=body,
            response_raw=payload,
            headers=dict(response.headers),
            provider=PROVIDER,
            model=str(body.get("model", MODEL)),
            http_status=response.status_code,
        )


def fetch_account_models(
    api_key: str, *, timeout: float = 30.0, get: Callable[..., Any] | None = None
) -> list[str]:
    """The model ids this account is served, straight from the provider.

    Used by the probe and the canary to fail loudly when the pinned model id stops
    existing, rather than discovering it as a 400 mid-run.
    """
    http_get = get or requests.get
    response = http_get(
        f"https://{OFFICIAL_HOST}{PROVIDER_MODELS_PATH}",
        headers={"Authorization": f"Bearer {api_key}"},
        allow_redirects=False,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    return sorted(entry["id"] for entry in payload["data"])
