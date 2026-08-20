"""FREEZE spec: ``regression/measure_closure.py``'s portable compute
(``compute_drc_clearance_pass_pct``) (U4 oracle retirement, batch 1).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/regression/_measure_closure_py_oracle.py
  VERBATIM copy of the pre-migration ``measure_closure.py`` as of commit
  ``0a29f15e3``; the oracle file itself was created (and never touched
  again) at ``de1f6ac9d`` — unchanged for 1489 commits as of this freeze
  (measured 2026-08-20 against ``origin/main``), far past the plan's
  10-consecutive-commit R19-shaped retirement bar.

Kernel:
  packages/temper-design-bundle/src/measure_closure.rs :: compute_drc_clearance_pass_pct
  The three-branch DRC-clearance-pass rule (100.0 clean / max(0, 100 -
  10*errors) with errors / 0.0 below 4 stages). A pure ``(i64, i64) -> f64``
  function — no pyo3 objects in or out — so the golden-vector test is plain
  Rust data + an assert loop, exactly the copper_reach FREEZE model.

Differential (retired by this same change):
  packages/temper-placer/tests/regression/test_measure_closure_rust_differential.py
  The oracle-comparison tests (``test_differential_pct_*``,
  ``test_differential_end_to_end_*`` and the kernel-only MR/prop blocks)
  are removed; the file is reduced to its ``test_shipped_module_delegates_to_rust``
  wiring check, matching the copper_reach precedent. ``measure_closure.py``
  itself is NOT deleted: it is a thin harness over the kept
  ``ClosureTest.run()`` (payload dict assembly, truth gates, the JSON CLI
  the promotion gate shells out to) with only this one portable formula —
  the module stays, the oracle that pinned the pre-migration formula goes.

Disposition: FREEZE, not KEEP or REIMPLEMENT.
  - Not a safety kernel: a measurement heuristic for the SM1/SM2/SM6
    promotion gate, not creepage/clearance/via-keepout geometry (those live
    in temper-drc-rs and are explicitly excluded from this batch).
  - No host-facility or entropy dependency: pure integer arithmetic with an
    exact ``f64`` multiply, a ``max`` clamp, and two constants.
  - Input domain (a pair of small integers) is small and well enumerable —
    exactly FREEZE's "enumerable or samplable" criterion.

Reproduction / regeneration note: ``run_oracle`` below drives the PINNED
oracle module's own ``measure_closure`` (monkeypatching
``ClosureTest.run`` — the closure pipeline itself is out of scope and is
stubbed on both arms, exactly as the differential it replaces did) and
reads ``payload["drc_clearance_pass_pct"]`` out of the oracle's own payload
assembly, so the frozen corpus is byte-for-byte the oracle's output, not a
re-transcription of its formula (transcribing it here would risk the exact
"two copies of the same bug" failure the plan's oracle-disposition table
warns against). Once this spec has been run and the oracle file deleted
(which happens in the same commit), re-running this generator will fail
with an import error by design — the frozen corpus is meant to be extended,
if ever, by reviving the oracle from git history
(`git show de1f6ac9d:packages/temper-placer/tests/regression/
_measure_closure_py_oracle.py`) for that one session, not by leaving a live
copy around indefinitely (which would defeat the retirement).
"""

from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib.oracle_freeze import (  # noqa: E402
    FreezeCase,
    FreezeSpec,
    NonVacuityCheck,
    SplitMix64,
    rust_f64_literal,
)

_PLACER_TESTS_ROOT = Path(__file__).resolve().parent.parent.parent / "packages" / "temper-placer"


def _oracle_module():
    """Import the pinned oracle.

    Expected to fail once the oracle has been retired (this spec's own
    first run deletes it in the same commit) — see the module docstring's
    "Reproduction / regeneration note". Raises a clear, actionable error
    rather than a bare ``ModuleNotFoundError`` so `--check`/regeneration
    attempts after retirement fail with an explanation instead of a stack
    trace.
    """
    if str(_PLACER_TESTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_PLACER_TESTS_ROOT))
    try:
        return importlib.import_module("tests.regression._measure_closure_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first: "
            "`git show de1f6ac9d:packages/temper-placer/tests/regression/"
            "_measure_closure_py_oracle.py > packages/temper-placer/tests/regression/"
            "_measure_closure_py_oracle.py`, run this generator, then discard the revived "
            "file again (it must not be re-committed)."
        ) from exc


def _tags_for(stages: int, errors: int) -> frozenset[str]:
    tags: set[str] = set()
    if stages < 4:
        tags.add("stages_lt_4")
    elif stages == 4:
        tags.add("stages_eq_4")
    else:
        tags.add("stages_gt_4")
    if errors == 0:
        tags.add("errors_zero")
    elif errors < 0:
        tags.add("errors_negative")
    else:
        tags.add("errors_positive")
    if stages >= 4 and errors == 0:
        tags.add("clean_run")
    elif stages >= 4 and 1 <= errors <= 9:
        tags.add("linear_region")
    elif stages >= 4 and errors >= 10:
        tags.add("clamp_region")
    elif stages >= 4 and errors < 0:
        tags.add("unclamped_negative")
    return frozenset(tags)


def _curated_cases() -> list[FreezeCase]:
    cases: list[tuple[str, int, int]] = [
        ("empty_pipeline", 0, 0),
        ("single_stage", 1, 0),
        ("three_stages", 3, 0),
        ("three_stages_many_errors", 3, 50),
        ("boundary_four_clean", 4, 0),
        ("boundary_four_one_error", 4, 1),
        ("boundary_four_nine_errors", 4, 9),
        ("boundary_four_ten_errors_clamp", 4, 10),
        ("boundary_four_twenty_errors_clamp", 4, 20),
        ("five_stages_three_errors", 5, 3),
        ("six_clean", 6, 0),
        ("seven_twelve_errors_clamp", 7, 12),
        ("two_stages_negative_errors", 2, -3),
        ("four_stages_negative_errors_unclamped", 4, -5),
        ("four_stages_negative_one_unclamped", 4, -1),
        ("huge_error_count_clamp", 9, 10_000),
    ]
    out = []
    for name, stages, errors in cases:
        out.append(
            FreezeCase(
                input={"stages": stages, "errors": errors},
                tags=_tags_for(stages, errors) | {f"named:{name}"},
            )
        )
    return out


def _random_cases(n: int, seed: int) -> list[FreezeCase]:
    rng = SplitMix64(seed)
    out: list[FreezeCase] = []
    for _ in range(n):
        stages = rng.range_i64(0, 11)  # 0..10
        special = rng.index(100)
        if special < 20:
            # Bias toward the stages==4 boundary (the formula's hinge).
            stages = 4
        errors_roll = rng.index(100)
        if errors_roll < 18:
            errors = 0
        elif errors_roll < 24:
            errors = -rng.range_i64(1, 6)  # -1..-5, the >100 unclamped zone
        elif errors_roll < 54:
            errors = rng.range_i64(1, 10)  # linear region
        else:
            errors = rng.range_i64(10, 61)  # clamp region incl. 60
        out.append(
            FreezeCase(
                input={"stages": stages, "errors": errors},
                tags=_tags_for(stages, errors),
            )
        )
    return out


def gen_cases() -> list[FreezeCase]:
    return _curated_cases() + _random_cases(80, seed=0xDEAD_BEEF_5EED)


def run_oracle(case_input: dict):
    """Drive the pinned oracle's own ``measure_closure`` with a stubbed
    ``ClosureTest.run`` (the closure pipeline itself is out of scope —
    exactly the differential's own ``_stub_run`` convention) and return the
    ``drc_clearance_pass_pct`` leaf from its payload assembly."""
    oracle = _oracle_module()
    stages = case_input["stages"]
    errors = case_input["errors"]

    result_fields = {
        "stages_exercised": stages,
        "drc_errors": errors,
        "drc_warnings": 0,
        "drc_measured": True,
        "router_completion_pct": 50.0,
        "wall_clock_seconds": 1.0,
        "benders_iterations": 1,
        "passed": True,
        "errors": [],
        "warnings": [],
        "summary": lambda: "frozen-closure-summary",
    }

    def fake_run(self, _observer=None):  # noqa: ANN001, ANN202
        return SimpleNamespace(**result_fields)

    from temper_placer.regression.closure_test import ClosureTest  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as td:
        pcb = Path(td) / "frozen.kicad_pcb"
        pcb.write_text("(kicad_pcb)\n")
        with mock.patch.object(ClosureTest, "run", fake_run):
            payload = oracle.measure_closure(pcb, repo_root=Path(td), strategy="template")
    return float(payload["drc_clearance_pass_pct"])


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for `compute_drc_clearance_pass_pct` (FREEZE, U4/U5).")
    lines.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec measure_closure`")
    lines.append("    /// (requires reviving the deleted oracle from git history first -- see")
    lines.append("    /// scripts/oracle_freeze_specs/measure_closure.py's module docstring).")
    lines.append("    #[cfg(test)]")
    lines.append("    mod frozen_tests {")
    lines.append("        use super::*;")
    lines.append("")
    lines.append("        struct FrozenMeasureClosureCase {")
    lines.append("            stages: i64,")
    lines.append("            errors: i64,")
    lines.append("            expected_bits: u64,")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_MEASURE_CLOSURE_GOLDEN: &[FrozenMeasureClosureCase] = &[")
    for case, output in results:
        ci = case.input
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenMeasureClosureCase {")
        lines.append(f"                stages: {ci['stages']}i64,")
        lines.append(f"                errors: {ci['errors']}i64,")
        lines.append(f"                expected_bits: {_bits(output):#018x}_u64,")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")
    lines.append("        #[test]")
    lines.append("        fn frozen_measure_closure_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_MEASURE_CLOSURE_GOLDEN {")
    lines.append("                let got = compute_drc_clearance_pass_pct(case.stages, case.errors);")
    lines.append("                let want = f64::from_bits(case.expected_bits);")
    lines.append(
        "                let ok = (got.is_nan() && want.is_nan()) || got.to_bits() == want.to_bits();"
    )
    lines.append(
        '                assert!(ok, "tags={:?}: got {:?} want {:?}", case.tags, got, want);'
    )
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were")
    lines.append("        /// ever hand-edited down to something trivially satisfiable. Mirrors the")
    lines.append("        /// coverage-guard convention in creepage_check.rs / via_clearance.rs (PR")
    lines.append("        /// #1007), property_campaigns.rs's IPC-2221 bracket guard, and")
    lines.append("        /// copper_reach.rs's own frozen-corpus guard.")
    lines.append("        #[test]")
    lines.append("        fn frozen_measure_closure_corpus_is_non_vacuous() {")
    lines.append("            let n = FROZEN_MEASURE_CLOSURE_GOLDEN.len() as u32;")
    lines.append(
        "            let count = |tag: &str| FROZEN_MEASURE_CLOSURE_GOLDEN.iter()."
        "filter(|c| c.tags.contains(&tag)).count() as u32;"
    )
    for nvc in _NON_VACUITY:
        if nvc.min_count:
            lines.append(
                f'            assert!(count("{nvc.tag}") >= {nvc.min_count}, '
                f'"{nvc.tag}: only {{}}/{{}} (need >= {nvc.min_count}) -- {nvc.description}", '
                f'count("{nvc.tag}"), n);'
            )
        else:
            pct = int(round(nvc.min_fraction * 100))
            lines.append(
                f'            assert!(count("{nvc.tag}") * 100 >= n * {pct}, '
                f'"{nvc.tag}: only {{}}/{{}} (need >= {pct}%) -- {nvc.description}", '
                f'count("{nvc.tag}"), n);'
            )
    lines.append("        }")
    lines.append("    }")
    return "\n".join(lines)


def _bits(x: float) -> int:
    import struct

    return struct.unpack(">Q", struct.pack(">d", x))[0]


_NON_VACUITY = [
    NonVacuityCheck(
        tag="clean_run",
        description="the 100.0 (stages>=4, errors==0) branch must be exercised",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="linear_region",
        description="the 100 - 10*errors regime (0 < errors < 10) must be exercised",
        min_count=5,
    ),
    NonVacuityCheck(
        tag="clamp_region",
        description="the max(0.0, ...) clamp (errors >= 10) must be exercised",
        min_count=5,
    ),
    NonVacuityCheck(
        tag="unclamped_negative",
        description="the oracle's missing upper clamp (negative errors -> >100) is pinned, not fixed",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="stages_lt_4",
        description="the stages<4 -> 0.0 branch must be exercised",
        min_count=5,
    ),
    NonVacuityCheck(
        tag="stages_eq_4",
        description="the inclusive stages==4 hinge must be exercised",
        min_count=10,
    ),
    NonVacuityCheck(
        tag="errors_zero",
        description="the errors==0 case must be common, not a rare fluke",
        min_fraction=0.10,
    ),
]


SPEC = FreezeSpec(
    name="measure_closure",
    description=(
        "regression/measure_closure.py::compute_drc_clearance_pass_pct -- the "
        "three-branch DRC-clearance-pass formula (100.0 clean / max(0, 100 - "
        "10*errors) / 0.0 below 4 stages)."
    ),
    oracle_provenance=(
        "packages/temper-placer/tests/regression/_measure_closure_py_oracle.py, "
        "VERBATIM from pre-migration commit 0a29f15e3, unchanged 1489 commits "
        "as of freeze (created de1f6ac9d)"
    ),
    kernel_provenance=(
        "packages/temper-design-bundle/src/measure_closure.rs :: "
        "compute_drc_clearance_pass_pct"
    ),
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-design-bundle/src/measure_closure.rs",
    insert_before_marker="/// Register the kernel on the `temper_design_bundle_python` module.",
)
