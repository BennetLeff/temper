"""The fidelity oracle: three tiers, only one of which runs in CI.

* **Tier A** (:mod:`temper_harness.oracle.fidelity`) replays the recorded corpus and
  is deterministic. It is a *reproducibility* instrument until Tier B has run, and
  must not be described as a fidelity instrument (R12).
* **Tier B** is the live canary, opt-in, run by hand, evidence hashed and committed.
  It lives in the canary suite rather than here because it needs the network.
* **Tier C** is socket fault injection, and it needs no model at all: it lives in
  the fault suite, because injecting a socket fault is not a property of this
  module.

Keeping the tiers in different places is deliberate. A Tier A oracle that also
tried to be the live instrument would end up with the weaker tier's guarantees
attached to the stronger tier's name, which is exactly the confusion R12 names.
"""

from temper_harness.oracle.fidelity import (
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
    OracleReport,
    Violation,
    assert_faithful,
    audit_corpus,
    audit_pair,
    envelope_of,
    normalized_usage_fields,
)

__all__ = [
    "CHECK_NAMES",
    "CORPUS_NOT_EMPTY",
    "RAW_ROUND_TRIP",
    "REQUEST_IDENTITY",
    "STREAM_FRAMING",
    "TOOL_CALL_ORDER",
    "TYPED_VIEW_FAITHFUL",
    "TYPED_VIEW_VALID",
    "USAGE_PRESENT",
    "USAGE_RECONCILED",
    "FidelityOracleError",
    "OracleReport",
    "Violation",
    "assert_faithful",
    "audit_corpus",
    "audit_pair",
    "envelope_of",
    "normalized_usage_fields",
]
