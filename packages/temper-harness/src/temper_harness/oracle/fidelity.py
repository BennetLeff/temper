"""Tier A: the recorded corpus, checked for fidelity and reproducibility.

R12 is blunt about what this is worth. Until Tier B -- a live canary -- has run,
Tier A is a **reproducibility instrument, not a fidelity instrument**: it proves
that the client turns these bytes into this typed view every time, not that the
typed view means what the provider meant. The distinction is written into this
module's vocabulary rather than into a comment, because the failure it prevents is
somebody quoting "the oracle passes" as evidence about the provider.

What it *can* prove, and does:

* the raw payload is losslessly recoverable (R8);
* the typed view follows from the raw payload, so a perturbation of either is
  caught (the plan's "fails on a perturbed typed view while the raw bytes stay
  valid");
* a request's identity is the request it names -- a perturbed tool schema makes the
  stored request and the stored hash disagree;
* ordering is the provider's ordering, not merely a permutation that happens to
  contain the same calls;
* usage reconciles against the provider's own total.

Every check is named, because a guard that cannot be *disabled by name* cannot be
shown to bite. The perturbation suite disables one at a time and asserts the
oracle then accepts what it rejected.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from jsonschema import ValidationError

from temper_harness.provider.deepseek import decode_completion, is_event_stream
from temper_harness.provider.errors import TransportError
from temper_harness.provider.interface import buffer_events
from temper_harness.provider.replay import events_from_recording
from temper_harness.provider.usage import normalize_usage
from temper_harness.schema_registry import build_validator
from temper_harness.store.errors import EmptyCorpusError
from temper_harness.store.recorder import scan_corpus
from temper_harness.store.recordings import (
    Recording,
    content_hash,
    decode_response_body,
    encode_response_body,
    request_hash,
)

#: Why the corpus is checked at all. Named so the perturbation suite can disable it.
CORPUS_NOT_EMPTY = "corpus_not_empty"
REQUEST_IDENTITY = "request_identity"
RAW_ROUND_TRIP = "raw_round_trip"
TYPED_VIEW_VALID = "typed_view_valid"
TYPED_VIEW_FAITHFUL = "typed_view_faithful"
TOOL_CALL_ORDER = "tool_call_order"
USAGE_RECONCILED = "usage_reconciled"
USAGE_PRESENT = "usage_present"
STREAM_FRAMING = "stream_framing"

CHECK_NAMES: tuple[str, ...] = (
    CORPUS_NOT_EMPTY,
    REQUEST_IDENTITY,
    RAW_ROUND_TRIP,
    TYPED_VIEW_VALID,
    TYPED_VIEW_FAITHFUL,
    TOOL_CALL_ORDER,
    USAGE_RECONCILED,
    USAGE_PRESENT,
    STREAM_FRAMING,
)

#: The fields a non-streaming provider message carries, compared against what the
#: raw payload actually says.
PROVIDER_FIELDS = (
    "id",
    "model",
    "finish_reason",
    "content",
    "reasoning_content",
    "system_fingerprint",
)


@dataclass(frozen=True, slots=True)
class Violation:
    """One way a recording failed the oracle."""

    check: str
    subject: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.subject}: {self.detail}"


@dataclass(frozen=True, slots=True)
class OracleReport:
    """The verdict for a corpus. Never a bare bool: a count and the reasons."""

    checked: int
    violations: tuple[Violation, ...] = field(default=())

    @property
    def ok(self) -> bool:
        return not self.violations

    def checks_failed(self) -> tuple[str, ...]:
        return tuple(sorted({violation.check for violation in self.violations}))

    def summary(self) -> str:
        if self.ok:
            return f"{self.checked} recording(s) passed every fidelity check"
        return (
            f"{self.checked} recording(s), {len(self.violations)} violation(s) "
            f"across {list(self.checks_failed())}"
        )


class FidelityOracleError(AssertionError):
    """Raised by :func:`assert_faithful`, carrying the violations."""

    def __init__(self, report: OracleReport) -> None:
        self.report = report
        super().__init__(report.summary())


def envelope_of(recording: Recording) -> dict[str, Any] | None:
    """The typed view a recording carries, through the shared adapter decoder.

    ``None`` for a non-2xx recording: a refusal has no envelope, it has an error,
    and inventing one would be the conflation R6 exists to prevent.
    """
    if recording.http_status >= 300:
        return None
    if not is_event_stream(recording.headers.get("content-type")):
        return decode_completion(recording.response_raw, served_from="replay")
    return buffer_events(events_from_recording(recording, stream=True), served_from="replay")


# -- individual checks -------------------------------------------------------


def _check_request_identity(recording: Recording) -> Iterator[str]:
    derived = request_hash(recording.request)
    if derived != recording.request_hash:
        yield (
            f"the stored request hashes to {derived}, not to the stored "
            f"{recording.request_hash}; a perturbed tool schema or message shows up here"
        )


def _check_raw_round_trip(recording: Recording) -> Iterator[str]:
    derived = content_hash(recording.response_raw)
    if derived != recording.response_hash:
        yield f"the raw payload hashes to {derived}, not to the recorded {recording.response_hash}"
    text, encoding = encode_response_body(recording.response_raw)
    if decode_response_body(text, encoding) != recording.response_raw:
        yield f"the {encoding} encoding is not a lossless round trip for this payload"


def _check_typed_view(recording: Recording, envelope: Mapping[str, Any]) -> Iterator[str]:
    try:
        build_validator("envelope.schema.json").validate(dict(envelope))
    except ValidationError as err:
        location = "/".join(str(part) for part in err.absolute_path) or "<root>"
        yield f"the typed view does not satisfy envelope.schema.json: {err.message} (at {location})"


def provider_message(recording: Recording) -> Mapping[str, Any] | None:
    """The provider's own message object, read straight from the payload.

    The independent anchor for a body that arrived whole, and the reason the two view
    guards can fail on the shipped corpus at all: `audit_corpus` derives the typed view
    *with* the decoder, so a guard that only compared the view to a re-derivation would
    be comparing the decoder to itself. A streamed body splits its arguments across
    chunks, so there the payload has no single message to read and this returns ``None``.
    """
    if is_event_stream(recording.headers.get("content-type")):
        return None
    try:
        payload = json.loads(recording.response_raw)
        message = payload["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return message if isinstance(message, Mapping) else None


def _check_faithfulness(
    recording: Recording, envelope: Mapping[str, Any], expected: Mapping[str, Any]
) -> Iterator[str]:
    for name in PROVIDER_FIELDS:
        if envelope.get(name) != expected.get(name):
            yield (
                f"{name}: the typed view says {envelope.get(name)!r}, the raw payload "
                f"says {expected.get(name)!r}"
            )

    actual_calls = {call["id"]: call for call in envelope.get("tool_calls") or ()}
    expected_calls = {call["id"]: call for call in expected.get("tool_calls") or ()}
    if set(actual_calls) != set(expected_calls):
        yield (
            f"tool call ids differ: typed view has {sorted(actual_calls)}, the raw "
            f"payload has {sorted(expected_calls)}"
        )
        return
    for call_id, expected_call in expected_calls.items():
        actual_call = actual_calls[call_id]
        for name in ("name", "arguments"):
            if actual_call.get(name) != expected_call.get(name):
                yield f"tool call {call_id} {name}: {actual_call.get(name)!r} != {expected_call.get(name)!r}"

    # The independent half. Everything above compares the typed view to a re-derivation,
    # which on the shipped path means comparing the decoder to itself; this reads the
    # provider's own JSON instead, so a decoder that rewrote an argument string is
    # caught. Note what it is *not*: a substring search of the raw bytes. The payload
    # JSON-escapes the quotes inside an argument string, so the decoded string never
    # appears verbatim in the payload -- a check written that way fires on a perfect
    # recording, which is how the earlier version of this was found.
    message = provider_message(recording)
    for provider_call in (message or {}).get("tool_calls") or ():
        call_id = provider_call.get("id")
        if call_id not in expected_calls:
            continue
        if provider_call["function"]["arguments"] != expected_calls[call_id]["arguments"]:
            yield (
                f"tool call {call_id} arguments in the typed view differ from the "
                "provider's own JSON; they were rewritten on the way through the decoder"
            )


def _check_tool_call_order(
    recording: Recording, envelope: Mapping[str, Any], expected: Mapping[str, Any]
) -> Iterator[str]:
    """Ordering is the provider's, not merely a set that happens to match.

    A permutation carries the same calls and is a different turn: the results a
    caller sends back are matched to calls by id *and* presented in the order the
    provider emitted them. Swapping two indices is the perturbation that the raw
    bytes cannot see.
    """
    actual_ids = [call["id"] for call in envelope.get("tool_calls") or ()]

    # The independent half: the order the provider actually wrote, for a body that
    # arrived whole. Without it this guard compares the view to a re-derivation, which
    # on the shipped corpus is the decoder compared to itself -- so a decoder that
    # reordered calls would pass. A streamed body splits its calls across chunks, so
    # there the re-derivation is all there is.
    message = provider_message(recording)
    if message is not None:
        provider_ids = [call["id"] for call in message.get("tool_calls") or ()]
        if actual_ids != provider_ids:
            yield f"tool call order is {actual_ids}; the provider emitted {provider_ids}"

    expected_ids = [call["id"] for call in expected.get("tool_calls") or ()]
    if actual_ids != expected_ids:
        yield f"tool call order is {actual_ids}, the re-derivation says {expected_ids}"
    actual_indices = [call["index"] for call in envelope.get("tool_calls") or ()]
    if actual_indices != sorted(actual_indices):
        yield f"tool call indices are not ascending: {actual_indices}"


def _check_usage(recording: Recording, envelope: Mapping[str, Any]) -> Iterator[str]:
    usage = envelope.get("usage")
    if usage is None:
        return
    for name in (
        "prompt_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "cached_input_tokens",
        "total_tokens",
    ):
        if name not in usage:
            yield f"usage is missing {name}; a field the provider reported cannot be absent"
            return
    prompt, completion, total = (
        usage["prompt_tokens"],
        usage["completion_tokens"],
        usage["total_tokens"],
    )
    if None in (prompt, completion, total):
        yield f"usage has a null among the provider's own totals: {usage}"
        return
    if total != prompt + completion:
        yield f"the provider's total {total} is not prompt {prompt} + completion {completion}"
    reasoning = usage["reasoning_tokens"]
    if reasoning is not None and reasoning > completion:
        yield f"reasoning_tokens {reasoning} exceeds completion_tokens {completion}"
    cached = usage["cached_input_tokens"]
    if cached is not None and cached > prompt:
        yield f"cached_input_tokens {cached} exceeds prompt_tokens {prompt}"


def _check_stream_framing(recording: Recording) -> Iterator[str]:
    """The framing facts a streamed recording must satisfy to be replayable at all."""
    if not is_event_stream(recording.headers.get("content-type")):
        return
    raw = recording.response_raw
    if b"data: [DONE]" not in raw:
        yield "the streamed recording has no [DONE] sentinel"
    if not raw.endswith(b"\n\n"):
        yield "the streamed recording does not end on an event boundary"

    payloads = [
        line[len(b"data: ") :]
        for line in raw.split(b"\n")
        if line.startswith(b"data: ") and line != b"data: [DONE]"
    ]
    if not payloads:
        yield "the streamed recording carries no JSON chunks"
        return
    carrying = [index for index, payload in enumerate(payloads) if b'"usage"' in payload]
    if carrying != [len(payloads) - 1]:
        yield f"usage appears on chunks {carrying}, not only on the final one"
    if b'"finish_reason":null' in payloads[-1] or b'"finish_reason": null' in payloads[-1]:
        yield "the final chunk carries no finish reason, so the turn is truncated"


# There is deliberately no `error_classified` guard here. An error record is *derived*
# from the status and body, so a check that re-derived one and compared would be
# comparing a value to itself, and no input could make it fail -- an unfalsifiable check
# in a gate, which this repo has paid for before. What guards an error is the store
# (`http_status` is schema-constrained and the bytes are hash-pinned) and the
# classifier's own suite. This is a comment rather than a function so that the deletion
# is the deletion.


#: Which guards have independent ground truth on the shipped corpus path, where
#: ``audit_corpus`` derives the typed view *with* the decoder. Stated because the
#: difference is otherwise invisible: a guard that compares the derived view to a
#: re-derivation is comparing the decoder to itself and cannot fail, and reading "the
#: corpus passes faithfulness" as protection would be reading it wrong.
#:
#: * independent -- ``corpus_not_empty``, ``request_identity``, ``raw_round_trip``,
#:   ``typed_view_valid`` (the committed schema), ``usage_reconciled``,
#:   ``usage_present``, ``stream_framing``;
#: * independent for a non-streamed recording -- ``typed_view_faithful`` and
#:   ``tool_call_order``, each anchored by a direct read of the provider's own JSON
#:   (:func:`provider_message`); for a streamed recording their only ground truth is the
#:   re-derivation, so there they check consistency rather than fidelity.
#:
#: `_check_tool_call_order` keeps both comparisons for exactly that reason.

#: The per-recording checks, in the order they run. A check that needs the typed
#: view takes it as a second argument.
PAIR_CHECKS: tuple[tuple[str, Callable[..., Iterator[str]]], ...] = (
    (REQUEST_IDENTITY, lambda recording, envelope: _check_request_identity(recording)),
    (RAW_ROUND_TRIP, lambda recording, envelope: _check_raw_round_trip(recording)),
    (STREAM_FRAMING, lambda recording, envelope: _check_stream_framing(recording)),
)


def audit_pair(
    recording: Recording,
    envelope: Mapping[str, Any] | None,
    *,
    enabled: frozenset[str] | None = None,
) -> list[Violation]:
    """Every violation this recording has, for the given typed view.

    ``envelope`` is passed in rather than derived, so a caller can hand over a
    perturbed view and see the oracle reject it while the raw bytes stay valid --
    which is the check that this is a fidelity oracle and not a decoder test.
    """
    active = frozenset(CHECK_NAMES) if enabled is None else enabled
    subject = recording.request_hash
    violations: list[Violation] = []

    for name, check in PAIR_CHECKS:
        if name in active:
            violations.extend(
                Violation(name, subject, detail) for detail in check(recording, envelope)
            )

    if envelope is None:
        # A non-2xx recording has no typed view, so the view checks do not apply.
        return violations

    try:
        expected = envelope_of(recording)
    except TransportError as err:
        violations.append(
            Violation(
                TYPED_VIEW_FAITHFUL,
                subject,
                f"the raw payload no longer decodes into a typed view: {err}",
            )
        )
        return violations
    assert expected is not None

    for name, view_check in (
        (TYPED_VIEW_VALID, lambda r, e, x: _check_typed_view(r, e)),
        (TYPED_VIEW_FAITHFUL, _check_faithfulness),
        (TOOL_CALL_ORDER, _check_tool_call_order),
        (USAGE_RECONCILED, lambda r, e, x: _check_usage(r, e)),
    ):
        if name in active:
            violations.extend(
                Violation(name, subject, detail)
                for detail in view_check(recording, envelope, expected)
            )

    if USAGE_PRESENT in active and recording.http_status < 300:
        if envelope.get("usage") is None:
            violations.append(
                Violation(
                    USAGE_PRESENT,
                    subject,
                    "a successful response carries no usage block; R4 requires the fields "
                    "be present or explicitly unknown, and an absent block is neither",
                )
            )
    return violations


def audit_corpus(
    root: Any,
    *,
    decode: Callable[[Recording], dict[str, Any] | None] = envelope_of,
    enabled: frozenset[str] | None = None,
) -> OracleReport:
    """Run every check over every recording under ``root``.

    Fails closed on an empty corpus, which is the R13 rule this package applies
    everywhere else: a verification loop that iterates nothing reports the same
    clean verdict as one that measured everything.
    """
    active = frozenset(CHECK_NAMES) if enabled is None else enabled
    try:
        recordings = scan_corpus(root)
    except EmptyCorpusError as err:
        if CORPUS_NOT_EMPTY not in active:
            return OracleReport(checked=0)
        return OracleReport(
            checked=0,
            violations=(Violation(CORPUS_NOT_EMPTY, str(root), str(err)),),
        )

    violations: list[Violation] = []
    for recording in recordings:
        violations.extend(audit_pair(recording, decode(recording), enabled=active))
    return OracleReport(checked=len(recordings), violations=tuple(violations))


def assert_faithful(root: Any, **kwargs: Any) -> OracleReport:
    """Audit and raise on any violation. The entry point a gate calls."""
    report = audit_corpus(root, **kwargs)
    if not report.ok:
        raise FidelityOracleError(report)
    return report


def normalized_usage_fields() -> tuple[str, ...]:
    """Re-exported so a caller can assert the record's shape without a second import."""
    return tuple(normalize_usage(None))
