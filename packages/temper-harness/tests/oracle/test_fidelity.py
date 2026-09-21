"""Tier A oracle tests, and the perturbations that must make it go red.

A fidelity oracle that cannot be shown to reject anything is a green light with no
bulb, so every guard here is exercised twice: once against the committed corpus
(where it must pass) and once against an input it exists to catch (where it must
fail). Each perturbation is crafted to trip **exactly one** guard, which is what
makes "disable that guard and the input is accepted" a real demonstration rather
than a tautology.

The committed evidence under ``evidence/`` is that demonstration, recorded. It is
re-derived by these tests on every run, so it cannot drift from the behaviour it
describes: regenerate with ``TEMPER_HARNESS_WRITE_GUARD_EVIDENCE=1``.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from temper_harness.oracle import (
    CHECK_NAMES,
    CORPUS_NOT_EMPTY,
    RAW_ROUND_TRIP,
    REQUEST_IDENTITY,
    STREAM_FRAMING,
    TOOL_CALL_ORDER,
    TYPED_VIEW_FAITHFUL,
    TYPED_VIEW_VALID,
    USAGE_PRESENT,
    USAGE_RECONCILED,
    FidelityOracleError,
    Violation,
    assert_faithful,
    audit_corpus,
    audit_pair,
    envelope_of,
)
from temper_harness.store import Recording
from temper_harness.store.recordings import content_hash
from tests import corpus

EVIDENCE_DIR = Path(__file__).resolve().parent / "evidence"
EVIDENCE_FILE = EVIDENCE_DIR / "guard_removal.json"
WRITE_ENV = "TEMPER_HARNESS_WRITE_GUARD_EVIDENCE"


@pytest.fixture
def recordings(tmp_path: Path) -> list[Recording]:
    return corpus.build_corpus(tmp_path)


# -- the corpus itself -------------------------------------------------------


def test_the_committed_corpus_passes_every_check(tmp_path: Path) -> None:
    """Anti-vacuity first: an empty corpus would make this prove nothing."""
    built = corpus.build_corpus(tmp_path)
    assert built, "the corpus builder produced nothing"

    report = audit_corpus(tmp_path)
    assert report.ok, "\n".join(str(v) for v in report.violations)
    assert report.checked == len(built)
    assert report.checked == len(corpus.CORPUS_PROBES)


def test_the_guard_registry_is_not_empty_and_has_no_duplicates() -> None:
    assert len(CHECK_NAMES) > 1
    assert len(set(CHECK_NAMES)) == len(CHECK_NAMES)


def test_an_empty_corpus_fails_rather_than_reporting_clean(tmp_path: Path) -> None:
    """R13: zero recordings and a clean verdict are the same green light."""
    empty = tmp_path / "nothing-here"
    report = audit_corpus(empty)
    assert not report.ok
    assert report.checked == 0
    assert report.checks_failed() == (CORPUS_NOT_EMPTY,)

    with pytest.raises(FidelityOracleError) as caught:
        assert_faithful(empty)
    assert CORPUS_NOT_EMPTY in caught.value.report.checks_failed()


def test_disabling_the_empty_corpus_guard_accepts_an_empty_corpus(tmp_path: Path) -> None:
    without = frozenset(CHECK_NAMES) - {CORPUS_NOT_EMPTY}
    assert audit_corpus(tmp_path / "nothing-here", enabled=without).ok


def test_a_shipped_recording_and_a_streamed_recording_both_audit_clean(
    recordings: list[Recording],
) -> None:
    for name in ("parallel_tools", "stream_plain", "strict_schema"):
        recording = corpus.recording_named(recordings, name)
        envelope = envelope_of(recording)
        assert envelope is not None, name
        assert audit_pair(recording, envelope) == [], name


def test_a_recorded_refusal_has_no_typed_view_and_is_not_invented(
    recordings: list[Recording],
) -> None:
    """A refusal is not a turn, and inventing an envelope for one is the R6 conflation."""
    recording = corpus.recording_named(recordings, "invalid_model")
    assert recording.http_status == 400
    assert envelope_of(recording) is None
    assert audit_pair(recording, None) == []


def test_the_typed_view_is_schema_valid_for_every_corpus_entry(
    recordings: list[Recording],
) -> None:
    """Every 2xx entry, not a sample: the schema contract is checked corpus-wide."""
    checked = 0
    for recording in recordings:
        envelope = envelope_of(recording)
        if envelope is None:
            continue
        assert audit_pair(recording, envelope) == [], recording.request_hash
        checked += 1
    assert checked > 1, "anti-vacuity: the loop must actually check something"


# -- perturbations -----------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class Perturbation:
    """One way to break a recording, and the one guard that must notice.

    ``mutate`` returns a ``(recording, typed_view)`` pair. Exactly one of the two is
    changed, and the mutation is chosen so that no *other* guard is in a position to
    see it -- which is what lets the guard-removal evidence be meaningful.
    """

    name: str
    fixture: str
    guard: str
    mutate: Callable[[Recording, dict[str, Any]], tuple[Recording, dict[str, Any]]]
    what: str
    #: What the mutation touches: the typed view, the request, the raw response bytes,
    #: or the stored hash. Only the last two can disturb the payload's integrity, and
    #: the tests use this to assert that the others leave it untouched.
    touches: str = "view"


def _enrich_the_typed_view(
    recording: Recording, envelope: dict[str, Any]
) -> tuple[Recording, dict]:
    """An unexpected field: the schema's `additionalProperties` is the only guard."""
    perturbed = copy.deepcopy(envelope)
    perturbed["surprise"] = "a field nobody modelled"
    return recording, perturbed


def _swap_tool_arguments(recording: Recording, envelope: dict[str, Any]) -> tuple[Recording, dict]:
    """Two calls' argument strings exchanged: ids and order untouched.

    The most dangerous of the set. The document stays schema-valid and the call set
    is unchanged, so a reader sees two plausible calls and the model is credited with
    parameters it never produced.
    """
    perturbed = copy.deepcopy(envelope)
    first, second = perturbed["tool_calls"][0], perturbed["tool_calls"][1]
    first["arguments"], second["arguments"] = second["arguments"], first["arguments"]
    return recording, perturbed


def _reorder_tool_calls(recording: Recording, envelope: dict[str, Any]) -> tuple[Recording, dict]:
    perturbed = copy.deepcopy(envelope)
    perturbed["tool_calls"] = list(reversed(perturbed["tool_calls"]))
    return recording, perturbed


def _alter_the_usage_total(
    recording: Recording, envelope: dict[str, Any]
) -> tuple[Recording, dict]:
    """A total that no longer equals the parts. Schema-valid, and wrong."""
    perturbed = copy.deepcopy(envelope)
    perturbed["usage"]["total_tokens"] = 9_999
    return recording, perturbed


def _null_the_usage_block(recording: Recording, envelope: dict[str, Any]) -> tuple[Recording, dict]:
    perturbed = copy.deepcopy(envelope)
    perturbed["usage"] = None
    return recording, perturbed


def _drop_the_done_sentinel(
    recording: Recording, envelope: dict[str, Any]
) -> tuple[Recording, dict]:
    """A streamed body with no sentinel, but a finish reason.

    The hash is recomputed so the payload remains self-consistent: this is the shape
    of a provider that stopped emitting the sentinel, not a corrupted file. Only the
    framing guard can see it, because the turn still decodes completely.
    """
    raw = recording.response_raw.replace(b"data: [DONE]\n\n", b"")
    assert raw != recording.response_raw
    return dataclasses.replace(
        recording, response_raw=raw, response_hash=content_hash(raw)
    ), envelope


def _disagree_the_response_hash(
    recording: Recording, envelope: dict[str, Any]
) -> tuple[Recording, dict]:
    """The bytes and their hash disagree -- the same fact as a mutated byte."""
    return dataclasses.replace(recording, response_hash="0" * 64), envelope


def _perturb_a_tool_schema(
    recording: Recording, envelope: dict[str, Any]
) -> tuple[Recording, dict]:
    """The tool schema sent differs from the one the request hash names.

    Built with :func:`dataclasses.replace` so the request and its hash disagree --
    the state a hand-edited fixture or a merged corpus would be in, and the state the
    oracle exists to refuse.
    """
    request = copy.deepcopy(recording.request)
    tools = request.get("tools") or []
    assert tools, "this perturbation needs a fixture that sent tools"
    tools[0]["function"]["description"] = "a description nobody sent"
    return dataclasses.replace(recording, request=request), envelope


PERTURBATIONS: tuple[Perturbation, ...] = (
    Perturbation(
        "enrich_the_typed_view",
        "plain",
        TYPED_VIEW_VALID,
        _enrich_the_typed_view,
        "an extra field in the typed view, which only the committed schema forbids",
    ),
    Perturbation(
        "swap_tool_arguments",
        "parallel_tools",
        TYPED_VIEW_FAITHFUL,
        _swap_tool_arguments,
        "two calls' argument strings exchanged, leaving ids, order, and schema intact",
    ),
    Perturbation(
        "reorder_tool_calls",
        "parallel_tools",
        TOOL_CALL_ORDER,
        _reorder_tool_calls,
        "the same two calls in the other order",
    ),
    Perturbation(
        "alter_the_usage_total",
        "plain",
        USAGE_RECONCILED,
        _alter_the_usage_total,
        "a provider total that no longer equals prompt + completion",
    ),
    Perturbation(
        "null_the_usage_block",
        "plain",
        USAGE_PRESENT,
        _null_the_usage_block,
        "a successful response with no usage block at all",
    ),
    Perturbation(
        "drop_the_done_sentinel",
        "stream_plain",
        STREAM_FRAMING,
        _drop_the_done_sentinel,
        "a streamed body with a finish reason but no [DONE] sentinel",
        touches="raw",
    ),
    Perturbation(
        "disagree_the_response_hash",
        "plain",
        RAW_ROUND_TRIP,
        _disagree_the_response_hash,
        "a stored hash that does not match the stored bytes",
        touches="hash",
    ),
    Perturbation(
        "perturb_a_tool_schema",
        "strict_schema",
        REQUEST_IDENTITY,
        _perturb_a_tool_schema,
        "a tool schema that the recorded request hash does not name",
        touches="request",
    ),
)


def _apply(
    recordings: list[Recording],
    perturbation: Perturbation,
    *,
    enabled: frozenset[str] | None = None,
) -> list[Violation]:
    recording = corpus.recording_named(recordings, perturbation.fixture)
    base = envelope_of(recording)
    assert base is not None
    perturbed_recording, perturbed_view = perturbation.mutate(recording, base)
    return audit_pair(perturbed_recording, perturbed_view, enabled=enabled)


def test_every_guard_has_a_perturbation() -> None:
    """A guard with no perturbation is a guard nobody has seen fire."""
    covered = {perturbation.guard for perturbation in PERTURBATIONS} | {CORPUS_NOT_EMPTY}
    assert covered == set(CHECK_NAMES)


@pytest.mark.parametrize("perturbation", PERTURBATIONS, ids=lambda p: p.name)
def test_a_perturbation_is_rejected_by_exactly_its_own_guard(
    recordings: list[Recording], perturbation: Perturbation
) -> None:
    """Exactly one, and it is the named one.

    "Exactly" is the load-bearing word twice over. A guard firing on something it was
    not built for is a false positive, and a perturbation caught by a neighbouring
    guard would let the guard under test be dead without anyone noticing.
    """
    failed = {violation.check for violation in _apply(recordings, perturbation)}
    assert failed == {perturbation.guard}, (
        f"{perturbation.name}: expected only {perturbation.guard}, got {sorted(failed)}"
    )


@pytest.mark.parametrize("perturbation", PERTURBATIONS, ids=lambda p: p.name)
def test_the_response_payload_stays_self_consistent(
    recordings: list[Recording], perturbation: Perturbation
) -> None:
    """Except where the disagreement itself is the perturbation.

    Every perturbation but one leaves the (bytes, hash) pair consistent, so the
    raw-integrity guard must stay silent -- otherwise a broken payload, and not the
    guard under test, would be doing the catching. The one exception is the
    perturbation whose whole content is that the pair disagrees.
    """
    recording = corpus.recording_named(recordings, perturbation.fixture)
    base = envelope_of(recording)
    assert base is not None
    perturbed_recording, _ = perturbation.mutate(recording, base)

    agrees = content_hash(perturbed_recording.response_raw) == perturbed_recording.response_hash
    assert agrees is (perturbation.guard != RAW_ROUND_TRIP)


@pytest.mark.parametrize(
    "perturbation",
    [p for p in PERTURBATIONS if p.touches in ("view", "request")],
    ids=lambda p: p.name,
)
def test_a_view_or_request_perturbation_does_not_touch_the_provider_bytes(
    recordings: list[Recording], perturbation: Perturbation
) -> None:
    """The plan's "fails while the raw bytes stay valid", asserted literally."""
    recording = corpus.recording_named(recordings, perturbation.fixture)
    base = envelope_of(recording)
    assert base is not None
    perturbed_recording, _ = perturbation.mutate(recording, base)

    assert perturbed_recording.response_raw == recording.response_raw
    assert perturbed_recording.response_hash == recording.response_hash


@pytest.mark.parametrize("perturbation", PERTURBATIONS, ids=lambda p: p.name)
def test_disabling_the_guard_accepts_the_perturbation(
    recordings: list[Recording], perturbation: Perturbation
) -> None:
    """Guard removal, in process rather than by editing the source.

    This is what the committed evidence records, and why each perturbation is crafted
    to trip one guard: if a second guard also caught it, disabling the first would
    change nothing and the demonstration would be tautological.
    """
    without = frozenset(CHECK_NAMES) - {perturbation.guard}
    assert _apply(recordings, perturbation, enabled=without) == []


def test_with_every_guard_disabled_nothing_is_rejected(recordings: list[Recording]) -> None:
    """The extreme, and the strongest anti-vacuity statement available.

    With no guards at all, every perturbation passes. That rules out the possibility
    that any of the rejections above came from something structural -- a dataclass
    invariant, a decoder refusal -- rather than from the guard that was named.
    """
    for perturbation in PERTURBATIONS:
        assert _apply(recordings, perturbation, enabled=frozenset()) == [], perturbation.name


# -- the recorded evidence ---------------------------------------------------


def _guard_evidence(recordings: list[Recording]) -> dict[str, Any]:
    """Re-derive the guard-removal evidence from the current behaviour."""
    entries: list[dict[str, Any]] = []
    for perturbation in PERTURBATIONS:
        recording = corpus.recording_named(recordings, perturbation.fixture)
        base = envelope_of(recording)
        assert base is not None
        perturbed_recording, perturbed_view = perturbation.mutate(recording, base)
        failing = audit_pair(perturbed_recording, perturbed_view)
        accepted = audit_pair(
            perturbed_recording,
            perturbed_view,
            enabled=frozenset(CHECK_NAMES) - {perturbation.guard},
        )
        entries.append(
            {
                "perturbation": perturbation.name,
                "fixture": perturbation.fixture,
                "guard": perturbation.guard,
                "what": perturbation.what,
                "perturbed_input_sha256": hashlib.sha256(
                    json.dumps(perturbed_view, sort_keys=True, separators=(",", ":")).encode(
                        "utf-8"
                    )
                ).hexdigest(),
                "with_guard": {
                    "rejected": bool(failing),
                    "checks_failed": sorted({violation.check for violation in failing}),
                },
                "without_guard": {
                    "rejected": bool(accepted),
                    "checks_failed": sorted({violation.check for violation in accepted}),
                },
            }
        )

    empty = audit_corpus(Path("/nonexistent-corpus"))
    empty_without = audit_corpus(
        Path("/nonexistent-corpus"), enabled=frozenset(CHECK_NAMES) - {CORPUS_NOT_EMPTY}
    )
    entries.append(
        {
            "perturbation": "empty_the_corpus",
            "fixture": None,
            "guard": CORPUS_NOT_EMPTY,
            "what": "a corpus with no recordings in it",
            "perturbed_input_sha256": None,
            "with_guard": {
                "rejected": not empty.ok,
                "checks_failed": sorted(empty.checks_failed()),
            },
            "without_guard": {
                "rejected": not empty_without.ok,
                "checks_failed": sorted(empty_without.checks_failed()),
            },
        }
    )
    return {
        "schema_version": "1.0",
        "note": (
            "Guard-removal evidence for the Tier A oracle. Re-derived by "
            "tests/oracle/test_fidelity.py on every run, so it cannot drift from the "
            "behaviour it describes. Regenerate with TEMPER_HARNESS_WRITE_GUARD_EVIDENCE=1."
        ),
        "guards": list(CHECK_NAMES),
        "entries": entries,
    }


def test_the_guard_removal_evidence_matches_current_behaviour(
    recordings: list[Recording],
) -> None:
    """The evidence is a claim about behaviour, and it is re-checked every run."""
    derived = _guard_evidence(recordings)
    if os.environ.get(WRITE_ENV):
        EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
        EVIDENCE_FILE.write_text(
            json.dumps(derived, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        pytest.skip(f"wrote {EVIDENCE_FILE} ({WRITE_ENV} is set)")

    assert EVIDENCE_FILE.exists(), f"{EVIDENCE_FILE} is missing; regenerate it"
    committed = json.loads(EVIDENCE_FILE.read_text(encoding="utf-8"))
    assert committed == derived


def test_the_evidence_shows_a_guard_that_bites_for_every_guard() -> None:
    """Reads the committed file, so a hand-emptied corpus of evidence fails here."""
    committed = json.loads(EVIDENCE_FILE.read_text(encoding="utf-8"))
    entries = committed["entries"]
    assert {entry["guard"] for entry in entries} == set(CHECK_NAMES)

    for entry in entries:
        assert entry["with_guard"]["rejected"] is True, entry["perturbation"]
        assert entry["with_guard"]["checks_failed"] == [entry["guard"]], entry["perturbation"]
        assert entry["without_guard"]["rejected"] is False, entry["perturbation"]
        assert entry["without_guard"]["checks_failed"] == [], entry["perturbation"]
        if entry["perturbed_input_sha256"] is not None:
            assert len(entry["perturbed_input_sha256"]) == 64


def test_a_decoder_that_forges_arguments_is_caught_by_the_providers_own_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The one guarantee the view guards have on the shipped path, isolated.

    `envelope_of` is mangled on *both* sides -- the view handed to the oracle and the
    re-derivation it compares against -- so every self-comparison passes. What still
    catches the forgery is the direct read of the provider's own JSON. Without that
    block a decoder could rewrite every tool argument and the oracle would report clean,
    which is exactly the "compared to itself" weakness an adversarial review found here.
    """
    import temper_harness.oracle.fidelity as fidelity

    real_envelope_of = fidelity.envelope_of

    def forging(recording: Recording) -> dict[str, Any] | None:
        envelope = real_envelope_of(recording)
        if envelope is None:
            return None
        for call in envelope.get("tool_calls") or ():
            call["arguments"] = '{"reference": "FORGED"}'
        return envelope

    corpus.build_corpus(tmp_path)
    monkeypatch.setattr(fidelity, "envelope_of", forging)

    report = audit_corpus(tmp_path, decode=forging)
    assert not report.ok
    assert report.checks_failed() == (TYPED_VIEW_FAITHFUL,)


def test_a_corpus_wide_perturbation_reddens_the_whole_audit(tmp_path: Path) -> None:
    """The audit, not just the pair check: a perturbed decode fails the corpus run."""

    def reorder(recording: Recording) -> dict[str, Any] | None:
        envelope = envelope_of(recording)
        if envelope is None or len(envelope.get("tool_calls") or ()) < 2:
            return envelope
        envelope["tool_calls"] = list(reversed(envelope["tool_calls"]))
        return envelope

    corpus.build_corpus(tmp_path)
    assert audit_corpus(tmp_path).ok

    report = audit_corpus(tmp_path, decode=reorder)
    assert not report.ok
    assert report.checks_failed() == (TOOL_CALL_ORDER,)
