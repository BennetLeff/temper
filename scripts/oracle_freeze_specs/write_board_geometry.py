"""FREEZE spec: ``io/_write_board.py``'s two numeric kernels
(``reorient_pad_angle`` / ``preserve_rotation_offset``) (U4 oracle
retirement, batch 2).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/io/_write_board_py_oracle.py
  VERBATIM pin (statement-level extraction) of the two numeric kernels
  embedded in ``temper_placer/io/_write_board.py`` at commit ``550cab2a3``;
  the oracle file itself was created at ``37e536d67`` and never touched
  again — unchanged for 1322 commits as of this freeze (measured
  2026-08-20 against ``origin/main``), far past the plan's 10-consecutive-
  commit R19-shaped retirement bar.

Kernel:
  packages/temper-design-bundle/src/write_board_geometry.rs ::
  reorient_pad_angle / reorient_pad_angles / preserve_rotation_offset
  Both kernels are pure ``f64`` arithmetic over ``Option<f64>`` scalars —
  no pyo3 objects in or out — so the golden-vector test is plain Rust data
  + an assert loop, exactly the copper_reach / measure_closure FREEZE
  model. The one non-ported oracle function, ``reorient_delta_is_noop``
  (``delta % 360.0 == 0.0``), is caller-side control flow with NO Rust
  kernel (see write_board_geometry.rs's module docstring); its semantics
  are folded into the reorient corpus as ``noop_delta`` tags (a noop delta
  must produce ``None``) rather than golden vectors of their own.

Differential (retired by this same change):
  packages/temper-placer/tests/io/test_write_board_geometry_rust_differential.py
  32/32 passed at freeze time (2026-08-20). The oracle-comparison tests
  (``test_reorient_pad_angle_matches_oracle_bit_exact`` and its named
  siblings, ``test_reorient_delta_is_noop_matches_oracle``, and the
  ``preserve_rotation_offset`` parametrized/named blocks) are removed,
  because their job is now done by the Rust golden-vector test; the two
  ``test_*_delegates_to_rust`` wiring checks in that file are NOT part of
  the oracle differential (they assert production wiring, Stage 7 concern)
  and are intentionally left in place.

Disposition: FREEZE, not KEEP or REIMPLEMENT.
  - Not a safety kernel: pad-angle wrap and rotation-offset preservation
    are KiCad-formatting conveniences, not creepage/clearance/via-keepout
    geometry (those live in temper-drc-rs and are explicitly excluded from
    this batch).
  - No host-facility or entropy dependency: pure ``f64`` arithmetic
    (floored modulo via ``py_float_mod``, round-half-to-even via
    ``py_round``) with no dlsym/libm boundary crossing.
  - Input domain (two scalars) is small and well enumerable — exactly
    FREEZE's "enumerable or samplable" criterion.

Reproduction / regeneration note: ``run_oracle`` below imports the pinned
oracle module directly so the corpus generation step is byte-for-byte the
oracle's own output, not a re-transcription of it. Once this spec has been
run and the oracle file deleted (which happens in the same commit),
re-running this generator will fail with an import error by design — the
frozen corpus is meant to be extended, if ever, by reviving the oracle from
git history (`git show 37e536d67:packages/temper-placer/tests/io/
_write_board_py_oracle.py`) for that one session, not by leaving a live
copy around indefinitely (which would defeat the retirement).
"""

from __future__ import annotations

import importlib
import struct
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
        return importlib.import_module("tests.io._write_board_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first: "
            "`git show 37e536d67:packages/temper-placer/tests/io/"
            "_write_board_py_oracle.py > packages/temper-placer/tests/io/"
            "_write_board_py_oracle.py`, run this generator, then discard the revived "
            "file again (it must not be re-committed)."
        ) from exc


# ---------------------------------------------------------------------------
# Case model: a plain dict {"kernel": ..., ...params...}
# ---------------------------------------------------------------------------


def _reorient(current_angle, delta_deg) -> FreezeCase:
    tags = {"kernel:reorient"}
    if current_angle is None:
        tags.add("none_current")
    elif current_angle == 0.0:
        tags.add("zero_current")
    if delta_deg < 0.0:
        tags.add("negative_delta")
    if abs(delta_deg) >= 360.0:
        tags.add("multi_turn_delta")
    if delta_deg % 360.0 == 0.0:
        tags.add("noop_delta")
    return FreezeCase(
        input={"kernel": "reorient", "current": current_angle, "delta": delta_deg},
        tags=frozenset(tags),
    )


def _preserve(rotation_deg, original_angle) -> FreezeCase:
    tags = {"kernel:preserve"}
    quantized = round(original_angle / 90.0) * 90.0
    offset = original_angle - quantized
    if offset == 0.0:
        tags.add("exact_90_multiple")
    if original_angle % 90.0 == 45.0:
        tags.add("half_even_tie")
    if abs(offset) > 0.1:
        tags.add("threshold_applied")
    else:
        tags.add("threshold_not_applied")
    if original_angle < 0.0:
        tags.add("negative_original")
    if (rotation_deg + offset) >= 360.0 or (rotation_deg + offset) < 0.0:
        tags.add("wrap_after_offset")
    return FreezeCase(
        input={"kernel": "preserve", "rotation": rotation_deg, "original": original_angle},
        tags=frozenset(tags),
    )


def _curated_cases() -> list[FreezeCase]:
    cases: list[FreezeCase] = []
    # --- reorient: mirrored from the retired differential's parametrization,
    # plus the semantic families the differential's named tests covered. ---
    for current, delta in [
        (None, 90.0),
        (0.0, 90.0),
        (10.0, 90.0),
        (270.0, 90.0),  # wraps past 360 -> 0.0 -> None
        (0.0, -90.0),  # negative delta, CPython floored-mod sign quirk
        (10.0, -90.0),
        (350.0, 20.0),  # 370 % 360 == 10.0
        (45.0, 315.0),  # exact multiple -> 0.0 -> None
        (None, -90.0),  # None -> 0.0 -> -90 % 360 == 270.0
        (0.0, -720.0),  # exact-multiple negative delta: CPython gives +0.0
        (123.456, 37.125),
        (359.999, 0.002),  # crosses 360 by a hair
        (0.0, 360.0),  # exact multiple positive -> None
        (0.0, -360.0),
        (720.0, 90.0),  # current already wrapped past 360
        (-180.0, 90.0),  # negative current: -180 + 90 = -90 % 360 == 270.0
        (-90.0, -90.0),  # -180 % 360 == 180.0
        (None, 0.0),  # None current, zero delta -> 0.0 -> None
        (1e-12, -1e-12),  # sub-ulp pair -> exactly 0.0 -> None
    ]:
        cases.append(_reorient(current, delta))
    # --- preserve: mirror the retired differential's parametrization. ---
    for rotation, original in [
        (0.0, 90.0),  # exactly on a 90-multiple: no offset applied
        (0.0, 45.0),  # round-half-to-even TIE: round(0.5) -> 0 (even)
        (180.0, 135.0),  # TIE: round(1.5) -> 2 (even) -> quantized 180
        (180.0, 225.0),  # TIE: round(2.5) -> 2 (even) -> quantized 180
        (0.0, 315.0),  # TIE: round(3.5) -> 4 (even) -> quantized 360
        (90.0, 46.0),  # small offset > 0.1 threshold
        (0.0, 0.05),  # offset below the 0.1 threshold: NOT applied
        (270.0, -10.0),  # negative original angle
        (0.0, 359.95),  # near-360 wrap after offset application
        (90.0, 91.0),
        (90.0, 90.1),  # |offset| exactly 0.1: excluded (strict >)
        (0.0, 0.1),  # exact threshold tie, quantized 0 -> offset 0.1 exactly
        (270.0, 269.0),  # wrap after offset: 270 + (-1) % 360 == 269.0
        (0.0, 405.0),  # original > 360: 405/90 == 4.5 -> round -> 4 -> 360
        (180.0, -45.0),  # negative tie: round(-0.5) -> 0 (even) -> offset -45
    ]:
        cases.append(_preserve(rotation, original))
    return cases


def _random_cases(n: int, seed: int) -> list[FreezeCase]:
    rng = SplitMix64(seed)
    out: list[FreezeCase] = []
    for _ in range(n):
        if rng.boolean():
            # reorient: 1-in-5 None current; deltas mostly in (-720, 720).
            current = None if rng.index(5) == 0 else rng.range(-720.0, 720.0)
            delta = rng.range(-720.0, 720.0)
            out.append(_reorient(current, delta))
        else:
            rotation = rng.range(-360.0, 360.0)
            # original angles biased toward the 0..360 band where the
            # quantized-90 lattice and its 45-degree ties live.
            original = rng.range(-90.0, 450.0)
            out.append(_preserve(rotation, original))
    return out


def gen_cases() -> list[FreezeCase]:
    return _curated_cases() + _random_cases(40, seed=0xBAAD_F00D)


def run_oracle(case_input: dict):
    oracle = _oracle_module()
    kernel = case_input["kernel"]
    if kernel == "reorient":
        return oracle.reorient_pad_angle(case_input["current"], case_input["delta"])
    if kernel == "preserve":
        return oracle.preserve_rotation_offset(case_input["rotation"], case_input["original"])
    raise ValueError(f"unknown kernel {kernel!r}")


# ---------------------------------------------------------------------------
# Rust rendering
# ---------------------------------------------------------------------------


def _f64_bits(x: float) -> int:
    return struct.unpack(">Q", struct.pack(">d", x))[0]


def _opt_bits(v) -> str:
    if v is None:
        return "None"
    return f"Some({_f64_bits(v):#018x}_u64)"


def _render_reorient(case: FreezeCase, output) -> str:
    inp = case.input
    current = inp["current"]
    current_rs = "None" if current is None else f"Some({rust_f64_literal(current)})"
    tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
    return (
        "        FrozenReorientCase {\n"
        f"            current_angle: {current_rs},\n"
        f"            delta_deg: {rust_f64_literal(inp['delta'])},\n"
        f"            expected_bits: {_opt_bits(output)},\n"
        f"            tags: &[{tags_rs}],\n"
        "        },"
    )


def _render_preserve(case: FreezeCase, output) -> str:
    inp = case.input
    tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
    return (
        "        FrozenPreserveCase {\n"
        f"            rotation_deg: {rust_f64_literal(inp['rotation'])},\n"
        f"            original_angle: {rust_f64_literal(inp['original'])},\n"
        f"            expected_bits: {_f64_bits(output):#018x}_u64,\n"
        f"            tags: &[{tags_rs}],\n"
        "        },"
    )


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    reorient_rows = [r for r in results if r[0].input["kernel"] == "reorient"]
    preserve_rows = [r for r in results if r[0].input["kernel"] == "preserve"]
    assert reorient_rows and preserve_rows, "corpus must cover both kernels"

    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for `reorient_pad_angle` / `preserve_rotation_offset`")
    lines.append("    /// (FREEZE, batch 2 — retired tests/io/_write_board_py_oracle.py).")
    lines.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec write_board_geometry`")
    lines.append("    /// (requires reviving the deleted oracle from git history first -- see")
    lines.append("    /// scripts/oracle_freeze_specs/write_board_geometry.py's module docstring).")
    lines.append("    struct FrozenReorientCase {")
    lines.append("        current_angle: Option<f64>,")
    lines.append("        delta_deg: f64,")
    lines.append("        expected_bits: Option<u64>,")
    lines.append("        tags: &'static [&'static str],")
    lines.append("    }")
    lines.append("")
    lines.append("    const FROZEN_REORIENT_GOLDEN: &[FrozenReorientCase] = &[")
    for case, output in reorient_rows:
        lines.append(_render_reorient(case, output))
    lines.append("    ];")
    lines.append("")
    lines.append("    struct FrozenPreserveCase {")
    lines.append("        rotation_deg: f64,")
    lines.append("        original_angle: f64,")
    lines.append("        expected_bits: u64,")
    lines.append("        tags: &'static [&'static str],")
    lines.append("    }")
    lines.append("")
    lines.append("    const FROZEN_PRESERVE_GOLDEN: &[FrozenPreserveCase] = &[")
    for case, output in preserve_rows:
        lines.append(_render_preserve(case, output))
    lines.append("    ];")
    lines.append("")
    lines.append("    #[test]")
    lines.append("    fn frozen_write_board_geometry_matches_golden_corpus() {")
    lines.append("        for case in FROZEN_REORIENT_GOLDEN {")
    lines.append("            let got = reorient_pad_angle(case.current_angle, case.delta_deg);")
    lines.append("            let want = case.expected_bits.map(f64::from_bits);")
    lines.append("            let ok = match (got, want) {")
    lines.append("                (None, None) => true,")
    lines.append("                (Some(g), Some(w)) => (g.is_nan() && w.is_nan()) || g.to_bits() == w.to_bits(),")
    lines.append("                _ => false,")
    lines.append("            };")
    lines.append(
        '            assert!(ok, "reorient tags={:?}: got {:?} want {:?}", case.tags, got, want);'
    )
    lines.append("        }")
    lines.append("        for case in FROZEN_PRESERVE_GOLDEN {")
    lines.append("            let got = preserve_rotation_offset(case.rotation_deg, case.original_angle);")
    lines.append("            let want = f64::from_bits(case.expected_bits);")
    lines.append(
        "            let ok = (got.is_nan() && want.is_nan()) || got.to_bits() == want.to_bits();"
    )
    lines.append(
        '            assert!(ok, "preserve tags={:?}: got {:?} want {:?}", case.tags, got, want);'
    )
    lines.append("        }")
    lines.append("    }")
    lines.append("")
    lines.append("    /// Q2 non-vacuity guard: fails closed if the frozen corpus above were")
    lines.append("    /// ever hand-edited down to something trivially satisfiable.")
    lines.append("    #[test]")
    lines.append("    fn frozen_write_board_geometry_corpus_is_non_vacuous() {")
    lines.append("        let n = (FROZEN_REORIENT_GOLDEN.len() + FROZEN_PRESERVE_GOLDEN.len()) as u32;")
    lines.append(
        '        let count = |tag: &str| FROZEN_REORIENT_GOLDEN.iter()'
        ".filter(|c| c.tags.contains(&tag)).count() as u32"
        " + FROZEN_PRESERVE_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32;"
    )
    for nvc in _NON_VACUITY:
        if nvc.min_count:
            lines.append(
                f'        assert!(count("{nvc.tag}") >= {nvc.min_count}, '
                f'"{nvc.tag}: only {{}}/{{}} (need >= {nvc.min_count}) -- {nvc.description}", '
                f'count("{nvc.tag}"), n);'
            )
        else:
            pct = int(round(nvc.min_fraction * 100))
            lines.append(
                f'        assert!(count("{nvc.tag}") * 100 >= n * {pct}, '
                f'"{nvc.tag}: only {{}}/{{}} (need >= {pct}%) -- {nvc.description}", '
                f'count("{nvc.tag}"), n);'
            )
    lines.append("    }")
    return "\n".join(lines)


_NON_VACUITY = [
    NonVacuityCheck(
        tag="kernel:reorient",
        description="reorient golden vectors must be present",
        min_count=10,
    ),
    NonVacuityCheck(
        tag="kernel:preserve",
        description="preserve golden vectors must be present",
        min_count=10,
    ),
    NonVacuityCheck(
        tag="none_current",
        description="`current_angle or 0.0` None-coalescing must be exercised",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="negative_delta",
        description="CPython floored-mod sign semantics must be exercised",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="noop_delta",
        description="`delta % 360 == 0` -> None (reorient_delta_is_noop contract)",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="half_even_tie",
        description="round-half-to-even quantization ties (45/135/225/315...)",
        min_count=4,
    ),
    NonVacuityCheck(
        tag="threshold_applied",
        description="|offset| > 0.1 adjustment branch",
        min_count=4,
    ),
    NonVacuityCheck(
        tag="threshold_not_applied",
        description="|offset| <= 0.1 pass-through branch",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="wrap_after_offset",
        description="final `% 360.0` wrap after offset application",
        min_count=2,
    ),
]


SPEC = FreezeSpec(
    name="write_board_geometry",
    description="io/_write_board.py::_reorient_pads per-pad angle + state_to_placements rotation-offset kernels.",
    oracle_provenance=(
        "packages/temper-placer/tests/io/_write_board_py_oracle.py, pinned at "
        "550cab2a3, unchanged 1322 commits as of freeze"
    ),
    kernel_provenance=(
        "packages/temper-design-bundle/src/write_board_geometry.rs :: "
        "reorient_pad_angle / reorient_pad_angles / preserve_rotation_offset"
    ),
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-design-bundle/src/write_board_geometry.rs",
    insert_before_marker="    #[test]",
)
