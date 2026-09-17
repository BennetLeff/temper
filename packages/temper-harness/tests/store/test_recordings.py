"""The recording shape, its hashes, and the committed-schema contract."""

from __future__ import annotations

import copy
import json

import pytest

from temper_harness.schema_registry import build_validator, load_schema
from temper_harness.store import (
    CorruptRecording,
    CredentialLeakError,
    Recording,
    RecordingFormatError,
    UnsupportedRecordingVersion,
    canonical_request_bytes,
    content_hash,
    current_recording_version,
    header_allowlist,
    redact_headers,
    request_hash,
    supported_recording_versions,
)
from temper_harness.store import redaction as redaction_module
from temper_harness.store.redaction import CREDENTIAL_HEADER_TOKENS, RECORDING_SCHEMA

REQUEST = {
    "model": "deepseek-flash",
    "messages": [{"role": "user", "content": "place the part"}],
}
RESPONSE = b'{"id":"msg-1","choices":[{"finish_reason":"stop","message":{"content":"ok"}}]}'
HEADERS = {"Content-Type": "application/json", "Authorization": "Bearer sk-planted"}


def build_recording(**overrides: object) -> Recording:
    kwargs: dict[str, object] = {
        "request": REQUEST,
        "response_raw": RESPONSE,
        "headers": HEADERS,
        "provider": "deepseek",
        "model": "deepseek-flash",
        "http_status": 200,
        "arm": "direct",
        "attempt": 0,
    }
    kwargs.update(overrides)
    return Recording.build(**kwargs)  # type: ignore[arg-type]


# -- version identity --------------------------------------------------------


def test_the_supported_versions_come_from_the_committed_schema() -> None:
    """Anti-vacuity, and R14: the reader does not carry its own copy.

    A version set that lived in Python could drift from the enum in the schema,
    and the two would disagree exactly when it mattered -- on the first
    recording written by a newer client.
    """
    versions = supported_recording_versions()
    assert versions
    declared = load_schema(RECORDING_SCHEMA)["properties"]["schema_version"]["enum"]
    assert list(versions) == list(declared)
    assert current_recording_version() in versions


# -- request identity --------------------------------------------------------


def test_key_order_is_not_part_of_a_request_identity() -> None:
    """A JSON object has no order to a model, so it must not decide a replay."""
    first = {"model": "m", "messages": [{"role": "user"}]}
    second = {"messages": [{"role": "user"}], "model": "m"}
    assert canonical_request_bytes(first) == canonical_request_bytes(second)
    assert request_hash(first) == request_hash(second)


def test_a_different_body_is_a_different_identity() -> None:
    assert request_hash({"model": "m"}) != request_hash({"model": "n"})


def test_a_nested_difference_is_a_different_identity() -> None:
    """The hash must see into tool schemas, or two tools would collide."""
    left = {"tools": [{"function": {"parameters": {"additionalProperties": False}}}]}
    right = {"tools": [{"function": {"parameters": {"additionalProperties": True}}}]}
    assert request_hash(left) != request_hash(right)


def test_the_response_hash_is_over_the_received_bytes() -> None:
    recording = build_recording()
    assert recording.response_hash == content_hash(RESPONSE)
    assert recording.response_raw == RESPONSE


# -- round trips -------------------------------------------------------------


def test_a_recording_round_trips_to_the_same_response_bytes() -> None:
    """The store's whole contract: what comes out is what went in."""
    original = build_recording()
    restored = Recording.from_wire(json.loads(original.to_json_bytes().decode("utf-8")))
    assert restored.response_raw == original.response_raw
    assert restored == original


def test_bytes_that_are_not_valid_utf8_survive_the_round_trip() -> None:
    """R8's lossless raw payload, tested where a text field would fail.

    An SSE body is usually UTF-8, so a JSON-string field would look correct
    until the first body that is not -- and then it would be lossy exactly once,
    in the recording nobody can re-derive.
    """
    binary = bytes(range(256))
    original = build_recording(response_raw=binary)
    restored = Recording.from_wire(json.loads(original.to_json_bytes().decode("utf-8")))
    assert restored.response_raw == binary


def test_the_on_disk_form_is_canonical_and_newline_terminated() -> None:
    """A determinism-bearing artifact: sorted keys, stable bytes.

    ``PYTHONHASHSEED``-dependent ordering in an artifact like this is a defect
    this repo gates against, so the canonical form is asserted rather than
    assumed.
    """
    data = build_recording().to_json_bytes()
    assert data.endswith(b"\n")
    text = data.decode("utf-8")
    assert json.dumps(json.loads(text), sort_keys=True, indent=2) + "\n" == text


def test_to_wire_does_not_hand_out_its_internals() -> None:
    recording = build_recording()
    wire = recording.to_wire()
    wire["request"]["messages"][0]["content"] = "tampered"
    assert recording.request["messages"][0]["content"] == "place the part"


def test_a_caller_mutating_its_request_cannot_corrupt_the_recording() -> None:
    """Aliasing a mutable caller object into a hashed artifact is the defect.

    Without the deep copy, a caller that reused and mutated its request dict
    would leave the recording holding a body that no longer hashes to its own
    ``request_hash`` -- and the file written afterwards would be unreadable.
    """
    body = {"model": "m", "messages": [{"role": "user", "content": "before"}]}
    recording = build_recording(request=body)
    body["messages"][0]["content"] = "after"
    assert recording.request["messages"][0]["content"] == "before"
    recording.verify()
    assert Recording.from_wire(json.loads(recording.to_json_bytes().decode())).request == (
        recording.request
    )


# -- redaction at the write boundary ----------------------------------------


def test_headers_are_redacted_before_anything_is_written() -> None:
    recording = build_recording()
    assert "authorization" not in recording.headers
    assert recording.headers == {"content-type": "application/json"}
    assert b"sk-planted" not in recording.to_json_bytes()


def test_header_names_are_folded_to_lowercase() -> None:
    assert redact_headers({"Content-Type": "application/json"}) == {
        "content-type": "application/json"
    }


def test_the_allowlist_never_admits_a_credential_header() -> None:
    """A guard on the guard: R11's allowlist is only a control if it is closed."""
    for name in header_allowlist():
        assert not any(token in name for token in CREDENTIAL_HEADER_TOKENS), name


def test_an_emptied_allowlist_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The committed fault injection for the empty-scan guard.

    An allowlist that became empty would silently drop every header, and the
    canary over those artifacts would then be scanning for a leak it had made
    impossible -- a clean verdict measuring nothing.
    """
    real_load = redaction_module.load_schema

    def emptied(name: str) -> dict:
        schema = real_load(name)
        if name == RECORDING_SCHEMA:
            schema = copy.deepcopy(schema)
            schema["$defs"]["headers"]["propertyNames"]["enum"] = []
        return schema

    monkeypatch.setattr(redaction_module, "load_schema", emptied)
    with pytest.raises(RecordingFormatError, match="empty header allowlist"):
        header_allowlist()


def test_an_allowlist_widened_to_a_credential_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The fault injection for the leak guard itself.

    Widening the enum is the one edit that turns R11's control into a leak path,
    so it fails at the point of use rather than at the next canary run.
    """
    real_load = redaction_module.load_schema

    def widened(name: str) -> dict:
        schema = real_load(name)
        if name == RECORDING_SCHEMA:
            schema = copy.deepcopy(schema)
            schema["$defs"]["headers"]["propertyNames"]["enum"] = ["authorization"]
        return schema

    monkeypatch.setattr(redaction_module, "load_schema", widened)
    with pytest.raises(CredentialLeakError, match="credential-bearing"):
        header_allowlist()


# -- refusal paths -----------------------------------------------------------


def test_a_freshly_built_recording_validates_against_the_committed_schema() -> None:
    build_validator(RECORDING_SCHEMA).validate(build_recording().to_wire())


def test_an_extra_field_is_refused() -> None:
    wire = build_recording().to_wire()
    wire["surprise"] = "value"
    with pytest.raises(RecordingFormatError, match="does not satisfy"):
        Recording.from_wire(wire)


def test_an_unparseable_schema_version_is_refused() -> None:
    wire = build_recording().to_wire()
    wire["schema_version"] = "latest"
    with pytest.raises(UnsupportedRecordingVersion, match="not a MAJOR.MINOR"):
        Recording.from_wire(wire)


def test_an_unknown_schema_version_is_refused() -> None:
    """A version this client does not know must fail, not be interpreted."""
    wire = build_recording().to_wire()
    wire["schema_version"] = "99.0"
    with pytest.raises(UnsupportedRecordingVersion, match="not one of"):
        Recording.from_wire(wire)


def test_a_non_string_schema_version_is_refused() -> None:
    wire = build_recording().to_wire()
    wire["schema_version"] = 1
    with pytest.raises(UnsupportedRecordingVersion, match="must be a string"):
        Recording.from_wire(wire)


def test_a_non_object_recording_is_refused() -> None:
    with pytest.raises(RecordingFormatError, match="must be a JSON object"):
        Recording.from_wire(["not", "a", "recording"])


def test_a_response_whose_hash_disagrees_with_its_bytes_is_refused() -> None:
    wire = build_recording().to_wire()
    wire["response_raw"] = "ZGlmZmVyZW50"  # valid base64, different bytes
    with pytest.raises(CorruptRecording, match="response hash mismatch"):
        Recording.from_wire(wire)


def test_a_request_whose_hash_disagrees_with_its_body_is_refused() -> None:
    wire = build_recording().to_wire()
    wire["request_hash"] = "0" * 64
    with pytest.raises(CorruptRecording, match="request hash mismatch"):
        Recording.from_wire(wire)


def test_response_text_that_is_not_base64_is_refused_when_base64_is_declared() -> None:
    """The decoder is the assertion for the encoding, so nothing else duplicates it."""
    wire = build_recording().to_wire()
    wire["response_encoding"] = "base64"
    wire["response_raw"] = "not base64 !!"
    with pytest.raises(CorruptRecording, match="not valid base64"):
        Recording.from_wire(wire)


def test_an_unknown_response_encoding_is_refused() -> None:
    wire = build_recording().to_wire()
    wire["response_encoding"] = "rot13"
    with pytest.raises(RecordingFormatError):
        Recording.from_wire(wire)


def test_a_utf8_body_is_carried_as_readable_text() -> None:
    """A committed fixture should show the provider's own bytes, not a blob."""
    recording = build_recording(response_raw=b'{"id":"msg-1"}')
    assert recording.response_encoding == "utf-8"
    assert recording.response_text == '{"id":"msg-1"}'


def test_a_body_that_is_not_utf8_falls_back_to_base64() -> None:
    recording = build_recording(response_raw=b"\xff\xfe\x00\x01")
    assert recording.response_encoding == "base64"
    assert Recording.from_wire(recording.to_wire()).response_raw == b"\xff\xfe\x00\x01"


def test_the_http_status_round_trips() -> None:
    """A replayed 400 must arrive as a 400, not as a 200 carrying an error body."""
    recording = build_recording(http_status=400)
    assert recording.http_status == 400
    assert Recording.from_wire(recording.to_wire()).http_status == 400


def test_an_impossible_http_status_is_refused() -> None:
    wire = build_recording().to_wire()
    wire["http_status"] = 999
    with pytest.raises(RecordingFormatError):
        Recording.from_wire(wire)


def test_a_header_outside_the_allowlist_is_refused_by_the_schema() -> None:
    """The committed schema is the enforcement point, not a Python set."""
    wire = build_recording().to_wire()
    wire["headers"]["authorization"] = "Bearer sk-planted"
    with pytest.raises(RecordingFormatError):
        Recording.from_wire(wire)
