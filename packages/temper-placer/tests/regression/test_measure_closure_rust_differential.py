"""Wiring check: `regression/measure_closure.py` production shim.

FROZEN 2026-08-20 (U4/U5 of `docs/plans/2026-08-11-003-feat-migration-
pipeline-wire-and-retire-plan.md`, batch 1): the oracle-comparison half of
this differential (the pinned `_measure_closure_py_oracle.py` and the tests
that compared it against `temper_design_bundle_python.compute_drc_clearance_pass_pct`,
including the end-to-end payload/truth-gate pairs and the kernel-only MR/prop
blocks) has been retired. That comparison is now a Rust golden-vector
regression test — `frozen_measure_closure_matches_golden_corpus` and its
non-vacuity guard `frozen_measure_closure_corpus_is_non_vacuous` in
`packages/temper-design-bundle/src/measure_closure.rs`'s own `frozen_tests`
module — produced by `scripts/gen_oracle_freeze.py --spec measure_closure`
(`scripts/oracle_freeze_specs/measure_closure.py` records the full
provenance: oracle VERBATIM from pre-migration commit `0a29f15e3`, unchanged
1489 commits as of freeze — far past the plan's 10-consecutive-commit
retirement bar).

What remains here is NOT part of the oracle differential: it is the
production-wiring check (migration-pipeline.md Stage 7 concern, not Stage
8/retire) that the shipped Python module actually calls into Rust rather
than silently keeping a dead Python fallback. FREEZE does not touch this.
`measure_closure.py` itself is NOT deleted: it is a thin harness over the
kept `ClosureTest.run()` (payload dict assembly, the truth gates, the JSON
CLI the promotion gate shells out to) with only this one portable formula —
the module stays, the oracle that pinned the pre-migration formula goes.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import temper_design_bundle_python as _tdb

from temper_placer.regression import measure_closure as shipped
from temper_placer.regression.closure_test import ClosureTest


def test_shipped_module_delegates_to_rust(monkeypatch, tmp_path):
    """The SHIPPED entry point must reach Rust, not just the differential.

    A green differential compares the oracle against the kernel and passes
    whether or not production delegates -- this is the assertion that catches
    the RUST-EXISTS-UNWIRED state. The closure pipeline itself is stubbed
    (``ClosureTest.run``), exactly as the retired differential did; the boom
    on the Rust kernel proves ``measure_closure`` actually calls it.
    """

    def fake_run(self, _observer=None):
        return SimpleNamespace(
            stages_exercised=4,
            drc_errors=1,
            drc_warnings=0,
            drc_measured=True,
            router_completion_pct=50.0,
            wall_clock_seconds=1.0,
            benders_iterations=1,
            passed=True,
            errors=[],
            warnings=[],
            summary=lambda: "frozen-closure-summary",
        )

    monkeypatch.setattr(ClosureTest, "run", fake_run)

    sentinel = RuntimeError("REACHED_RUST")

    def boom(*_a, **_k):
        raise sentinel

    monkeypatch.setattr(_tdb, "compute_drc_clearance_pass_pct", boom)
    pcb = tmp_path / "b.kicad_pcb"
    pcb.write_text("(kicad_pcb)\n")
    with pytest.raises(RuntimeError, match="REACHED_RUST"):
        shipped.measure_closure(pcb, repo_root=tmp_path)
