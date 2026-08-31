"""FREEZE spec: ``deterministic/stages/slot_generation.py``'s
``generate_slots_for_zone`` kernel (U4 oracle retirement, batch 3).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/deterministic/stages/_slot_generation_py_oracle.py
  VERBATIM copy of the pre-migration ``slot_generation.py`` as of commit
  ``16bb2adaa``; unchanged 1617 commits as of this freeze.

Kernel:
  packages/temper-design-bundle/src/deterministic_stages.rs :: generate_slots
  A pure function over 5 f64s returning Vec<(f64, f64)> — the naive += grid
  walk with strict < upper bounds. No pyo3 objects in or out (only the
  PyResult wrapper), so the golden-vector test is plain Rust data + an
  assert loop.

Disposition: FREEZE, not KEEP or REIMPLEMENT.
  - Not a safety kernel: a placement-slot grid generator, not
    creepage/clearance/via/keepout geometry.
  - No host-facility or entropy dependency: pure f64 arithmetic.
  - Input domain (5 floats, small enumerable edge cases) is well suited to
    curated + seeded-volume corpus generation.
"""

from __future__ import annotations

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


class _FakeZone:
    def __init__(self, bounds):
        self.bounds = bounds


def _oracle_module():
    if str(_PLACER_TESTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_PLACER_TESTS_ROOT))
    import importlib
    try:
        return importlib.import_module("tests.deterministic.stages._slot_generation_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first: "
            "`git show 16bb2adaa:packages/temper-placer/tests/deterministic/stages/"
            "_slot_generation_py_oracle.py > packages/temper-placer/tests/deterministic/stages/"
            "_slot_generation_py_oracle.py`, run this generator, then discard the revived "
            "file again (it must not be re-committed)."
        ) from exc


def run_oracle(case_input: dict) -> list:
    oracle = _oracle_module()
    zone = _FakeZone(case_input["bounds"])
    return oracle.generate_slots_for_zone(zone, case_input["spacing"])


def _tags_for(bounds, spacing, output) -> frozenset[str]:
    (x_min, y_min), (x_max, y_max) = bounds
    tags: set[str] = set()
    if not output:
        tags.add("empty")
    if spacing >= max(abs(x_max - x_min), abs(y_max - y_min)):
        tags.add("spacing_exceeds_extent")
    if x_min == x_max or y_min == y_max:
        tags.add("zero_extent")
    if spacing == 0.1:
        tags.add("float_accumulation")
    if x_min < 0 or y_min < 0:
        tags.add("negative_origin")
    w = abs(x_max - x_min)
    h = abs(y_max - y_min)
    if w > 0 and spacing > 0:
        n_x = int((w - spacing / 2) // spacing) + 1
        n_y = int((h - spacing / 2) // spacing) + 1
        if n_x > 0 and n_y > 0 and len(output) == n_x * n_y:
            tags.add("full_grid")
    if spacing in (2.0, 5.0) and w > 0 and h > 0:
        if (w / spacing) % 1 == 0 or (h / spacing) % 1 == 0:
            tags.add("boundary_landing")
    return frozenset(tags)


def _tagged_case(name, bounds, spacing):
    output = run_oracle({"bounds": bounds, "spacing": spacing})
    tags = _tags_for(bounds, spacing, output)
    if name is not None:
        tags = tags | {f"named:{name}"}
    return FreezeCase(input={"bounds": bounds, "spacing": spacing}, tags=tags)


def _curated_cases() -> list[FreezeCase]:
    cases = [
        ("basic_grid_2", ((0, 0), (10, 10)), 2.0),
        ("basic_grid_5", ((0, 0), (10, 10)), 5.0),
        ("offset_grid", ((1.5, -2.5), (12.5, 7.5)), 2.5),
        ("empty_spacing_exceeds", ((0, 0), (1, 1)), 5.0),
        ("empty_zero_extent", ((2, 2), (2, 2)), 1.0),
        ("empty_zero_extent_x", ((5, 0), (5, 10)), 2.0),
        ("empty_zero_extent_y", ((0, 3), (10, 3)), 2.0),
        ("empty_zero_extent_both", ((0, 0), (0, 0)), 1.0),
        ("strict_upper_5x3", ((0.0, 0.0), (5.0, 3.0)), 2.0),
        ("strict_upper_5x5", ((0.0, 0.0), (5.0, 5.0)), 2.0),
        ("strict_upper_3x5", ((0.0, 0.0), (3.0, 5.0)), 2.0),
        ("negative_origin_strict", ((-2.0, -2.0), (5.0, 5.0)), 2.0),
        ("float_acc_01", ((0, 0), (1, 1)), 0.1),
        ("float_acc_offset", ((0.05, 0.05), (0.95, 0.95)), 0.1),
        ("negative_origin", ((-5, -5), (5, 5)), 2.0),
        ("negative_fractional", ((-1.3, -2.7), (0.1, 3.3)), 0.5),
        ("large_spacing_small_zone", ((0, 0), (3, 3)), 10.0),
        ("spacing_equals_extent_x", ((0, 0), (5, 10)), 5.0),
        ("spacing_equals_extent_y", ((0, 0), (10, 5)), 5.0),
        ("tiny_spacing", ((0, 0), (0.5, 0.5)), 0.01),
        ("wide_zone", ((0, 0), (100, 1)), 10.0),
        ("tall_zone", ((0, 0), (1, 100)), 10.0),
        ("spacing_025", ((0, 0), (1, 1)), 0.25),
        ("spacing_075", ((0, 0), (3, 3)), 0.75),
        ("spacing_125", ((0, 0), (5, 5)), 1.25),
    ]
    return [_tagged_case(name, bounds, spacing) for name, bounds, spacing in cases]


def _random_cases(n: int, seed: int) -> list[FreezeCase]:
    import random
    rng = random.Random(seed)
    spacing_choices = [0.1, 0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.5]
    out: list[FreezeCase] = []
    for _ in range(n):
        x_min = rng.uniform(-50, 0)
        y_min = rng.uniform(-50, 0)
        w = rng.uniform(0.0, 50)
        h = rng.uniform(0.0, 50)
        spacing = rng.choice(spacing_choices)
        out.append(_tagged_case(None, ((x_min, y_min), (x_min + w, y_min + h)), spacing))
    return out


def gen_cases() -> list[FreezeCase]:
    return _curated_cases() + _random_cases(80, seed=21)


_NON_VACUITY = [
    NonVacuityCheck(
        tag="full_grid",
        description="the normal non-empty grid case must dominate the corpus",
        min_fraction=0.40,
    ),
    NonVacuityCheck(
        tag="empty",
        description="the empty-result branch (spacing >= extent) must be exercised",
        min_count=5,
    ),
    NonVacuityCheck(
        tag="float_accumulation",
        description="naive += accumulation with non-exact spacing must be exercised",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="negative_origin",
        description="negative-origin zones must be exercised",
        min_count=5,
    ),
    NonVacuityCheck(
        tag="boundary_landing",
        description="cases where the lattice lands exactly on the boundary (strict < test)",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="zero_extent",
        description="zero-extent zones must be exercised",
        min_count=2,
    ),
]


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for `generate_slots` (FREEZE, U4/U5, batch 3).")
    lines.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec slot_generation`")
    lines.append("    /// (requires reviving the deleted oracle from git history first -- see")
    lines.append("    /// scripts/oracle_freeze_specs/slot_generation.py's module docstring).")
    lines.append("    #[cfg(test)]")
    lines.append("    mod frozen_slot_generation_tests {")
    lines.append("        use super::*;")
    lines.append("")
    lines.append("        struct FrozenSlotCase {")
    lines.append("            x_min: f64,")
    lines.append("            y_min: f64,")
    lines.append("            x_max: f64,")
    lines.append("            y_max: f64,")
    lines.append("            spacing: f64,")
    lines.append("            expected: &'static [(f64, f64)],")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_SLOT_GENERATION_GOLDEN: &[FrozenSlotCase] = &[")
    for case, output in results:
        ci = case.input
        (x_min, y_min), (x_max, y_max) = ci["bounds"]
        spacing = ci["spacing"]
        expected_rs = ", ".join(
            f"({rust_f64_literal(x)}, {rust_f64_literal(y)})" for x, y in output
        )
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenSlotCase {")
        lines.append(f"                x_min: {rust_f64_literal(float(x_min))},")
        lines.append(f"                y_min: {rust_f64_literal(float(y_min))},")
        lines.append(f"                x_max: {rust_f64_literal(float(x_max))},")
        lines.append(f"                y_max: {rust_f64_literal(float(y_max))},")
        lines.append(f"                spacing: {rust_f64_literal(float(spacing))},")
        lines.append(f"                expected: &[{expected_rs}],")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")
    lines.append("        #[test]")
    lines.append("        fn frozen_slot_generation_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_SLOT_GENERATION_GOLDEN {")
    lines.append("                let got = generate_slots(")
    lines.append("                    case.x_min, case.y_min, case.x_max, case.y_max, case.spacing,")
    lines.append("                );")
    lines.append('                assert_eq!(got, case.expected, "tags={:?}", case.tags);')
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were")
    lines.append("        /// ever hand-edited down to something trivially satisfiable.")
    lines.append("        #[test]")
    lines.append("        fn frozen_slot_generation_corpus_is_non_vacuous() {")
    lines.append("            let n = FROZEN_SLOT_GENERATION_GOLDEN.len() as u32;")
    lines.append("            let count = |tag: &str| FROZEN_SLOT_GENERATION_GOLDEN.iter()")
    lines.append("                .filter(|c| c.tags.contains(&tag)).count() as u32;")
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


SPEC = FreezeSpec(
    name="slot_generation",
    description=(
        "deterministic/stages/slot_generation.py::generate_slots_for_zone -- "
        "the naive += grid walk with strict < upper bounds."
    ),
    oracle_provenance=(
        "packages/temper-placer/tests/deterministic/stages/_slot_generation_py_oracle.py, "
        "VERBATIM from pre-migration commit 16bb2adaa, unchanged 1617 commits "
        "as of freeze"
    ),
    kernel_provenance=(
        "packages/temper-design-bundle/src/deterministic_stages.rs :: generate_slots"
    ),
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-design-bundle/src/deterministic_stages.rs",
    insert_before_marker="    #[test]",
)
