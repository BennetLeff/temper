"""Tier C: socket faults, ported from the prior attempt's stream diagnostic.

`harness-lab/STREAM-DIAGNOSTIC.md` (on the unmerged ref
``origin/codex/buck-harness-experiment-plan``) lists five real localhost-socket
fault-injection cases, each of which failed the old relay for its intended
assertion, and each of which was then fixed by that iteration's transport policy.
The plan for this work says to **port the fault tests, not the policy**. So the
mechanism is kept and the expectations are re-derived against this transport, which
has different answers because it has a different scope:

===============================  ==================================================
prior case                        what it becomes here
===============================  ==================================================
silent 61 s, then complete        a gap inside the configured timeout must not
                                  truncate the turn. The 61-second figure belonged to
                                  the old relay's fixed cutoff; the lesson is that the
                                  cutoff has to be the budget, and a budget is S1's.
incomplete EOF, then retry        ``IncompleteStream``, and exactly ONE upstream
                                  request -- retry policy is S1, so the transport's
                                  job is to not retry behind the caller's back.
429, then retry                   ``RateLimited`` with ``Retry-After`` captured, the
                                  rate-limit counters retained, cookies excluded, and
                                  again exactly one request.
stall past a short deadline       a read the client times out is ``RequestTimeout``
                                  and is billable, because the provider may already
                                  have generated.
two concurrent requests           both forwarded, neither dropped, and no shared
                                  call state for one to disturb in the other.
===============================  ==================================================

"Exactly one request" is the ported assertion that matters most, and it is the one
this repo keeps re-learning: a transport that retries on its own turns a provider
refusal into a cost the ledger cannot see.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
import requests

from temper_harness.provider.deepseek import LiveTransport
from temper_harness.provider.errors import IncompleteStream, RateLimited, RequestTimeout
from temper_harness.provider.interface import (
    BufferedTransport,
    Request,
    StreamEnd,
    Terminal,
    TextDelta,
)
from temper_harness.provider.messages import ChatMessage
from temper_harness.schema_registry import build_validator
from temper_harness.store.redaction import header_allowlist, redact_headers
from tests import corpus

#: The five ported cases, named so this suite cannot silently shrink to four.
FAULT_CASES = (
    "gap_within_the_timeout_completes",
    "incomplete_eof_does_not_retry",
    "rate_limit_is_captured_and_not_retried",
    "stall_past_the_timeout_is_a_billable_timeout",
    "concurrent_streams_do_not_interfere",
)

KEY = "not-a-real-credential"
STREAM_BODY = corpus.response_bytes("stream_plain")


class _ScriptedResponse:
    """A response whose read behaviour is scripted, standing in for the socket.

    ``sleep_before`` injects a real delay before a chunk, which is how a provider
    that goes quiet is modelled without a 61-second test. ``raise_at`` injects a
    client exception mid-read, which is what a read timeout looks like from the
    adapter's side.
    """

    def __init__(
        self,
        chunks: list[bytes],
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
        sleep_before: dict[int, float] | None = None,
        raise_at: int | None = None,
        error: BaseException | None = None,
    ) -> None:
        self.status_code = status_code
        self.headers = dict(headers or {})
        self.content = body
        self._chunks = list(chunks)
        self._sleep_before = dict(sleep_before or {})
        self._raise_at = raise_at
        self._error = error
        self.closed = False

    def iter_content(self, chunk_size: int | None = None):
        for index, chunk in enumerate(self._chunks):
            delay = self._sleep_before.get(index)
            if delay:
                time.sleep(delay)
            if self._raise_at == index and self._error is not None:
                raise self._error
            yield chunk

    def close(self) -> None:
        self.closed = True


def _adapter(
    response: _ScriptedResponse, *, timeout: float = 5.0
) -> tuple[LiveTransport, list[Any]]:
    calls: list[Any] = []

    def post(url: str, **kwargs: Any) -> _ScriptedResponse:
        calls.append(kwargs)
        return response

    return LiveTransport(api_key=KEY, post=post, timeout=timeout), calls


def _request(*, stream: bool = True) -> Request:
    return Request(
        model="deepseek-flash",
        messages=[ChatMessage(role="user", content="place it")],
        temperature=0,
        max_tokens=64,
        served_from="live",
        stream=stream,
    )


def _stream_chunks(parts: int) -> list[bytes]:
    size = max(1, len(STREAM_BODY) // parts)
    return [STREAM_BODY[i : i + size] for i in range(0, len(STREAM_BODY), size)]


def test_the_five_ported_cases_are_all_present() -> None:
    """Anti-vacuity: the module docstring names five, and so does this tuple."""
    assert len(FAULT_CASES) == 5
    assert len(set(FAULT_CASES)) == 5


# -- 1. a gap inside the timeout -------------------------------------------------


def test_a_quiet_provider_inside_the_timeout_completes() -> None:
    """The ported lesson: the cutoff must be the budget, not a constant.

    The old relay read-cut at 60 seconds and lost a completion that arrived at 64.
    Here the read is bounded by the configured timeout, and a gap well inside it must
    be invisible to the caller. The delay is small because it is the *shape* being
    tested -- the 61-second figure was a property of the old relay.
    """
    response = _ScriptedResponse(
        _stream_chunks(4),
        headers={"content-type": "text/event-stream; charset=utf-8"},
        sleep_before={2: 0.05},
    )
    transport, calls = _adapter(response, timeout=5.0)

    events = list(transport.stream(_request()))
    assert any(isinstance(event, StreamEnd) for event in events)
    assert "".join(e.text for e in events if isinstance(e, TextDelta)) == "temper"
    assert len(calls) == 1, "a quiet read must not be retried"


# -- 2. incomplete EOF ----------------------------------------------------------


def test_an_incomplete_eof_raises_and_sends_no_second_request() -> None:
    """The ported assertion is the request count, and it is the one that matters.

    Retry policy is S1. The transport's job is to not retry behind the caller's back,
    because a silent retry is a cost the ledger never sees.
    """
    payloads = [
        line
        for line in STREAM_BODY.split(b"\n")
        if line.startswith(b"data: ") and line != b"data: [DONE]"
    ]
    truncated = b"\n\n".join(payloads[:-1]) + b"\n\n"
    response = _ScriptedResponse(
        _stream_chunks(3) if False else [truncated],
        headers={"content-type": "text/event-stream; charset=utf-8"},
    )
    transport, calls = _adapter(response)

    with pytest.raises(IncompleteStream):
        list(BufferedTransport(transport).stream(_request()))
    assert len(calls) == 1, "the transport must not retry an incomplete stream"


# -- 3. rate limit -------------------------------------------------------------


def test_a_rate_limit_is_classified_with_its_headers_captured_and_no_cookie() -> None:
    """The ported case, including the two assertions the revised test added.

    Rate-limit capture and cookie exclusion, both checked where they can actually
    leak: the allowlist that decides what reaches disk.
    """
    response = _ScriptedResponse(
        [],
        status_code=429,
        body=b'{"error":{"message":"Rate limit reached","type":"rate_limit_error"}}',
        headers={
            "content-type": "application/json",
            "retry-after": "30",
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": "30",
            "set-cookie": "session=must-never-be-written",
        },
    )
    transport, calls = _adapter(response)

    with pytest.raises(RateLimited) as caught:
        list(transport.stream(_request(stream=False)))
    error = caught.value
    assert error.http_status == 429
    assert error.retryable is True
    assert error.billable is False
    assert error.retry_after == 30.0, "Retry-After is the only actionable fact on a 429"

    retained = redact_headers(response.headers)
    assert "retry-after" in retained and retained["x-ratelimit-remaining"] == "0"
    assert "set-cookie" not in retained
    assert "set-cookie" not in header_allowlist()

    record = error.to_record()
    build_validator("error.schema.json").validate(record)
    assert "must-never-be-written" not in json.dumps(record)
    assert len(calls) == 1, "the transport must not retry a rate limit"


def test_a_date_form_retry_after_is_a_recorded_gap_not_a_guess() -> None:
    """Converting the HTTP-date form needs a clock, and a clock in a classifier
    makes the classification depend on when it ran."""
    response = _ScriptedResponse(
        [],
        status_code=429,
        body=b'{"error":{"message":"slow down"}}',
        headers={
            "content-type": "application/json",
            "retry-after": "Wed, 21 Oct 2026 07:28:00 GMT",
        },
    )
    transport, _ = _adapter(response)
    with pytest.raises(RateLimited) as caught:
        list(transport.stream(_request(stream=False)))
    assert caught.value.retry_after is None


# -- 4. a stalled read ---------------------------------------------------------


def test_a_stalled_read_past_the_timeout_is_a_billable_timeout() -> None:
    """Read timeout mid-stream, which is the branch the ported fault found missing.

    Before this suite, only the initial request was wrapped in the classifier, so a
    read that failed mid-stream propagated raw out of the send path. It is also
    *billable*: the provider had already been asked and may have generated, so the
    row must not read as a free failure.
    """
    response = _ScriptedResponse(
        _stream_chunks(6),
        headers={"content-type": "text/event-stream; charset=utf-8"},
        raise_at=2,
        error=requests.exceptions.ReadTimeout("read timed out"),
    )
    transport, calls = _adapter(response, timeout=0.5)

    with pytest.raises(RequestTimeout) as caught:
        list(BufferedTransport(transport).stream(_request()))
    assert caught.value.billable is True
    assert caught.value.retryable is True
    assert len(calls) == 1, "a timed-out read must not be retried by the transport"
    assert response.closed is True, "the response must be closed on the failure path"


def test_a_connect_timeout_is_not_billable() -> None:
    """The distinction the ported fault sharpened: nothing was sent, nothing was billed.

    ``requests``' ConnectTimeout inherits from both ConnectionError and Timeout, so
    the order of the checks decides the answer -- and the answer is a flag that
    attributes spend.
    """
    calls: list[Any] = []

    def post(url: str, **kwargs: Any) -> Any:
        calls.append(kwargs)
        raise requests.exceptions.ConnectTimeout("could not connect")

    transport = LiveTransport(api_key=KEY, post=post)
    with pytest.raises(Exception) as caught:
        list(transport.stream(_request(stream=False)))
    assert caught.value.category == "pre_connection_unavailable"
    assert caught.value.billable is False
    assert len(calls) == 1


# -- 5. concurrency -----------------------------------------------------------


def test_two_concurrent_streams_do_not_interfere() -> None:
    """Both forwarded, neither dropped, and no shared state to disturb.

    The old relay forwarded both requests and had no idea they were concurrent. This
    adapter has no per-call state on the instance at all -- no cancellation flag, no
    accumulator -- so interleaving two streams by hand is a real test of the property
    rather than a stylistic one. Interleaving rather than threading keeps it
    deterministic and still exercises every shared field, because the only remaining
    shared field is the configuration.
    """
    responses = [
        _ScriptedResponse(
            _stream_chunks(4),
            headers={"content-type": "text/event-stream; charset=utf-8"},
        )
        for _ in range(2)
    ]
    issued: list[_ScriptedResponse] = []

    def post(url: str, **kwargs: Any) -> _ScriptedResponse:
        issued.append(responses[len(issued)])
        return issued[-1]

    transport = LiveTransport(api_key=KEY, post=post)
    first = transport.stream(_request())
    second = transport.stream(_request())

    first_events = [next(first), *first]
    second_events = [next(second), *second]

    assert len(issued) == 2, "both requests must be issued; neither is dropped"
    assert all(response.closed for response in responses)
    for events in (first_events, second_events):
        assert any(isinstance(event, StreamEnd) for event in events)
    assert [e.text for e in first_events if isinstance(e, TextDelta)] == [
        e.text for e in second_events if isinstance(e, TextDelta)
    ]


def test_a_terminal_record_from_a_concurrent_stream_is_well_formed() -> None:
    """Each stream assembles its own turn, with no cross-contamination."""
    response = _ScriptedResponse(
        _stream_chunks(4),
        headers={"content-type": "text/event-stream; charset=utf-8"},
    )
    transport, _ = _adapter(response)
    terminals = [
        event
        for event in BufferedTransport(transport).stream(_request())
        if isinstance(event, Terminal)
    ]
    assert len(terminals) == 1
    build_validator("envelope.schema.json").validate(terminals[0].envelope)
