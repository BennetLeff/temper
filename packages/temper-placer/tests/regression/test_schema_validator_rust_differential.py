"""Wiring check: `regression/schema_validator.py` production shim.

FROZEN 2026-08-20 (U4/U5 of `docs/plans/2026-08-11-003-feat-migration-
pipeline-wire-and-retire-plan.md`, batch 1): the oracle-comparison half of
this differential (the pinned `_schema_validator_py_oracle.py` and the tests
that compared it against `temper_design_bundle_python.validate_schema`,
including the kernel-only MR/prop blocks) has been retired. That comparison
is now a Rust golden-vector regression test —
`frozen_schema_validator_matches_golden_corpus` and its non-vacuity guard
`frozen_schema_validator_corpus_is_non_vacuous` in
`packages/temper-design-bundle/src/schema_validator.rs`'s own
`frozen_tests` module — produced by `scripts/gen_oracle_freeze.py --spec
schema_validator` (`scripts/oracle_freeze_specs/schema_validator.py`
records the full provenance: oracle VERBATIM from pre-migration commit
`0a29f15e3`, unchanged 1489 commits as of freeze — far past the plan's
10-consecutive-commit retirement bar).

What remains here is NOT part of the oracle differential: it is the
production-wiring check (migration-pipeline.md Stage 7 concern, not Stage
8/retire) that the shipped Python module actually calls into Rust rather
than silently keeping a dead Python fallback. FREEZE does not touch this.
`schema_validator.py` itself is NOT deleted: it remains the shim that
formats the kernel's reason codes into exact messages with Python `str()`
(int-vs-float type-carrying), and its import path is pinned inside the
VERBATIM oracle `tests/pipeline/_metrics_observer_py_oracle.py` (whose
bytes cannot be edited).
"""

from __future__ import annotations

import pytest
import temper_design_bundle_python as _tdb

from temper_placer.regression.schema_validator import SchemaValidator as shipped


def test_shipped_module_delegates_to_rust(tmp_path):
    """The SHIPPED entry point must reach Rust, not just the differential.

    A green differential compares the oracle against the kernel and passes
    whether or not production delegates -- this is the assertion that catches
    the RUST-EXISTS-UNWIRED state. The boom on the Rust kernel proves
    ``SchemaValidator.validate`` actually calls it.
    """
    schema = tmp_path / "schema.yaml"
    schema.write_text(
        "metrics:\n"
        "  wall_time_ms:\n"
        "    min: 0\n"
        "    max: 100\n"
        "    zero_is_valid: true\n"
    )

    sentinel = RuntimeError("REACHED_RUST")

    def boom(*_a, **_k):
        raise sentinel

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_tdb, "validate_schema", boom)
    try:
        validator = shipped(schema)
        with pytest.raises(RuntimeError, match="REACHED_RUST"):
            validator.validate({"wall_time_ms": 50.0})
    finally:
        monkeypatch.undo()
