"""The committed schema files are the contract, and they must bite.

Every test here fails closed on an empty corpus. A schema suite that iterates
zero samples and reports green is the vacuous-truth failure this repo has
mechanised a gate against, so the anti-vacuity assertions come first.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

from temper_harness.schema_registry import SCHEMA_DIR, build_validator, load_schema

#: The five records R14 names. U1's Definition of Done counts the same five:
#: envelope, usage, error, ledger row, and recording.
EXPECTED_SCHEMAS = (
    "usage.schema.json",
    "ledger_row.schema.json",
    "error.schema.json",
    "envelope.schema.json",
    "recording.schema.json",
    "canary_evidence.schema.json",
)


def _load(name: str) -> dict:
    return load_schema(name)


def _validator(name: str) -> Draft202012Validator:
    return build_validator(name)


def test_schema_directory_is_not_empty() -> None:
    """Anti-vacuity: an empty scan fails rather than reporting clean."""
    found = sorted(p.name for p in SCHEMA_DIR.glob("*.json"))
    assert found, f"no schemas found under {SCHEMA_DIR}"


@pytest.mark.parametrize("name", EXPECTED_SCHEMAS)
def test_each_expected_schema_is_committed_and_valid(name: str) -> None:
    """R14: records are defined by committed files, not inline constants."""
    path = SCHEMA_DIR / name
    assert path.exists(), f"{name} is missing"
    Draft202012Validator.check_schema(_load(name))


def test_no_inline_schema_version_constant() -> None:
    """The predecessor's anti-pattern, asserted absent.

    ``harness-lab/telemetry.py`` carried a module-level version integer as a
    Python constant, so no artefact existed to validate against. The scan
    matches an *assignment* rather than the bare token: a substring scan would
    trip on the sentence that documents the anti-pattern, which is the same
    syntactic-gate weakness this repo has already recorded for its
    raw-rotation-trig check.
    """
    src = Path(__file__).resolve().parents[2] / "src" / "temper_harness"
    # Widened from `^\s*SCHEMA_VERSION\s*=`: a *prefixed* name walked straight past
    # the literal form, and one did -- `EVIDENCE_SCHEMA_VERSION` sat in
    # `canary/runner.py` while this test reported clean. The substance the check is
    # after is "no record's version is a Python literal with no artefact behind it",
    # and the spelling is not the substance.
    assignment = re.compile(r"^\s*\w*SCHEMA_VERSION\s*=", re.MULTILINE)
    offenders = [
        path.relative_to(src).as_posix()
        for path in src.rglob("*.py")
        if assignment.search(path.read_text())
    ]
    assert offenders == []


def _valid_call_row(**overrides) -> dict:
    row = {
        "kind": "call_terminal",
        "seq": 0,
        "lineage": {
            "root_id": "root-1",
            "session_id": "root-session",
            "parent_session_id": None,
            "call_id": "call-1",
            "attempt": 0,
        },
        "status": "ok",
        "served_from": "live",
        "usage": {
            "prompt_tokens": None,
            "completion_tokens": None,
            "reasoning_tokens": None,
            "cached_input_tokens": None,
            "total_tokens": None,
        },
        "usage_source": "unknown",
        "price_table_id": "unpriced",
        "provider_reported_usd": None,
        "estimated_usd": None,
    }
    row.update(overrides)
    return row


def test_a_minimal_call_row_validates() -> None:
    _validator("ledger_row.schema.json").validate(_valid_call_row())


def test_null_usage_is_accepted_and_negative_usage_is_rejected() -> None:
    """R4 lets a field be unknown; it does not let one be impossible."""
    validator = _validator("ledger_row.schema.json")
    validator.validate(_valid_call_row())

    bad = _valid_call_row(
        usage={
            "prompt_tokens": -1,
            "completion_tokens": None,
            "reasoning_tokens": None,
            "cached_input_tokens": None,
        }
    )
    with pytest.raises(ValidationError):
        validator.validate(bad)


def test_unknown_status_and_served_from_values_are_rejected() -> None:
    validator = _validator("ledger_row.schema.json")
    with pytest.raises(ValidationError):
        validator.validate(_valid_call_row(status="maybe-ok"))
    with pytest.raises(ValidationError):
        validator.validate(_valid_call_row(served_from="cached"))


def test_unexpected_fields_are_rejected() -> None:
    """additionalProperties:false keeps a silent extra field from being added
    to a row without a schema change, which is how a schema drifts from its
    data."""
    validator = _validator("ledger_row.schema.json")
    with pytest.raises(ValidationError):
        validator.validate(_valid_call_row(surprise="value"))


def test_the_two_record_kinds_this_slice_writes_validate() -> None:
    """A sample per written kind, so the corpus can never be empty."""
    validator = _validator("ledger_row.schema.json")
    samples = [
        {"kind": "root_opened", "seq": 0, "root_id": "root-1"},
        {
            "kind": "session_registered",
            "seq": 1,
            "root_id": "root-1",
            "session_id": "root-session",
            "parent_session_id": None,
        },
        _valid_call_row(seq=2),
    ]
    for sample in samples:
        validator.validate(sample)


def test_the_aggregates_usage_taxonomy_covers_the_committed_record() -> None:
    """Every field in the committed usage record is classified as additive, breakdown,
    or the provider's own total.

    Without this, `BREAKDOWN_USAGE_FIELDS` would be documentation nobody checks and a
    new usage field could arrive unclassified -- silently summed, or silently ignored.
    """
    from temper_harness.ledger.aggregate import (
        ADDITIVE_USAGE_FIELDS,
        BREAKDOWN_USAGE_FIELDS,
        PROVIDER_TOTAL_FIELD,
    )
    from temper_harness.provider.usage import usage_fields

    classified = set(ADDITIVE_USAGE_FIELDS) | set(BREAKDOWN_USAGE_FIELDS) | {PROVIDER_TOTAL_FIELD}
    assert classified == set(usage_fields())
    # Disjoint: a field that were both additive and a breakdown would be summed twice.
    assert not set(ADDITIVE_USAGE_FIELDS) & set(BREAKDOWN_USAGE_FIELDS)


def test_usage_schema_rejects_missing_required_field() -> None:
    validator = _validator("usage.schema.json")
    validator.validate(
        {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "cached_input_tokens": 0,
            "total_tokens": 0,
        }
    )
    with pytest.raises(ValidationError):
        validator.validate({"prompt_tokens": 0})
