"""FREEZE spec: ``deterministic/stages/phased_component_assignment_validator.py``'s
slot-grid kernels (``_infer_slot_spacing`` / ``_build_slot_index`` /
``_slots_within_radius``) (U4 oracle retirement, batch 2).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/deterministic/stages/_phased_component_assignment_validator_py_oracle.py
  VERBATIM pin of the pre-migration slot-grid kernels; the oracle file was
  created at ``2546d5e95`` and never touched again — unchanged for 673
  commits as of this freeze (measured 2026-08-20 against ``origin/main``),
  far past the plan's 10-consecutive-commit R19-shaped retirement bar. (The
  ``_flatten_slots`` kernel is NOT part of this oracle's differential and
  stays Python in the shim.)

Kernel:
  packages/temper-design-bundle/src/deterministic_leaves.rs ::
  infer_slot_spacing / build_slot_index / slots_within_radius
  All three are pure ``f64``/``i64`` list-and-map functions — no pyo3
  objects in or out — so the golden-vector test is plain Rust data + an
  assert loop, exactly the copper_reach / measure_closure FREEZE model.

Differential (retired by this same change):
  packages/temper-placer/tests/deterministic/stages/test_phased_component_assignment_validator_rust_differential.py
  13/13 passed at freeze time (2026-08-20). The file contains ONLY
  oracle-comparison tests of these three kernels — no shipped-module wiring
  check exists (the production validator delegates through the same
  ``deterministic_leaves`` submodule the differential drives). After this
  freeze the file is reduced to a single pyo3 wiring check, matching the
  power_plane retirement in this same batch.

Disposition: FREEZE, not KEEP or REIMPLEMENT.
  - Not a safety kernel: slot-grid bucketing/radius scans are placement
    heuristics, not creepage/clearance/via-keepout geometry (those live in
    temper-drc-rs and are explicitly excluded from this batch).
  - No host-facility or entropy dependency: pure arithmetic
    (``math.hypot`` via the crate's host_math, CPython round-half-to-even
    via ``py_round``, ``ceil``, integer cell keys).
  - Input domain (small float-coordinate lists + two scalars) is small and
    well enumerable — exactly FREEZE's "enumerable or samplable" criterion.

Known corpus boundaries (deliberate, documented):
  - Duplicate -0.0/+0.0 coordinates are excluded: the oracle's ``seen``
    set and ``sorted({...})`` treat them as equal (Python set equality)
    while the Rust kernel's bit-pattern ``slot_key`` and
    ``partial_cmp(...).unwrap_or(Equal)`` keep them distinct — a
    divergence the differential never tested.
  - NaN/inf coordinates are excluded for the same reason
    (``partial_cmp`` vs CPython ``sorted``/``min`` semantics differ).

Reproduction / regeneration note: ``run_oracle`` below imports the pinned
oracle module directly so the corpus generation step is byte-for-byte the
oracle's own output. Once this spec has been run and the oracle file
deleted (which happens in the same commit), re-running this generator will
fail with an import error by design — the frozen corpus is meant to be
extended, if ever, by reviving the oracle from git history
(`git show 2546d5e95:packages/temper-placer/tests/deterministic/stages/
_phased_component_assignment_validator_py_oracle.py`) for that one session,
not by leaving a live copy around indefinitely (which would defeat the
retirement).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

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
    "Reproduction / regeneration note".
    """
    if str(_PLACER_TESTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_PLACER_TESTS_ROOT))
    try:
        return importlib.import_module(
            "tests.deterministic.stages._phased_component_assignment_validator_py_oracle"
        )
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first: "
            "`git show 2546d5e95:packages/temper-placer/tests/deterministic/stages/"
            "_phased_component_assignment_validator_py_oracle.py > packages/temper-placer/"
            "tests/deterministic/stages/_phased_component_assignment_validator_py_oracle.py`, "
            "run this generator, then discard the revived file again (it must not be "
            "re-committed)."
        ) from exc


# ---------------------------------------------------------------------------
# Case model
# ---------------------------------------------------------------------------

_ZERO = 0.0  # canonical positive zero; the corpus must never emit -0.0


def _norm(x: float) -> float:
    """Normalize -0.0 to +0.0 so the corpus stays inside the agreement
    region (Python set/sorted equality vs Rust bit-pattern dedup)."""
    return _ZERO if x == 0.0 else x


def _spacing_case(slots) -> FreezeCase:
    tags = {"kernel:spacing"}
    if len(slots) < 2:
        tags.add("spacing_fallback_degenerate")
    xs = {_norm(s[0]) for s in slots}
    ys = {_norm(s[1]) for s in slots}
    candidates = [b - a for a, b in zip(sorted(xs), sorted(xs)[1:]) if b > a] + [
        b - a for a, b in zip(sorted(ys), sorted(ys)[1:]) if b > a
    ]
    if not candidates:
        tags.add("spacing_fallback_uniform")
    else:
        tags.add("spacing_min_diff")
    return FreezeCase(
        input={"kernel": "spacing", "slots": slots},
        tags=frozenset(tags),
    )


def _index_case(slots, spacing: float) -> FreezeCase:
    tags = {"kernel:index"}
    if not slots:
        tags.add("index_empty")
    keys = {(int(round(_norm(s[0]) / spacing)), int(round(_norm(s[1]) / spacing))) for s in slots}
    if len(keys) >= 2:
        tags.add("index_multi_cell")
    if any(k[0] < 0 or k[1] < 0 for k in keys):
        tags.add("index_negative_key")
    if any(abs(s[0] / spacing) % 1.0 == 0.5 for s in slots) or any(
        abs(s[1] / spacing) % 1.0 == 0.5 for s in slots
    ):
        tags.add("index_half_even")
    return FreezeCase(
        input={"kernel": "index", "slots": slots, "spacing": spacing},
        tags=frozenset(tags),
    )


def _within_case(center, radius: float, slots, spacing: float) -> FreezeCase:
    tags = {"kernel:within"}
    if radius <= 0.0:
        tags.add("within_empty_radius")
    if not slots:
        tags.add("within_empty_index")
    else:
        tags.add("within_nonempty")
    # Inclusive-boundary probe: does any slot sit exactly at `radius`?
    cx, cy = center
    if any((s[0] - cx) ** 2 + (s[1] - cy) ** 2 == radius * radius for s in slots):
        tags.add("within_radius_inclusive")
    return FreezeCase(
        input={
            "kernel": "within",
            "center": center,
            "radius": radius,
            "slots": slots,
            "spacing": spacing,
        },
        tags=frozenset(tags),
    )


def _curated_cases() -> list[FreezeCase]:
    cases: list[FreezeCase] = []
    # --- spacing: mirrored from the retired differential. ---
    for slots in [
        [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 1.0), (1.0, 1.0)],
        [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (0.0, 5.0)],
        [],
        [(1.0, 1.0)],
        [(1.0, 1.0), (2.0, 2.0)],
        [(0.0, 0.0), (0.0, 3.0), (0.0, 6.0)],  # single-column grid
        [(0.0, 0.0), (3.0, 0.0), (8.0, 0.0), (0.0, 5.0)],  # irregular
        [(round(0.1 * i, 6), 0.0) for i in range(5)],  # 0.1-spaced grid
        [(1.0, 2.0), (1.0, 2.0)],  # duplicate slot -> uniform fallback
        [(-3.0, 0.0), (0.0, 0.0), (3.0, 0.0)],  # negative coords
    ]:
        cases.append(_spacing_case(slots))
    # --- index: mirrored from the retired differential. ---
    cases.append(_index_case([(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (0.0, 5.0), (5.1, 5.1)], 5.0))
    cases.append(_index_case([(12.5, 0.0), (12.6, 0.0), (-12.5, 0.0), (-2.5, 0.0)], 5.0))
    cases.append(_index_case([], 5.0))
    cases.append(_index_case([(0.25, 0.25), (0.75, 0.75)], 1.0))
    cases.append(_index_case([(1.0, 1.0), (11.0, 1.0), (1.0, 11.0)], 5.0))
    # Half-even cell-key ratios: x/spacing == k + 0.5 exactly.
    cases.append(_index_case([(10.0, 0.0), (18.0, 0.0), (-14.0, 0.0)], 4.0))
    cases.append(_index_case([(7.5, 7.5), (12.5, 12.5)], 5.0))
    cases.append(_index_case([(3.0, 4.0), (6.0, 8.0), (9.0, 12.0)], 2.0))
    # --- within: mirrored from the retired differential. ---
    cases.append(_within_case((0.0, 0.0), 6.0, [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (0.0, 5.0), (5.0, 5.0)], 5.0))
    cases.append(_within_case((0.0, 0.0), 4.9, [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (0.0, 5.0), (5.0, 5.0)], 5.0))
    cases.append(_within_case((5.0, 5.0), 8.0, [(0.0, 0.0), (5.0, 0.0), (10.0, 0.0), (0.0, 5.0), (5.0, 5.0)], 5.0))
    cases.append(_within_case((0.0, 0.0), 0.0, [(0.0, 0.0), (5.0, 5.0)], 5.0))  # radius 0
    cases.append(_within_case((0.0, 0.0), 1.0, [], 5.0))  # empty index
    cases.append(_within_case((0.0, 0.0), 5.0, [(3.0, 4.0), (10.0, 10.0)], 5.0))  # 3-4-5 inclusive
    cases.append(_within_case((0.5, 0.5), 2.0, [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (0.0, 2.0)], 1.0))
    return cases


def _random_slots(rng: SplitMix64) -> list[tuple[float, float]]:
    n = rng.index(9)
    out = []
    for _ in range(n):
        out.append((_norm(rng.range(-20.0, 20.0)), _norm(rng.range(-20.0, 20.0))))
    return out


def _random_cases(n: int, seed: int) -> list[FreezeCase]:
    rng = SplitMix64(seed)
    out: list[FreezeCase] = []
    for _ in range(n):
        roll = rng.index(3)
        slots = _random_slots(rng)
        spacing = _norm(rng.range(1.0, 10.0))
        if roll == 0:
            out.append(_spacing_case(slots))
        elif roll == 1:
            out.append(_index_case(slots, spacing))
        else:
            radius = _norm(rng.range(0.0, 12.0))
            center = (_norm(rng.range(-10.0, 10.0)), _norm(rng.range(-10.0, 10.0)))
            out.append(_within_case(center, radius, slots, spacing))
    return out


def gen_cases() -> list[FreezeCase]:
    return _curated_cases() + _random_cases(48, seed=0x51D07_61D)


def run_oracle(case_input: dict):
    oracle = _oracle_module()
    kernel = case_input["kernel"]
    if kernel == "spacing":
        return oracle._infer_slot_spacing(case_input["slots"])
    if kernel == "index":
        return oracle._build_slot_index(case_input["slots"], case_input["spacing"])
    if kernel == "within":
        index = oracle._build_slot_index(case_input["slots"], case_input["spacing"])
        return oracle._slots_within_radius(
            case_input["center"], case_input["radius"], index, case_input["spacing"]
        )
    raise ValueError(f"unknown kernel {kernel!r}")


# ---------------------------------------------------------------------------
# Rust rendering
# ---------------------------------------------------------------------------


def _f64(x: float) -> str:
    return rust_f64_literal(x)


def _slots_rs(slots) -> str:
    return ", ".join(f"({_f64(x)}, {_f64(y)})" for x, y in slots)


def _index_output_rs(output) -> str:
    # output: dict {(i,j): [(x,y), ...]} in first-seen order
    parts = []
    for (i, j), cell in output.items():
        parts.append(f"(({i}i64, {j}i64), &[{_slots_rs(cell)}])")
    return ", ".join(parts)


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    spacing_rows = [r for r in results if r[0].input["kernel"] == "spacing"]
    index_rows = [r for r in results if r[0].input["kernel"] == "index"]
    within_rows = [r for r in results if r[0].input["kernel"] == "within"]

    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for the validator slot-grid kernels")
    lines.append("    /// `infer_slot_spacing` / `build_slot_index` / `slots_within_radius` (FREEZE, batch 2).")
    lines.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec slot_grid_validator`")
    lines.append("    /// (requires reviving the deleted oracle from git history first -- see")
    lines.append("    /// scripts/oracle_freeze_specs/slot_grid_validator.py's module docstring).")
    lines.append("    #[cfg(test)]")
    lines.append("    mod frozen_slot_grid_tests {")
    lines.append("        use super::*;")
    lines.append("        use std::collections::HashMap;")
    lines.append("")
    lines.append("        struct FrozenSpacingCase {")
    lines.append("            slots: &'static [(f64, f64)],")
    lines.append("            expected_bits: u64,")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_SPACING_GOLDEN: &[FrozenSpacingCase] = &[")
    for case, output in spacing_rows:
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenSpacingCase {")
        lines.append(f"                slots: &[{_slots_rs(case.input['slots'])}],")
        lines.append(f"                expected_bits: {_bits(output):#018x}_u64,")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")
    lines.append("        struct FrozenIndexCase {")
    lines.append("            slots: &'static [(f64, f64)],")
    lines.append("            spacing: f64,")
    lines.append("            expected: &'static [((i64, i64), &'static [(f64, f64)])],")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_INDEX_GOLDEN: &[FrozenIndexCase] = &[")
    for case, output in index_rows:
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenIndexCase {")
        lines.append(f"                slots: &[{_slots_rs(case.input['slots'])}],")
        lines.append(f"                spacing: {_f64(case.input['spacing'])},")
        lines.append(f"                expected: &[{_index_output_rs(output)}],")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")
    lines.append("        struct FrozenWithinCase {")
    lines.append("            center: (f64, f64),")
    lines.append("            radius: f64,")
    lines.append("            slots: &'static [(f64, f64)],")
    lines.append("            spacing: f64,")
    lines.append("            expected: &'static [(f64, f64)],")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_WITHIN_GOLDEN: &[FrozenWithinCase] = &[")
    for case, output in within_rows:
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenWithinCase {")
        lines.append(
            f"                center: ({_f64(case.input['center'][0])}, {_f64(case.input['center'][1])}),"
        )
        lines.append(f"                radius: {_f64(case.input['radius'])},")
        lines.append(f"                slots: &[{_slots_rs(case.input['slots'])}],")
        lines.append(f"                spacing: {_f64(case.input['spacing'])},")
        lines.append(f"                expected: &[{_slots_rs(output)}],")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")
    lines.append("        #[test]")
    lines.append("        fn frozen_slot_grid_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_SPACING_GOLDEN {")
    lines.append("                let got = infer_slot_spacing(case.slots);")
    lines.append("                let want = f64::from_bits(case.expected_bits);")
    lines.append(
        '                let ok = (got.is_nan() && want.is_nan()) || got.to_bits() == want.to_bits();'
    )
    lines.append(
        '                assert!(ok, "spacing tags={:?}: got {:?} want {:?}", case.tags, got, want);'
    )
    lines.append("            }")
    lines.append("            for case in FROZEN_INDEX_GOLDEN {")
    lines.append("                let got = build_slot_index(case.slots, case.spacing);")
    lines.append("                let want: Vec<((i64, i64), Vec<(f64, f64)>)> = case.expected")
    lines.append("                    .iter().map(|&(k, v)| (k, v.to_vec())).collect();")
    lines.append('                assert_eq!(got, want, "index tags={:?}", case.tags);')
    lines.append("            }")
    lines.append("            for case in FROZEN_WITHIN_GOLDEN {")
    lines.append("                let index: HashMap<(i64, i64), Vec<(f64, f64)>> =")
    lines.append("                    build_slot_index(case.slots, case.spacing).into_iter().collect();")
    lines.append("                let got = slots_within_radius(case.center, case.radius, &index, case.spacing);")
    lines.append("                let want: Vec<(f64, f64)> = case.expected.to_vec();")
    lines.append('                assert_eq!(got, want, "within tags={:?}", case.tags);')
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were")
    lines.append("        /// ever hand-edited down to something trivially satisfiable.")
    lines.append("        #[test]")
    lines.append("        fn frozen_slot_grid_corpus_is_non_vacuous() {")
    lines.append(
        "            let n = (FROZEN_SPACING_GOLDEN.len() + FROZEN_INDEX_GOLDEN.len()"
        " + FROZEN_WITHIN_GOLDEN.len()) as u32;"
    )
    lines.append(
        '            let count = |tag: &str| FROZEN_SPACING_GOLDEN.iter()'
        ".filter(|c| c.tags.contains(&tag)).count() as u32"
        " + FROZEN_INDEX_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32"
        " + FROZEN_WITHIN_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32;"
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
        tag="kernel:spacing",
        description="spacing golden vectors must be present",
        min_count=8,
    ),
    NonVacuityCheck(
        tag="kernel:index",
        description="index golden vectors must be present",
        min_count=6,
    ),
    NonVacuityCheck(
        tag="kernel:within",
        description="within-radius golden vectors must be present",
        min_count=6,
    ),
    NonVacuityCheck(
        tag="spacing_fallback_degenerate",
        description="<2 slots -> DEFAULT_SLOT_SPACING fallback branch",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="spacing_fallback_uniform",
        description="uniform grid (no distinct coords) -> fallback branch",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="spacing_min_diff",
        description="minimum non-zero difference branch",
        min_count=6,
    ),
    NonVacuityCheck(
        tag="index_half_even",
        description="`int(round(x/spacing))` round-half-to-even cell keys",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="index_multi_cell",
        description="multi-cell bucketing must be exercised",
        min_count=5,
    ),
    NonVacuityCheck(
        tag="index_negative_key",
        description="negative cell keys (CPython round ties-to-even on negatives)",
        min_count=1,
    ),
    NonVacuityCheck(
        tag="within_empty_radius",
        description="radius <= 0 -> [] branch",
        min_count=1,
    ),
    NonVacuityCheck(
        tag="within_empty_index",
        description="empty index -> [] branch",
        min_count=1,
    ),
    NonVacuityCheck(
        tag="within_radius_inclusive",
        description="inclusive `<= radius` distance check on an exact-boundary slot",
        min_count=1,
    ),
]


SPEC = FreezeSpec(
    name="slot_grid_validator",
    description=(
        "deterministic/stages/phased_component_assignment_validator.py slot-grid kernels "
        "-- _infer_slot_spacing / _build_slot_index / _slots_within_radius."
    ),
    oracle_provenance=(
        "packages/temper-placer/tests/deterministic/stages/"
        "_phased_component_assignment_validator_py_oracle.py, pinned at 2546d5e95, "
        "unchanged 673 commits as of freeze"
    ),
    kernel_provenance=(
        "packages/temper-design-bundle/src/deterministic_leaves.rs :: "
        "infer_slot_spacing / build_slot_index / slots_within_radius"
    ),
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-design-bundle/src/deterministic_leaves.rs",
    insert_before_marker=(
        "/// Registered as a submodule (`temper_design_bundle_python.deterministic_leaves`)"
    ),
)
