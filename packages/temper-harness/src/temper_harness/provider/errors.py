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

import socket
import ssl
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
    """Map an HTTP status onto the taxonomy."""
    detail = message or f"HTTP {status}"
    if status == 429:
        return RateLimited(detail, http_status=status)
    # 408 and 504 are timeouts, not server errors, so they are matched before
    # the 5xx branch -- 504 is >= 500 and would otherwise be swallowed by it.
    if status in (408, 504):
        return RequestTimeout(detail, http_status=status)
    if status >= 500:
        return ServerError(detail, http_status=status)
    if status == 400:
        return ToolSchemaRejected(detail, http_status=status)
    return UnknownTransportError(detail, http_status=status)
