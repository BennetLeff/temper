"""The live probe: replace every assumption about the provider with captured bytes.

KTD4 makes this unit first rather than an afterthought. Cache fields, whether
reasoning tokens sit inside or beside completion tokens, whether parallel tool
calls are supported, whether strict schemas are accepted, and which stream chunk
carries usage are all unverifiable from documentation for this provider, and
every one of them turned out to need correcting:

* ``deepseek-v4.1-flash`` is not a model this account serves. The provider's own
  400 body names the set -- ``deepseek-flash`` and ``deepseek-v4-pro`` -- which is
  the strongest possible form of the finding: not "the docs say X" but the
  provider refusing the request.
* Reasoning tokens sit *inside* completion tokens. A trivial completion reports
  ``completion_tokens=15`` with ``completion_tokens_details.reasoning_tokens=12``
  and three characters of content, so the two are not additive.
* Usage arrives complete on the final streamed chunk, not fragmented across
  chunks, and the terminal is an OpenAI-style ``data: [DONE]`` sentinel.
* Responses carry ``system_fingerprint``, which identifies the backend build. A
  typed view that dropped it would discard the one field that explains a
  run-to-run behaviour change.
* Absent stream fields are explicit ``null``, and a content delta can be ``""``.
  Neither is the same as "the field was not present".
* A 400 is ``invalid_request_error`` for a bad *model name* as well as for a
  request defect, so classifying by status alone mislabels it.

The probe writes what it received and nothing else. It does not retry, does not
interpret, and does not normalize -- interpretation belongs to the adapter, and
the entire reason to capture first is to have something to interpret against.

Two properties are non-negotiable and are asserted by the suite rather than
trusted: no fixture contains the API key or an ``Authorization`` header (R11),
and every fixture re-verifies against its own recorded hash.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from temper_harness.provider.deepseek import (
    API_KEY_ENV,
    COMPLETIONS_PATH,
    MODEL,
    PROVIDER,
    fetch_account_models,
    wire_body,
)
from temper_harness.provider.interface import OFFICIAL_HOST, Request
from temper_harness.provider.messages import ChatMessage, ToolCall, ToolDefinition
from temper_harness.store.recordings import canonical_request_bytes
from temper_harness.store.redaction import redact_headers


def _request(
    content: str | None = None,
    *,
    messages: list[ChatMessage] | None = None,
    tools: tuple[ToolDefinition, ...] = (),
    stream: bool = False,
    max_tokens: int = 600,
    model: str = MODEL,
    thinking: bool | None = None,
) -> Request:
    """A probe request, built the way the client builds one.

    Deliberately routed through the production types rather than assembled as a
    raw dict: the fixture then holds the body the *client* would send, so its
    recorded hash is a hash a replay can reproduce. A capture that only a
    hand-written serializer can regenerate is not a corpus entry.
    """
    if messages is None:
        assert content is not None
        messages = [ChatMessage(role="user", content=content)]
    return Request(
        model=model,
        messages=messages,
        tools=tools,
        temperature=0,
        max_tokens=max_tokens,
        thinking=thinking,
        served_from="live",
        stream=stream,
    )


#: The tool schema R7 requires be preserved verbatim: an unknown keyword
#: (``$defs``), a ``$ref`` to it, a nested ``oneOf``, an ``enum``, ``required``,
#: and ``additionalProperties: false``. If the client filtered to a known
#: keyword set, the model would be asked to satisfy a schema it never saw.
PLACE_TOOL = ToolDefinition(
    name="place",
    description="Place a component on a copper layer",
    parameters={
        "type": "object",
        "additionalProperties": False,
        "required": ["reference", "layer", "rotation"],
        "properties": {
            "reference": {"type": "string"},
            "layer": {"$ref": "#/$defs/layer"},
            "rotation": {"oneOf": [{"type": "integer", "multipleOf": 90}, {"type": "number"}]},
        },
        "$defs": {"layer": {"type": "string", "enum": ["F.Cu", "B.Cu"]}},
    },
)

CHECK_TOOL = ToolDefinition(
    name="check",
    description="Check a design rule",
    parameters={
        "type": "object",
        "additionalProperties": False,
        "required": ["rule"],
        "properties": {"rule": {"type": "string", "enum": ["clearance", "creepage"]}},
    },
)

TWO_CALLS = (
    "Make exactly two tool calls in this turn: place reference R1 on layer F.Cu "
    "with rotation 0, and check rule clearance. Do not explain."
)


@dataclass(frozen=True, slots=True)
class Probe:
    """One request to issue, and what it exists to reveal.

    ``request`` may be a callable so that a probe can be a genuine continuation of
    an earlier capture rather than a reconstruction of one. That matters for the
    tool round trip: rebuilding the assistant turn by hand would produce a fixture
    that agrees with my assumptions, which is the self-consistency trap. Taking the
    provider's own reasoning and tool_call ids and sending them back through the
    client's own encoder is the only version of that probe worth having.

    ``raw_body`` is the escape hatch, and it exists for exactly one probe. Some of
    what is worth knowing about a provider is what it does with a request this
    client refuses to send: the client validates the message array before any I/O
    (R7), so an orphaned tool result has no client-shaped form to build. Capturing
    the provider's 400 requires going around our own guard, and the fixture is then
    the evidence that the guard is protecting against something real rather than
    something imagined.
    """

    name: str
    reveals: str
    request: Request | Callable[[Mapping[str, CapturedExchange]], Request] | None = None
    raw_body: Mapping[str, Any] | None = None
    expect_status: int = 200

    def __post_init__(self) -> None:
        if (self.request is None) == (self.raw_body is None):
            raise ValueError(f"probe {self.name!r} must define exactly one of request/raw_body")


def _assistant_turn(prior: Mapping[str, CapturedExchange]) -> ChatMessage:
    """The provider's own assistant message, carried into the client's types.

    The provider's message also carries an ``index`` on each tool call, which is a
    response-side field the client's request encoder does not emit. It is dropped
    here rather than smuggled through, so the fixture is the body the client would
    send -- and the fact that the provider accepted it both ways is recorded as an
    observation rather than relied on.
    """
    raw = json.loads(prior["parallel_tools"].body)["choices"][0]["message"]
    return ChatMessage(
        role="assistant",
        content=raw.get("content"),
        reasoning_content=raw.get("reasoning_content"),
        tool_calls=tuple(
            ToolCall(
                id=call["id"],
                name=call["function"]["name"],
                arguments=call["function"]["arguments"],
            )
            for call in raw["tool_calls"]
        ),
    )


def _tool_roundtrip_request(prior: Mapping[str, CapturedExchange]) -> Request:
    """Continue the provider's own tool-call turn, reasoning replayed.

    This is the shape a loop must send. The half that fails without it is
    ``reasoning_omitted`` below.
    """
    assistant = _assistant_turn(prior)
    messages = [
        ChatMessage(role="user", content="Place R1 on F.Cu and check clearance."),
        assistant,
    ]
    messages.extend(
        ChatMessage(role="tool", tool_call_id=call.id, content="done")
        for call in assistant.tool_calls
    )
    return _request(messages=messages, tools=(PLACE_TOOL, CHECK_TOOL), max_tokens=300)


def _reasoning_omitted_request(_: Mapping[str, CapturedExchange]) -> Request:
    """The same turn with ``reasoning_content`` dropped and unrecognized ids.

    Synthetic ids are load-bearing here, and this is the surprising part of the
    finding: with ids the provider generated moments earlier, the identical
    request returns 200, because the provider still recognizes them. With ids it
    has never seen, it returns 400 and demands the reasoning back. Measured at
    5/5 for each, on an otherwise identical body.

    So the rule a client must implement is not "replay reasoning if the provider
    asks" -- it is "always replay reasoning", because whether the provider asks
    depends on server-side state that a client cannot inspect and that a test
    cannot reproduce. Relying on the exemption produces a transport that works in
    a quick test and fails later, which is this repo's definition of correct by
    coincidence.
    """
    calls = (
        ToolCall(
            id="call_probe_00",
            name="place",
            arguments='{"reference": "R1", "layer": "F.Cu", "rotation": 0}',
        ),
        ToolCall(id="call_probe_01", name="check", arguments='{"rule": "clearance"}'),
    )
    messages = [
        ChatMessage(role="user", content="Place R1 on F.Cu and check clearance."),
        ChatMessage(role="assistant", content="", tool_calls=calls),
    ]
    messages.extend(
        ChatMessage(role="tool", tool_call_id=call.id, content="done") for call in calls
    )
    return _request(messages=messages, tools=(PLACE_TOOL, CHECK_TOOL), max_tokens=300)


def _invalid_tool_schema_request(_: Mapping[str, CapturedExchange]) -> Request:
    return _request(
        "Place R1.",
        tools=(
            ToolDefinition(
                name="place",
                description="Place a component",
                parameters={
                    "type": "object",
                    "properties": {"reference": {"type": "not-a-real-type"}},
                },
            ),
        ),
        max_tokens=64,
    )


PROBE_SET: tuple[Probe, ...] = (
    Probe(
        name="plain",
        reveals="the usage block's real field names and nesting, whether reasoning_content is emitted, and the top-level response shape",
        request=_request("Reply with exactly the word: temper", max_tokens=64),
    ),
    Probe(
        name="parallel_tools",
        reveals="whether two tool calls can arrive in one response, with distinct ids and stable ordering, and what an assistant tool-call turn looks like verbatim -- the input to the round-trip probe",
        request=_request(TWO_CALLS, tools=(PLACE_TOOL, CHECK_TOOL)),
    ),
    Probe(
        name="strict_schema",
        reveals="whether a tool schema carrying $defs, a $ref, a nested oneOf, and additionalProperties:false is accepted rather than rejected or rewritten",
        request=_request(
            "Place reference C6 on layer B.Cu at rotation 90. Use the tool.",
            tools=(PLACE_TOOL,),
        ),
    ),
    Probe(
        name="stream_plain",
        reveals="the SSE framing, which chunk carries usage, whether usage is fragmented, and the terminal sentinel",
        request=_request("Reply with exactly the word: temper", stream=True, max_tokens=64),
    ),
    Probe(
        name="stream_tools",
        reveals="how tool_calls fragment across chunks -- whether the id repeats on every fragment or appears once, and how arguments split",
        request=_request(TWO_CALLS, tools=(PLACE_TOOL, CHECK_TOOL), stream=True),
    ),
    Probe(
        name="tool_roundtrip",
        reveals="that a continued tool turn is accepted when the assistant message is replayed through the client's own encoder, reasoning_content included",
        request=_tool_roundtrip_request,
    ),
    Probe(
        name="reasoning_omitted",
        reveals="that the identical turn is refused when reasoning_content is dropped and the tool_call ids are ones the provider has not seen, so reasoning must always be replayed rather than re-requested",
        request=_reasoning_omitted_request,
        expect_status=400,
    ),
    Probe(
        name="thinking_disabled",
        reveals="the shape of a non-thinking response: whether reasoning_content is absent or explicit null, whether completion_tokens_details exists at all, and that prompt_tokens falls because thinking mode injects hidden prompt overhead",
        request=_request("Reply with exactly the word: temper", thinking=False, max_tokens=64),
    ),
    Probe(
        name="max_tokens_out_of_range",
        reveals="the measured max_tokens ceiling. The model page states 384K; the error names the exact range, which is a measurement rather than a transcription, and it tells a caller what to clamp to",
        request=_request("hi", max_tokens=99_999_999),
        expect_status=400,
    ),
    Probe(
        name="orphan_tool_result",
        reveals="what the provider does with a tool result whose id matches no assistant tool call -- the local check in R7 exists so this never leaves the client, and this is the error it prevents",
        # The only probe that goes around the client's encoder, because the client
        # refuses to produce this body at all (R7). Capturing the provider's 400 is
        # what shows the local guard is protecting against something real.
        raw_body={
            "model": MODEL,
            "messages": [
                {"role": "user", "content": "Place R1 on F.Cu."},
                {
                    "role": "tool",
                    "tool_call_id": "call_that_never_happened",
                    "content": "placed",
                },
            ],
            "max_tokens": 64,
            "temperature": 0,
        },
        expect_status=400,
    ),
    Probe(
        name="invalid_model",
        reveals="that the plan's model id is wrong, by capturing the provider naming the ids it does serve",
        request=_request("hello", max_tokens=64, model="deepseek-v4.1-flash"),
        expect_status=400,
    ),
    Probe(
        name="invalid_tool_schema",
        reveals="that the provider validates a tool schema server-side, so a malformed schema is a request defect the provider reports rather than something only the model can discover",
        request=_invalid_tool_schema_request,
        expect_status=400,
    ),
)


@dataclass(frozen=True, slots=True)
class CapturedExchange:
    """One probe's request and the bytes that came back."""

    name: str
    reveals: str
    request: dict[str, Any]
    request_hash: str
    stream: bool
    expect_status: int
    http_status: int
    headers: dict[str, str]
    body: bytes

    @property
    def response_suffix(self) -> str:
        return "sse" if self.stream else "json"

    @property
    def status_as_expected(self) -> bool:
        """Whether the provider still answers this probe the way it did before.

        Recorded rather than enforced: a changed status is evidence about the
        provider, and the capture is worth keeping either way. The suite asserts
        it, so drift is loud instead of absorbed.
        """
        return self.http_status == self.expect_status


def request_hash_of(body_bytes: bytes) -> str:
    """sha256 of the bytes actually sent.

    Hashed over the wire bytes rather than the dict, so the manifest records the
    identity of what was on the wire. A test asserts it equals what the store's
    canonical encoder derives from the same body, which is the check that the
    probe and the client agree about what "the same request" means.
    """
    return hashlib.sha256(body_bytes).hexdigest()


def _exchange_filenames(exchange: CapturedExchange) -> dict[str, str]:
    base = exchange.name
    return {
        "request": f"{base}.request.json",
        "response": f"{base}.response.{exchange.response_suffix}",
        "meta": f"{base}.meta.json",
    }


def render_fixture_files(exchange: CapturedExchange, *, captured_at: str) -> dict[str, bytes]:
    """Render one capture to the committed file set, without touching disk.

    Pure so the layout and the redaction can be asserted in a test with no
    network, and so a fixture can be regenerated and compared rather than
    assumed. The response body is written verbatim, as its own file: it is the
    primary evidence, and a diff should show the provider's own bytes.
    """
    names = _exchange_filenames(exchange)
    meta = {
        "name": exchange.name,
        "reveals": exchange.reveals,
        "provider": PROVIDER,
        "model": MODEL,
        "stream": exchange.stream,
        "http_status": exchange.http_status,
        "expect_status": exchange.expect_status,
        "status_as_expected": exchange.status_as_expected,
        "request_hash": exchange.request_hash,
        "response_sha256": hashlib.sha256(exchange.body).hexdigest(),
        "response_bytes": len(exchange.body),
        "headers": dict(sorted(exchange.headers.items())),
        "captured_at": captured_at,
    }
    return {
        names["request"]: json.dumps(
            exchange.request, sort_keys=True, indent=2, ensure_ascii=False
        ).encode("utf-8")
        + b"\n",
        names["response"]: exchange.body,
        names["meta"]: json.dumps(meta, sort_keys=True, indent=2, ensure_ascii=False).encode(
            "utf-8"
        )
        + b"\n",
    }


def _endpoint() -> str:
    return f"https://{OFFICIAL_HOST}{COMPLETIONS_PATH}"


def _post(body_bytes: bytes, api_key: str, *, timeout: float) -> tuple[int, dict[str, str], bytes]:
    """Issue one request and return status, allowlisted headers, and raw bytes.

    Redirects are refused rather than followed (R16): a followed redirect is
    enough to send both the key and the board content to a host the design never
    agreed to talk to.
    """
    response = requests.post(
        _endpoint(),
        data=body_bytes,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        allow_redirects=False,
        timeout=timeout,
    )
    if 300 <= response.status_code < 400:
        raise requests.RequestException(
            f"the provider redirected to {response.headers.get('location')!r}; refusing to follow (R16)"
        )
    return response.status_code, redact_headers(response.headers), response.content


def list_account_models(api_key: str, *, timeout: float = 30.0) -> list[str]:
    """The model ids this account is served. Thin alias for the adapter's reader.

    Kept as a name because the probe's manifest records what it returned, and the
    probe is not the place to reimplement an HTTP call the adapter already makes.
    """
    return fetch_account_models(api_key, timeout=timeout)


def run_probe_set(api_key: str, *, timeout: float = 120.0) -> list[CapturedExchange]:
    """Issue every probe, in order, and return what came back. Writes nothing.

    Each probe's body is built by the client's own encoder and serialized once, and
    both sent and hashed. That is what makes a capture a corpus entry: the bytes on
    the wire are the bytes the client would produce, so the recorded hash is one a
    replay can reproduce.

    Probes run in declaration order and a callable request receives the captures so
    far, which is what lets a later probe continue an earlier one instead of
    reconstructing it.
    """
    captures: list[CapturedExchange] = []
    by_name: dict[str, CapturedExchange] = {}
    for probe in PROBE_SET:
        if probe.raw_body is not None:
            body = dict(probe.raw_body)
        else:
            source = probe.request
            resolved = source(by_name) if callable(source) else source
            assert isinstance(resolved, Request)
            body = wire_body(resolved)
        body_bytes = canonical_request_bytes(body)
        status, headers, payload = _post(body_bytes, api_key, timeout=timeout)
        exchange = CapturedExchange(
            name=probe.name,
            reveals=probe.reveals,
            request=body,
            request_hash=request_hash_of(body_bytes),
            stream=bool(body.get("stream", False)),
            expect_status=probe.expect_status,
            http_status=status,
            headers=headers,
            body=payload,
        )
        captures.append(exchange)
        by_name[probe.name] = exchange
    return captures


def write_fixtures(
    captures: list[CapturedExchange],
    out_dir: Path,
    *,
    models: list[str],
    captured_at: str,
    harness_commit: str,
    harness_dirty: bool,
) -> list[Path]:
    """Write the capture set and its manifest; return the files written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    manifest_entries: list[dict[str, Any]] = []

    for exchange in captures:
        files = render_fixture_files(exchange, captured_at=captured_at)
        for name, payload in sorted(files.items()):
            path = out_dir / name
            path.write_bytes(payload)
            written.append(path)
        manifest_entries.append(
            {
                "name": exchange.name,
                "reveals": exchange.reveals,
                "stream": exchange.stream,
                "http_status": exchange.http_status,
                "expect_status": exchange.expect_status,
                "status_as_expected": exchange.status_as_expected,
                "request_hash": exchange.request_hash,
                "response_sha256": hashlib.sha256(exchange.body).hexdigest(),
                "files": dict(sorted(_exchange_filenames(exchange).items())),
            }
        )

    manifest = {
        "schema_version": "1.0",
        "provider": PROVIDER,
        "model": MODEL,
        "endpoint_host": OFFICIAL_HOST,
        "account_models": models,
        "captured_at": captured_at,
        "harness_commit": harness_commit,
        # Recorded, not refused: a dirty capture is still evidence, and the field is what
        # lets a reader tell a reproducible corpus from an anecdote.
        "harness_dirty": harness_dirty,
        "probes": manifest_entries,
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    written.append(manifest_path)
    return written


def _harness_state() -> tuple[str, bool]:
    """HEAD, and whether the tree was clean, for the capture manifest.

    Both, because a commit alone is not provenance. The first version of this recorded only
    HEAD, and the committed manifest consequently names a commit that *cannot* reproduce it:
    the twelve-probe corpus was captured from a dirty tree whose probe code was committed
    later, so checking out the named commit yields a ten-probe corpus. Nothing in the file
    said so. The canary's evidence had the same problem and gained a dirty flag for it; the
    corpus -- which the whole fidelity oracle rests on -- had not.

    Best-effort and declared as such: an honest ``UNKNOWN`` is recorded rather than a
    fabricated sha.
    """
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return "UNKNOWN", True
    return (commit or "UNKNOWN"), bool(status.strip())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="temper_harness.provider.probe", description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="fixture directory to write")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args(argv)

    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        # R12/U6: a missing key is a typed failure, never a skip that reports
        # clean. A probe that silently did nothing would leave the corpus empty
        # and the suite green over it.
        print(
            f"BLOCKED: {API_KEY_ENV} is not set. The probe needs a provisioned key; "
            "it will not substitute a hand-written fixture.",
            file=sys.stderr,
        )
        return 2

    models = list_account_models(api_key)
    print(f"account serves: {', '.join(models)}", file=sys.stderr)
    if MODEL not in models:
        print(
            f"BLOCKED: {MODEL!r} is not served by this account ({models}); "
            "refusing to probe against a model that does not exist.",
            file=sys.stderr,
        )
        return 3

    captures = run_probe_set(api_key, timeout=args.timeout)
    unexpected = 0
    for exchange in captures:
        flag = "" if exchange.status_as_expected else f"  <-- EXPECTED {exchange.expect_status}"
        unexpected += 0 if exchange.status_as_expected else 1
        print(
            f"  {exchange.name:<20} status={exchange.http_status} bytes={len(exchange.body)}{flag}",
            file=sys.stderr,
        )
    if unexpected:
        print(
            f"WARNING: {unexpected} probe(s) answered with an unexpected status. "
            "The captures are still written, because a changed answer is evidence "
            "about the provider, but the suite asserts this so it cannot pass silently.",
            file=sys.stderr,
        )
    harness_commit, harness_dirty = _harness_state()
    written = write_fixtures(
        captures,
        args.out,
        models=models,
        captured_at=dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat(),
        harness_commit=harness_commit,
        harness_dirty=harness_dirty,
    )
    print(f"wrote {len(written)} file(s) under {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
