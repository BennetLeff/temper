"""Typed transport errors.

R6 exists so that a transport failure is never recorded as a model failure.
That guarantee is only as good as the taxonomy's coverage: a DNS failure or a
refused connection that matches no case would otherwise surface as "the model
returned nothing", which is the conflation this module prevents. Two rules
follow from it:

* every failure mode on the send path has its own class, including the
  pre-connection ones a timeout check alone does not catch;
* :func:`classify_exception` is the catch-all, so nothing propagates raw.

``billable`` is a *declared default*, not a measurement. The only evidence that
a call was charged is the usage block on its ``call_terminal`` ledger row, and
these flags are pinned from real bytes by U1's capture rather than assumed.
"""

from __future__ import annotations

import json
import socket
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ErrorSpec:
    """The classification of one failure mode."""

    category: str
    retryable: bool
    billable: bool


class TransportError(Exception):
    """Base class for every classified transport failure."""

    spec = ErrorSpec(category="unknown_transport", retryable=True, billable=False)

    #: Usage measured before a failure interrupted the call, attached by the
    #: buffered transport when an inner stream raises. ``None`` means no usage was
    #: observed, which the ledger records as ``usage_source: unknown`` -- never as
    #: a zero (R4). A truncated but billed call needs this: the row must carry what
    #: was actually spent, and discarding the accumulator because the exception
    #: unwound would report a call that cost money as having cost nothing.
    partial_usage: dict[str, int | None] | None = None

    #: ``Retry-After`` from the response, in seconds, when the provider sent one.
    #: Retained because it is the only actionable fact on a 429: S1's backoff policy
    #: can wait the interval the provider asked for instead of guessing, and a
    #: header that is not captured at the moment of the refusal cannot be recovered
    #: afterwards. Ported from the prior attempt's rate-limit diagnostic, which
    #: asserted rate-limit header capture for the same reason.
    retry_after: float | None = None

    def __init__(self, message: str, *, http_status: int | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status

    @property
    def category(self) -> str:
        return self.spec.category

    @property
    def retryable(self) -> bool:
        return self.spec.retryable

    @property
    def billable(self) -> bool:
        return self.spec.billable

    def to_record(self) -> dict[str, Any]:
        """Render this failure as a schema-valid error record."""
        return {
            "category": self.category,
            "retryable": self.retryable,
            "billable": self.billable,
            "message": str(self),
            "http_status": self.http_status,
            "retry_after": self.retry_after,
        }


class PreConnectionUnavailable(TransportError):
    """DNS, connection refused, or TLS failure: no byte ever left the host.

    Kept distinct from ``RequestTimeout`` because it is not a timeout, and a
    network outage that lands in a generic bucket is indistinguishable from the
    model producing nothing.
    """

    spec = ErrorSpec(category="pre_connection_unavailable", retryable=True, billable=False)


class RateLimited(TransportError):
    spec = ErrorSpec(category="rate_limited", retryable=True, billable=False)


class ServerError(TransportError):
    spec = ErrorSpec(category="server_error", retryable=True, billable=False)


class RequestTimeout(TransportError):
    """Billable because the provider may have generated before the socket died."""

    spec = ErrorSpec(category="timeout", retryable=True, billable=True)


class MalformedStream(TransportError):
    spec = ErrorSpec(category="malformed_stream", retryable=True, billable=True)


class IncompleteStream(TransportError):
    """The stream ended without a finish reason; partial usage is real usage."""

    spec = ErrorSpec(category="incomplete_stream", retryable=True, billable=True)


class MalformedResponse(TransportError):
    """A 200 whose body is not the expected shape. Raw bytes are retained."""

    spec = ErrorSpec(category="malformed_response", retryable=True, billable=False)


class ContextLengthExceeded(TransportError):
    spec = ErrorSpec(category="context_length_exceeded", retryable=False, billable=False)


class ToolSchemaRejected(TransportError):
    """Distinct from content filtering and from a rate limit: it is a request defect."""

    spec = ErrorSpec(category="tool_schema_rejected", retryable=False, billable=False)


class ContentFiltered(TransportError):
    spec = ErrorSpec(category="content_filtered", retryable=False, billable=False)


class RequestRejected(TransportError):
    """The provider refused the request itself, and it is not one of the known shapes.

    Added because the captured 400s on this provider are indistinguishable by
    status: a bad model name, a tool result with no matching call, and a dropped
    reasoning field all arrive as ``invalid_request_error`` /
    ``code: invalid_request_error``. Before this class existed a 400 became a
    ``ToolSchemaRejected``, which was wrong for three of those four cases, and
    the only other option -- ``unknown_transport`` -- is retryable, so a
    deterministic request defect would have been retried forever.

    Not retryable, and not billable: the provider rejects before generating.
    """

    spec = ErrorSpec(category="request_rejected", retryable=False, billable=False)


class CredentialMissing(TransportError):
    """No usable credential is configured, so no request was attempted.

    A send-path refusal by *us*, before any I/O, which is why it is a transport
    error with a category rather than a ``ValueError``: R3 requires a ledger row
    for a call that failed before reaching the provider, and R6 requires that
    every send-path failure be classified rather than propagated raw. It is also
    the shape U6 needs -- running the canary without a key must be a typed blocked
    error, not a skip that reports clean.

    ``retryable`` is False because retrying changes nothing; ``billable`` is False
    because nothing was sent.
    """

    spec = ErrorSpec(category="credential_missing", retryable=False, billable=False)


class EndpointRejected(TransportError):
    """A host override, a non-HTTPS scheme, or a redirect (R16)."""

    spec = ErrorSpec(category="endpoint_rejected", retryable=False, billable=False)


class UnknownTransportError(TransportError):
    """An unrecognised failure on the send path."""

    spec = ErrorSpec(category="unknown_transport", retryable=True, billable=False)


def classify_exception(exc: BaseException, *, http_status: int | None = None) -> TransportError:
    """Map any send-path exception onto the taxonomy.

    Returns a :class:`TransportError` rather than raising, so the caller decides
    whether to re-raise or record. Never returns ``None``: an unclassified
    failure is exactly what this function exists to prevent.
    """
    if isinstance(exc, TransportError):
        return exc
    if isinstance(exc, (socket.gaierror, ConnectionRefusedError, ConnectionResetError)):
        return PreConnectionUnavailable(str(exc), http_status=http_status)
    if isinstance(exc, ssl.SSLError):
        return PreConnectionUnavailable(f"TLS failure: {exc}", http_status=http_status)
    if isinstance(exc, TimeoutError):
        return RequestTimeout(str(exc), http_status=http_status)
    if isinstance(exc, OSError):
        return PreConnectionUnavailable(str(exc), http_status=http_status)
    return UnknownTransportError(f"{type(exc).__name__}: {exc}", http_status=http_status)


def for_http_status(status: int, message: str = "") -> TransportError:
    """Map an HTTP status onto the taxonomy on the status alone.

    A 400 maps to :class:`RequestRejected`, not to :class:`ToolSchemaRejected`.
    That is a correction, not a preference: the captured 400s carry the same
    ``type`` and ``code`` for a bad model name, a tool result with no matching
    call, a malformed tool schema, and a dropped reasoning field, so a
    status-only classifier labelled four different defects identically -- and the
    one it labelled them as was wrong three times out of four. Use
    :func:`classify_http_response` when the body is available.
    """
    detail = message or f"HTTP {status}"
    if status == 429:
        return RateLimited(detail, http_status=status)
    # 408 and 504 are timeouts, not server errors, so they are matched before
    # the 5xx branch -- 504 is >= 500 and would otherwise be swallowed by it.
    if status in (408, 504):
        return RequestTimeout(detail, http_status=status)
    if status >= 500:
        return ServerError(detail, http_status=status)
    # 401 and 403 are the provider refusing the request, exactly like a 400. They
    # must not fall through to the unknown catch-all, which is retryable: a wrong
    # key would then be retried forever against a provider that will refuse it
    # identically every time. The status is retained on the record, so a caller
    # that wants to distinguish "your key is wrong" from "your body is wrong" can,
    # without a category per remedy.
    if status in (400, 401, 403):
        return RequestRejected(detail, http_status=status)
    return UnknownTransportError(detail, http_status=status)


#: Message fragments that place a rejected request on a specific category.
#: The two schema markers are VERIFIED against captured 400 bodies. The
#: context-length and content-filter markers are NOT verified on this provider --
#: no probe produced either -- so they are declared as unverified rather than
#: presented as measured, and the plan's unknowns list carries them as such. A
#: category that could never be reached would make the taxonomy a claim rather
#: than a mechanism, so they stay wired even while unproven.
_SCHEMA_REJECTION_MARKERS = (
    "invalid schema for function",
    "is not valid under any of the schemas",
)
_CONTEXT_LENGTH_MARKERS = (
    "maximum context length",
    "context length exceeded",
    "reduce the length of the messages",
)
_CONTENT_FILTER_MARKERS = (
    "content filter",
    "content_filter",
    "content policy",
)


def provider_error_message(body: bytes | str | None) -> str | None:
    """The provider's own message from an error body, if the body has that shape.

    ``{"error": {"message": ..., "type": ..., "code": ...}}`` is the captured
    shape. Returns ``None`` rather than raising when the body is something else:
    a proxy or a load balancer can answer with an HTML page, and that is a
    malformed response, not a crash inside the classifier.
    """
    if body is None:
        return None
    text = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body
    stripped = text.strip()
    if not stripped.startswith("{"):
        return None
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and isinstance(error.get("message"), str):
        message: str = error["message"]
        return message
    return None


def _retry_after_seconds(headers: Mapping[str, Any] | None) -> float | None:
    """``Retry-After`` in seconds, when the provider sent it in that form.

    The header is case-insensitive, so both spellings are looked up. The HTTP-date
    form is deliberately *not* converted: parsing it needs a clock, and a clock
    inside a classifier makes the classification depend on when it ran. A date-form
    value therefore yields ``None``, which is a recorded gap rather than a guess.
    No 429 was ever observed from this provider, so both branches are exercised only
    against synthetic responses -- see the plan's unknowns.
    """
    if not headers:
        return None
    raw = headers.get("retry-after", headers.get("Retry-After"))
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except ValueError:
        return None


def classify_http_response(
    status: int,
    body: bytes | str | None = None,
    headers: Mapping[str, Any] | None = None,
) -> TransportError:
    """Map a non-2xx response onto the taxonomy, using the provider's own message.

    The status narrows the class; the body picks the category inside it. This is
    the entry point the live adapter uses, because the alternative -- classifying a
    400 by its status -- cannot tell a bad model name from a bad tool schema, and
    this repo's own record is that filtering before reading the evidence produces a
    confidently wrong set.

    ``headers`` are the *allowlisted* response headers. They matter for one case: a
    429's ``Retry-After`` is the only actionable fact on a rate-limit response, and
    a header not captured at the moment of the refusal cannot be recovered later.
    """
    message = provider_error_message(body)
    if message is None:
        raw = body.decode("utf-8", errors="replace") if isinstance(body, bytes) else (body or "")
        message = raw.strip()[:400]

    error = for_http_status(status, message)
    if status == 400:
        lowered = message.lower()
        if any(marker in lowered for marker in _SCHEMA_REJECTION_MARKERS):
            error = ToolSchemaRejected(message, http_status=status)
        elif any(marker in lowered for marker in _CONTEXT_LENGTH_MARKERS):
            error = ContextLengthExceeded(message, http_status=status)
        elif any(marker in lowered for marker in _CONTENT_FILTER_MARKERS):
            error = ContentFiltered(message, http_status=status)

    if status == 429:
        error.retry_after = _retry_after_seconds(headers)
    return error
