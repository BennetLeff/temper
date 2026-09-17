"""The taxonomy must be exhaustive, or R6's guarantee is unenforced."""

from __future__ import annotations

import json
import socket
import ssl

import pytest
from jsonschema import ValidationError

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
    RequestRejected,
    RequestTimeout,
    ServerError,
    ToolSchemaRejected,
    TransportError,
    UnknownTransportError,
    classify_exception,
    classify_http_response,
    for_http_status,
    provider_error_message,
)
from temper_harness.schema_registry import build_validator

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
    RequestRejected,
    ContentFiltered,
    EndpointRejected,
    UnknownTransportError,
]

#: The four 400 bodies captured from the live provider. They are the reason a
#: status-only classifier was wrong: all four carry ``invalid_request_error`` and
#: ``code: invalid_request_error``, so the body is the only discriminator.
CAPTURED_400_BODIES = {
    "bad model name": (
        b'{"error":{"message":"The supported API model names are deepseek-flash, '
        b'deepseek-v4-pro, but you passed deepseek-v4.1-flash.","type":'
        b'"invalid_request_error","param":null,"code":"invalid_request_error"}}'
    ),
    "orphan tool result": (
        b'{"error":{"message":"Messages with role \'tool\' must be a response to a '
        b'preceding message with \'tool_calls\'","type":"invalid_request_error",'
        b'"param":null,"code":"invalid_request_error"}}'
    ),
    "bad tool schema": (
        b'{"error":{"message":"Invalid schema for function \'place\': \\"not-a-real-type\\" '
        b'is not valid under any of the schemas listed in the \'anyOf\' keyword","type":'
        b'"invalid_request_error","param":null,"code":"invalid_request_error"}}'
    ),
    "reasoning dropped": (
        b'{"error":{"message":"The `reasoning_content` in the thinking mode must be '
        b'passed back to the API.","type":"invalid_request_error","param":null,'
        b'"code":"invalid_request_error"}}'
    ),
}


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
        (400, RequestRejected),
    ],
)
def test_http_status_mapping(status: int, expected: type[TransportError]) -> None:
    """Status-only mapping, and 400 is the interesting row.

    It used to map to ``ToolSchemaRejected``, which the captures show is wrong:
    a 400 is also how a bad model name, an orphaned tool result, and a dropped
    reasoning field arrive. The timeout rows are here because ``504 >= 500`` and
    a branch order that checked 5xx first would swallow it.
    """
    assert isinstance(for_http_status(status), expected)


def test_a_rejected_request_is_not_retryable() -> None:
    """A deterministic request defect must not be retried forever.

    The catch-all ``unknown_transport`` is retryable, so routing a 400 there
    would have produced a retry loop against a request the provider will refuse
    identically every time.
    """
    rejected = for_http_status(400)
    assert rejected.retryable is False
    assert rejected.billable is False


@pytest.mark.parametrize("name", sorted(CAPTURED_400_BODIES))
def test_no_captured_400_body_classifies_as_a_tool_schema_rejection(
    name: str,
) -> None:
    """The fault injection for the mislabelling.

    Three of the four captured 400s are not tool-schema problems. Restore
    ``for_http_status(400) -> ToolSchemaRejected`` as the body-aware default and
    this goes red for those three.
    """
    error = classify_http_response(400, CAPTURED_400_BODIES[name])
    if name == "bad tool schema":
        assert isinstance(error, ToolSchemaRejected)
    else:
        assert isinstance(error, RequestRejected)
    assert error.http_status == 400
    assert error.retryable is False


def test_the_captured_message_reaches_the_error_record() -> None:
    """The provider's own words are what a human debugs from."""
    error = classify_http_response(400, CAPTURED_400_BODIES["bad model name"])
    assert "deepseek-flash" in str(error)
    assert error.to_record()["category"] == "request_rejected"


def test_provider_error_message_reads_the_captured_shape() -> None:
    assert provider_error_message(CAPTURED_400_BODIES["bad tool schema"]) is not None


def test_provider_error_message_declines_a_non_json_body() -> None:
    """A proxy answering with HTML is a malformed response, not a parse crash."""
    assert provider_error_message(b"<html>502 Bad Gateway</html>") is None
    assert provider_error_message(None) is None
    assert provider_error_message(b"{not json") is None


def test_a_non_json_error_body_still_classifies() -> None:
    error = classify_http_response(503, b"<html>503</html>")
    assert isinstance(error, ServerError)
    assert error.retryable is True


def test_the_unverified_markers_still_classify() -> None:
    """Context length and content filtering are wired but unproven here.

    No probe produced either message on this provider, so these markers are
    declared unverified rather than measured. They are exercised against
    synthetic bodies so the wiring cannot rot, and the plan's unknowns list says
    plainly that no captured body backs them.
    """
    assert isinstance(
        classify_http_response(
            400,
            json.dumps(
                {"error": {"message": "This model's maximum context length is 65536 tokens"}}
            ).encode(),
        ),
        ContextLengthExceeded,
    )
    assert isinstance(
        classify_http_response(
            400,
            json.dumps({"error": {"message": "Blocked by content filter"}}).encode(),
        ),
        ContentFiltered,
    )


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
