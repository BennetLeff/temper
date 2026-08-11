"""Wiring check: `io/real_board.py::_copper_reach_mm` production shim.

FROZEN 2026-08-11 (U4/U5 of `docs/plans/2026-08-11-003-feat-migration-
pipeline-wire-and-retire-plan.md`): the oracle-comparison half of this
differential (the pinned `_copper_reach_py_oracle.py` and the tests that
compared it against `temper_geometry.copper_reach_mm_py`, including the
NaN/Infinity cases) has been retired. That comparison is now a Rust
golden-vector regression test — `frozen_copper_reach_matches_golden_corpus`
and its non-vacuity guard `frozen_copper_reach_corpus_is_non_vacuous` in
`packages/temper-geometry/src/copper_reach.rs`'s own `mod tests` — produced
by `scripts/gen_oracle_freeze.py --spec copper_reach`
(`scripts/oracle_freeze_specs/copper_reach.py` records the full provenance:
oracle pinned at `d7a22b5d16d4db7d47be39f9d7580921eb9e5263`, unchanged 863
commits; kernel unchanged 182 commits — both far past the plan's
10-consecutive-commit retirement bar). That Rust test carries the same
regression signal this file used to and, unlike this file, is
wasm32-tier-executable (no CPython, no pyo3).

What remains here is NOT part of the oracle differential: it is the
production-wiring check (migration-pipeline.md Stage 7 concern, not Stage
8/retire) that the shipped Python module actually calls into Rust rather
than silently keeping a dead Python fallback. FREEZE does not touch this.
"""

from __future__ import annotations

import pytest

from temper_placer.io import real_board as shipped

pytest.importorskip("temper_geometry")
import temper_geometry as _tg  # noqa: E402


def test_shipped_module_delegates_to_rust():
    """The SHIPPED entry point must reach Rust, not just the differential.

    A green differential compares the oracle against the kernel and passes
    whether or not production delegates -- this is the assertion that catches
    the RUST-EXISTS-UNWIRED state.
    """
    pads = [
        {
            "offset": (3.0, 4.0),
            "width": 1.0,
            "height": 2.0,
            "shape": "rect",
            "roundrect_ratio": 0.25,
        }
    ]
    sentinel = RuntimeError("REACHED_RUST")

    def boom(*_a, **_k):
        raise sentinel

    original = _tg.copper_reach_mm_py
    _tg.copper_reach_mm_py = boom
    try:
        with pytest.raises(RuntimeError, match="REACHED_RUST"):
            shipped._copper_reach_mm(pads, 0.0)
    finally:
        _tg.copper_reach_mm_py = original
