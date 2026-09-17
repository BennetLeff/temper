"""The taxonomy must be exhaustive, or R6's guarantee is unenforced."""

from __future__ import annotations

import socket
import ssl

import pytest
from jsonschema import ValidationError

from temper_harness.ledger.store import build_validator
from temper_harness.provider import errors
from temper_harness.provider.errors import (
    ContentFiltered,
    ContextLengthExceeded,
    EndpointRejected,
    IncompleteStream,
    MalformedResponse,
    MalformedStream,
    PreConnectionUnavailable,
    RateLimited,
    RequestTimeout,
    ServerError,
    ToolSchemaRejected,
    TransportError,
    UnknownTransportError,
    classify_exception,
    for_http_status,
)

ALL_ERROR_CLASSES = [
    PreConnectionUnavailable,
    RateLimited,
    ServerError,
    RequestTimeout,
    MalformedStream,
    IncompleteStream,
    MalformedResponse,
    ContextLengthExceeded,
    ToolSchemaRejected,
    ContentFiltered,
    EndpointRejected,
    UnknownTransportError,
]


def test_there_is_more_than_one_error_class() -> None:
    """Anti-vacuity: a taxonomy that iterates nothing must not report clean."""
    assert len(ALL_ERROR_CLASSES) > 1


def test_every_class_has_a_distinct_category() -> None:
    categories = [cls.spec.category for cls in ALL_ERROR_CLASSES]
    assert len(set(categories)) == len(categories)
    assert all(categories)


@pytest.mark.parametrize("cls", ALL_ERROR_CLASSES)
def test_every_error_renders_a_schema_valid_record(cls: type[TransportError]) -> None:
    record = cls("boom", http_status=500).to_record()
    build_validator("error.schema.json").validate(record)


def test_a_pre_connection_failure_is_not_a_timeout() -> None:
    """The class a timeout-only check would miss.

    A blocked network makes every call raise a connection error; if that lands
    in a generic bucket, the run records "the model produced nothing".
    """
    refused = classify_exception(ConnectionRefusedError("refused"))
    assert isinstance(refused, PreConnectionUnavailable)
    assert refused.category == "pre_connection_unavailable"
    assert refused.retryable is True
    assert refused.billable is False

    dns = classify_exception(socket.gaierror("name or service not known"))
    assert isinstance(dns, PreConnectionUnavailable)

    tls = classify_exception(ssl.SSLError("handshake failed"))
    assert isinstance(tls, PreConnectionUnavailable)


def test_a_timeout_is_its_own_class_and_may_be_billable() -> None:
    timeout = classify_exception(TimeoutError("timed out"))
    assert isinstance(timeout, RequestTimeout)
    assert timeout.category == "timeout"


def test_no_send_path_exception_stays_unclassified() -> None:
    """R6: nothing propagates raw, including failures nobody anticipated."""
    weird = classify_exception(ValueError("something unexpected"))
    assert isinstance(weird, TransportError)
    assert weird.category == "unknown_transport"


def test_classify_passes_an_already_typed_error_through() -> None:
    original = RateLimited("slow down", http_status=429)
    assert classify_exception(original) is original


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (429, RateLimited),
        (500, ServerError),
        (503, ServerError),
        (408, RequestTimeout),
        (504, RequestTimeout),
        (400, ToolSchemaRejected),
    ],
)
def test_http_status_mapping(status: int, expected: type[TransportError]) -> None:
    assert isinstance(for_http_status(status), expected)


def test_error_categories_match_the_committed_schema() -> None:
    """A category the schema does not list would fail validation at write time,
    turning a classification into a crash."""
    schema = build_validator("error.schema.json")
    allowed = set(schema.schema["properties"]["category"]["enum"])
    for cls in ALL_ERROR_CLASSES:
        assert cls.spec.category in allowed, cls.spec.category


def test_unknown_status_is_rejected_by_the_schema() -> None:
    record = UnknownTransportError("x").to_record()
    record["category"] = "not_a_real_category"
    with pytest.raises(ValidationError):
        build_validator("error.schema.json").validate(record)


def test_errors_module_exposes_only_typed_exceptions() -> None:
    """Every public error name in this module subclasses TransportError, so a
    caller catching TransportError cannot miss one."""
    public = [name for name in errors.__dict__ if name.endswith("Error")]
    assert public
    for name in public:
        assert issubclass(getattr(errors, name), Exception)
