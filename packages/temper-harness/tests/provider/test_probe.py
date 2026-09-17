"""The captured corpus is the authority for everything the wire format claims.

These tests read committed bytes and never touch the network. That is the point:
every assertion here is against what the provider actually sent, so a schema
change that contradicts reality fails on the fixture rather than in a run.

Two of them are fault injections for guards that exist elsewhere:

* ``test_no_fixture_carries_a_credential`` is the R11 canary applied to the
  capture set itself, which is the one artifact kind a live probe writes.
* ``test_the_pinned_request_bodies_match_the_probe_set`` fails the moment a probe
  body is edited without a recapture, so the corpus cannot silently describe a
  request nobody sends.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from temper_harness.provider.errors import TransportError, classify_http_response
from temper_harness.provider.interface import ToolCallDelta, reassemble_tool_calls
from temper_harness.provider.probe import MODEL, PROBE_SET
from temper_harness.provider.usage import normalize_usage, usage_fields
from temper_harness.schema_registry import build_validator
from temper_harness.store.redaction import header_allowlist

CAPTURED = Path(__file__).resolve().parents[1] / "fixtures" / "captured"

MANIFEST: dict[str, Any] = json.loads((CAPTURED / "manifest.json").read_text(encoding="utf-8"))
ENTRIES: dict[str, dict[str, Any]] = {entry["name"]: entry for entry in MANIFEST["probes"]}

#: Anything shaped like a provider key. Deliberately a shape, not the real value:
#: the test must fail on a leaked key without the key being present in the repo.
CREDENTIAL_SHAPE = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")


def meta(name: str) -> dict[str, Any]:
    return json.loads((CAPTURED / f"{name}.meta.json").read_text(encoding="utf-8"))


def request_of(name: str) -> dict[str, Any]:
    return json.loads((CAPTURED / f"{name}.request.json").read_text(encoding="utf-8"))


def response_bytes(name: str) -> bytes:
    suffix = "sse" if ENTRIES[name]["stream"] else "json"
    return (CAPTURED / f"{name}.response.{suffix}").read_bytes()


def response_of(name: str) -> dict[str, Any]:
    return json.loads(response_bytes(name))


def sse_chunks(name: str) -> list[dict[str, Any]]:
    """The JSON payloads of an SSE capture, in order, excluding the sentinel."""
    payloads: list[dict[str, Any]] = []
    for line in response_bytes(name).split(b"\n"):
        if line.startswith(b"data: ") and line != b"data: [DONE]":
            payloads.append(json.loads(line[len(b"data: ") :]))
    return payloads


def successful_nonstreams() -> list[str]:
    return sorted(
        name
        for name, entry in ENTRIES.items()
        if entry["http_status"] == 200 and not entry["stream"]
    )


def streams() -> list[str]:
    return sorted(name for name, entry in ENTRIES.items() if entry["stream"])


# -- the corpus is complete and self-consistent ------------------------------


def test_the_capture_set_is_not_empty() -> None:
    """Anti-vacuity: every test below iterates this, so it must not be empty."""
    assert len(ENTRIES) > 1
    assert successful_nonstreams()
    assert streams()


def test_every_probe_in_the_set_has_a_capture_and_vice_versa() -> None:
    """A probe added without a recapture, or a fixture left behind, fails here."""
    assert {probe.name for probe in PROBE_SET} == set(ENTRIES)


def test_every_response_matches_its_recorded_hash() -> None:
    """The corpus is content-addressed, so a hand-edited fixture is caught."""
    import hashlib

    for name in ENTRIES:
        body = response_bytes(name)
        assert hashlib.sha256(body).hexdigest() == ENTRIES[name]["response_sha256"], name
        assert len(body) == meta(name)["response_bytes"], name


def test_no_fixture_file_is_unreferenced_by_the_manifest() -> None:
    """An unreferenced fixture is one whose checks stopped running."""
    referenced: set[str] = set()
    for entry in ENTRIES.values():
        referenced.update(entry["files"].values())
    referenced.add("manifest.json")
    on_disk = {path.name for path in CAPTURED.iterdir() if path.is_file()}
    assert on_disk == referenced


def test_the_pinned_request_bodies_match_the_probe_set() -> None:
    """Fault injection for corpus/code drift.

    A probe body is a statement about what we send. Editing it without
    recapturing would leave the corpus describing a request that is no longer
    made, and nothing else would notice.
    """
    for probe in PROBE_SET:
        if callable(probe.body):
            continue
        assert request_of(probe.name) == probe.body, probe.name


def test_the_chained_tool_roundtrip_continues_the_captured_turn() -> None:
    """The round trip must replay the provider's own message, not a rebuild.

    Rebuilding it would prove only that my reconstruction agrees with my
    assumptions -- the self-consistency trap.
    """
    assistant = request_of("tool_roundtrip")["messages"][1]
    captured = response_of("parallel_tools")["choices"][0]["message"]
    assert assistant == captured
    assert assistant["reasoning_content"], "the replayed turn must carry reasoning"


def test_every_probe_answered_with_the_status_it_was_expected_to() -> None:
    """A changed status is a provider change, and it must not pass silently."""
    for name, entry in ENTRIES.items():
        assert entry["status_as_expected"], (
            f"{name} answered {entry['http_status']}, expected {entry['expect_status']}"
        )


def test_the_account_serves_the_target_model() -> None:
    """The plan's model id was wrong; the manifest records the ids that exist."""
    assert MODEL in MANIFEST["account_models"]
    assert sorted(MANIFEST["account_models"]) == MANIFEST["account_models"]


# -- R11 ---------------------------------------------------------------------


def test_no_fixture_carries_a_credential() -> None:
    """The canary, applied to the capture set. Scans bytes, not fields."""
    offenders = [
        path.name
        for path in sorted(CAPTURED.iterdir())
        if path.is_file()
        and (
            CREDENTIAL_SHAPE.search(path.read_text(encoding="utf-8", errors="ignore"))
            or "authorization" in path.read_text(encoding="utf-8", errors="ignore").lower()
        )
    ]
    assert offenders == []


def test_every_recorded_header_is_on_the_committed_allowlist() -> None:
    """A header outside the allowlist would mean R11's boundary was bypassed."""
    allowed = set(header_allowlist())
    for name in ENTRIES:
        recorded = set(meta(name)["headers"])
        assert recorded, name  # a capture with no headers would make this vacuous
        assert recorded <= allowed, (name, sorted(recorded - allowed))


def test_the_capture_records_the_providers_correlation_id() -> None:
    """x-ds-trace-id is what a billing dispute is reconciled against."""
    assert "x-ds-trace-id" in meta("plain")["headers"]


# -- usage, frozen from the bytes -------------------------------------------


def test_the_committed_usage_record_has_more_than_one_field() -> None:
    assert len(usage_fields()) > 1


@pytest.mark.parametrize("name", successful_nonstreams())
def test_every_captured_usage_block_normalizes_into_the_committed_schema(name: str) -> None:
    """The mapping is the thing being pinned, so it is run over every sample."""
    record = normalize_usage(response_of(name)["usage"])
    build_validator("usage.schema.json").validate(record)


@pytest.mark.parametrize("name", successful_nonstreams())
def test_the_provider_reports_every_field_the_record_requires(name: str) -> None:
    """No field is null, so the record is a measurement rather than a gap."""
    record = normalize_usage(response_of(name)["usage"])
    missing = sorted(field for field, value in record.items() if value is None)
    assert missing == [], name


@pytest.mark.parametrize("name", successful_nonstreams())
def test_the_providers_own_total_equals_prompt_plus_completion(name: str) -> None:
    """The external check on the accounting, asserted over the whole corpus.

    KTD7 wanted computed and provider-reported cost to agree; the provider
    reports no cost, so this is where that check lives.
    """
    record = normalize_usage(response_of(name)["usage"])
    assert record["total_tokens"] == record["prompt_tokens"] + record["completion_tokens"]


@pytest.mark.parametrize("name", successful_nonstreams())
def test_reasoning_tokens_are_a_subset_of_completion_tokens(name: str) -> None:
    """The measured fact the aggregate's additive set depends on.

    This is why ``reasoning_tokens`` must not be summed with
    ``completion_tokens``: over this corpus reasoning is most of the completion,
    so adding them would over-report by a large factor rather than a rounding
    error.
    """
    record = normalize_usage(response_of(name)["usage"])
    assert record["reasoning_tokens"] is not None
    assert record["reasoning_tokens"] <= record["completion_tokens"]


@pytest.mark.parametrize("name", successful_nonstreams())
def test_cached_input_tokens_are_a_subset_of_prompt_tokens(name: str) -> None:
    record = normalize_usage(response_of(name)["usage"])
    assert record["cached_input_tokens"] is not None
    assert record["cached_input_tokens"] <= record["prompt_tokens"]


def test_a_missing_usage_block_becomes_nulls_never_zeroes() -> None:
    """R4, at the only place the provider's block becomes our record."""
    record = normalize_usage(None)
    assert set(record) == set(usage_fields())
    assert all(value is None for value in record.values())


# -- errors, frozen from the bytes -----------------------------------------


def captured_failures() -> list[str]:
    return sorted(name for name, entry in ENTRIES.items() if entry["http_status"] >= 400)


def test_there_is_at_least_one_captured_failure() -> None:
    assert captured_failures()


@pytest.mark.parametrize("name", captured_failures())
def test_every_captured_failure_classifies_into_the_taxonomy(name: str) -> None:
    """No captured failure may be left as a raw exception (R6)."""
    status = ENTRIES[name]["http_status"]
    error = classify_http_response(status, response_bytes(name))
    assert isinstance(error, TransportError)
    build_validator("error.schema.json").validate(error.to_record())


def test_a_rejected_request_is_recorded_as_not_retryable() -> None:
    error = classify_http_response(400, response_bytes("invalid_model"))
    assert error.retryable is False


# -- streaming, frozen from the bytes ---------------------------------------


def test_stream_responses_are_sse_and_terminated_by_the_done_sentinel() -> None:
    """The sentinel is a complete SSE record, so it ends with a blank line.

    ``data: [DONE]\\n\\n`` and not ``data: [DONE]\\n``: the double newline is the
    event terminator, and a parser that split on single lines without honouring
    the blank-line boundary would treat the sentinel as just another chunk.
    """
    for name in streams():
        assert response_bytes(name).endswith(b"data: [DONE]\n\n"), name
        assert meta(name)["headers"]["content-type"].startswith("text/event-stream"), name


def test_every_stream_chunk_is_a_json_object() -> None:
    for name in streams():
        chunks = sse_chunks(name)
        assert len(chunks) > 1, name
        assert all(chunk["object"] == "chat.completion.chunk" for chunk in chunks), name


def test_usage_arrives_once_on_the_final_chunk_and_is_not_fragmented() -> None:
    """The plan named this as an unknown; the capture settles it.

    Usage is not accumulated across chunks. Assuming it was would have produced a
    null usage block for every streamed call -- a systematically-zero column,
    which is the exact shape this package exists to prevent.
    """
    for name in streams():
        chunks = sse_chunks(name)
        carrying = [index for index, chunk in enumerate(chunks) if "usage" in chunk]
        assert carrying == [len(chunks) - 1], name
        assert chunks[-1]["usage"]["total_tokens"] > 0, name


def test_finish_reason_appears_once_on_the_final_chunk() -> None:
    for name in streams():
        chunks = sse_chunks(name)
        reasons = [
            index
            for index, chunk in enumerate(chunks)
            if chunk["choices"][0]["finish_reason"] is not None
        ]
        assert reasons == [len(chunks) - 1], name


def test_absent_stream_delta_fields_are_explicit_nulls() -> None:
    """``null`` means "no delta", which is not the same as an empty string."""
    chunks = sse_chunks("stream_plain")
    first = chunks[0]["choices"][0]["delta"]
    assert first["content"] is None
    assert "role" in first


def test_the_parallel_tool_calls_have_distinct_ids_and_stable_order() -> None:
    message = response_of("parallel_tools")["choices"][0]["message"]
    calls = message["tool_calls"]
    assert [call["index"] for call in calls] == [0, 1]
    assert [call["function"]["name"] for call in calls] == ["place", "check"]
    assert len({call["id"] for call in calls}) == len(calls)


def test_streamed_tool_calls_reassemble_from_real_fragmentation() -> None:
    """The reassembler, against the provider's actual split points.

    Captured fragmentation is character-level -- ``{``, ``"``, ``reference`` --
    so an escape split across chunks is the norm rather than an edge case. This
    runs the shipped reassembler over the real fragments rather than over a
    hand-written example chosen to exercise it, because a differential only
    proves what it is fed.
    """
    fragments: list[ToolCallDelta] = []
    for chunk in sse_chunks("stream_tools"):
        for raw in chunk["choices"][0]["delta"].get("tool_calls", []):
            function = raw.get("function", {})
            fragments.append(
                ToolCallDelta(
                    index=raw["index"],
                    id=raw.get("id"),
                    name=function.get("name"),
                    arguments=function.get("arguments", ""),
                )
            )
    assert len(fragments) > 2, "the capture must actually be fragmented for this to mean anything"

    calls = reassemble_tool_calls(fragments)
    assert [call.index for call in calls] == [0, 1]
    assert [call.name for call in calls] == ["place", "check"]
    assert len({call.id for call in calls}) == len(calls)

    streamed = [(call.name, json.loads(call.arguments)) for call in calls]
    nonstreamed = [
        (call["function"]["name"], json.loads(call["function"]["arguments"]))
        for call in response_of("parallel_tools")["choices"][0]["message"]["tool_calls"]
    ]
    # The two independent captures agree on the semantics; only the ids differ,
    # because the provider mints new ones per call.
    assert streamed == nonstreamed
