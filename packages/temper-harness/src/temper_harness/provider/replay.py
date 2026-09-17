"""The replay adapter: the same decoder, fed from a recording instead of a socket.

Holding only a store. There is no HTTP client in this module, no reference to a
live transport, and nothing that could open a socket -- the offline property is
structural rather than a flag a caller has to remember to set, which is the whole
reason R9 asks for two explicit modes rather than one mode with a switch.

Replay is the live path with its bytes substituted, deliberately: the two
adapters share :func:`~temper_harness.provider.deepseek.decode_completion`,
:func:`~temper_harness.provider.deepseek.iter_sse_payloads`, and
:func:`~temper_harness.provider.deepseek.decode_stream_payloads`. If replay used
its own parser, a passing recorded test would say nothing about the live path --
and this repo has already paid for that lesson twice, with a Rust/Python pair that
agreed bit-for-bit while both were wrong.
"""

from __future__ import annotations

from collections.abc import Iterator

from temper_harness.provider.deepseek import (
    decode_completion,
    decode_stream_payloads,
    is_event_stream,
    iter_sse_payloads,
    wire_body,
)
from temper_harness.provider.errors import MalformedResponse, classify_http_response
from temper_harness.provider.interface import Event, Request, Terminal
from temper_harness.store.recorder import RecordingStore


class ReplayTransport:
    """Serves a recorded exchange through the live path's decoder."""

    def __init__(self, store: RecordingStore) -> None:
        self._store = store
        self._cancelled = False

    def cancel(self) -> None:
        """Replay is already over by the time a caller could cancel it.

        Present so the adapter satisfies the transport protocol and so that a
        caller written against the live path works unchanged. Deliberately not a
        no-op-with-a-side-effect: there is no network read to interrupt.
        """
        self._cancelled = True

    def _require_provenance(self, served_from: str) -> None:
        if served_from != "replay":
            raise ValueError(
                f"a replay transport records served_from='replay', not {served_from!r}; "
                "a recorded turn summed into a scored aggregate is exactly what R15 "
                "fails closed on, so the provenance is not the caller's to choose"
            )

    def stream(self, request: Request) -> Iterator[Event]:
        self._require_provenance(request.served_from)
        self._cancelled = False

        # The request is hashed exactly the way the live path hashes it, because
        # it is the same function: `serve` refuses on a mismatch rather than
        # serving a near miss, and that only works if both sides agree on what
        # "the same request" means.
        recording = self._store.serve(wire_body(request))

        if recording.http_status >= 300:
            raise classify_http_response(recording.http_status, recording.response_raw)

        content_type = recording.headers.get("content-type")
        payload = recording.response_raw

        if request.stream:
            if not is_event_stream(content_type):
                raise MalformedResponse(
                    f"asked to replay a stream and the recording is {content_type!r}"
                )
            for event in decode_stream_payloads(
                iter_sse_payloads(payload.split(b"\n")), served_from="replay"
            ):
                if self._cancelled:
                    return
                yield event
            return

        if is_event_stream(content_type):
            raise MalformedResponse(
                f"asked to replay a single response and the recording is {content_type!r}"
            )
        yield Terminal(decode_completion(payload, served_from="replay"))
