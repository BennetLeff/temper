"""FREEZE spec: ``deterministic/stages/fine_pitch_escape.py``'s two kernels
(``_calculate_min_pin_pitch`` / ``_get_escape_layer_for_net``) (U4 oracle
retirement, batch 2).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/deterministic/stages/_fine_pitch_escape_py_oracle.py
  VERBATIM pin of the pre-migration kernels; the oracle file was created at
  ``1e1243795`` and never touched again — unchanged for 1420 commits as of
  this freeze (measured 2026-08-20 against ``origin/main``), far past the
  plan's 10-consecutive-commit R19-shaped retirement bar.

Kernel:
  packages/temper-design-bundle/src/deterministic_leaves.rs ::
  min_pin_pitch / escape_layer_for_net
  Both are pure ``f64``/string functions — no pyo3 objects in or out — so
  the golden-vector test is plain Rust data + an assert loop, exactly the
  copper_reach / measure_closure FREEZE model. Note the pure
  ``escape_layer_for_net`` takes ``(net_name, layer3_nets, layer2_nets,
  primary, secondary)`` — layer3 BEFORE layer2, mirroring the oracle's
  precedence order but swapping the two set arguments relative to the
  Python-visible ``escape_layer_for_net_py`` (which keeps the oracle's
  ``(layer2_nets, layer3_nets)`` order). The golden test below calls the
  PURE function, so it passes the sets in the pure function's order.

Differential (retired by this same change):
  packages/temper-placer/tests/deterministic/stages/test_fine_pitch_escape_rust_differential.py
  12/12 passed at freeze time (2026-08-20). The file contains ONLY
  oracle-comparison tests of these two kernels — no shipped-module wiring
  check exists. After this freeze the file is reduced to a single pyo3
  wiring check, matching the power_plane retirement in this same batch.

Disposition: FREEZE, not KEEP or REIMPLEMENT.
  - Not a safety kernel: pin-pitch and escape-layer selection are routing
    heuristics, not creepage/clearance/via-keepout geometry (those live in
    temper-drc-rs and are explicitly excluded from this batch).
  - No host-facility or entropy dependency: pure arithmetic
    (``math.sqrt`` via the crate's host_math, direct ``dx*dx`` products,
    ``min`` fold with first-minimum-wins) and string-set membership.
  - Input domain (small float-coordinate lists / short net-name strings +
    two ints) is small and well enumerable — exactly FREEZE's "enumerable
    or samplable" criterion.

Known corpus boundaries (deliberate, documented):
  - The oracle's ``_calculate_min_pin_pitch`` consumes pin OBJECTS with a
    ``.position`` attribute; the freeze marshals them as ``(x, y)`` tuples
    on both arms (the differential's ``_Pin`` wrapper is the same marshal).
  - NaN/inf coordinates are excluded: CPython ``min``/comparison semantics
    vs Rust ``f64`` comparison diverge on them, and the differential never
    tested that input class.

Reproduction / regeneration note: ``run_oracle`` below imports the pinned
oracle module directly so the corpus generation step is byte-for-byte the
oracle's own output. Once this spec has been run and the oracle file
deleted (which happens in the same commit), re-running this generator will
fail with an import error by design — the frozen corpus is meant to be
extended, if ever, by reviving the oracle from git history
(`git show 1e1243795:packages/temper-placer/tests/deterministic/stages/
_fine_pitch_escape_py_oracle.py`) for that one session, not by leaving a
live copy around indefinitely (which would defeat the retirement).
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
        return importlib.import_module("tests.deterministic.stages._fine_pitch_escape_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first: "
            "`git show 1e1243795:packages/temper-placer/tests/deterministic/stages/"
            "_fine_pitch_escape_py_oracle.py > packages/temper-placer/tests/deterministic/"
            "stages/_fine_pitch_escape_py_oracle.py`, run this generator, then discard "
            "the revived file again (it must not be re-committed)."
        ) from exc


class _Pin:
    """The differential's pin-object marshal: ``.position`` only."""

    __slots__ = ("position",)

    def __init__(self, position):
        self.position = position


# ---------------------------------------------------------------------------
# Case model
# ---------------------------------------------------------------------------


def _pitch_case(pins) -> FreezeCase:
    tags = {"kernel:pitch"}
    if len(pins) < 2:
        tags.add("pitch_fewer_than_two")
    else:
        tags.add("pitch_ge_two")
    if len(pins) >= 2 and any(p[0] < 0 or p[1] < 0 for p in pins):
        tags.add("pitch_negative_coords")
    if len(pins) >= 2:
        min_d = None
        for i in range(len(pins)):
            for j in range(i + 1, len(pins)):
                dx = pins[i][0] - pins[j][0]
                dy = pins[i][1] - pins[j][1]
                d = (dx * dx + dy * dy) ** 0.5
                if min_d is None or d < min_d:
                    min_d = d
        if min_d == 0.0:
            tags.add("pitch_identical_pins_zero")
        else:
            tags.add("pitch_min_dist")
    return FreezeCase(
        input={"kernel": "pitch", "pins": pins},
        tags=frozenset(tags),
    )


def _escape_case(net_name, layer2, layer3, primary=1, secondary=2) -> FreezeCase:
    tags = {"kernel:escape"}
    if net_name in layer3:
        tags.add("escape_l3")
    elif net_name in layer2:
        tags.add("escape_l2")
    else:
        tags.add("escape_default")
    if net_name in layer2 and net_name in layer3:
        tags.add("escape_l3_precedence")
    if (primary, secondary) != (1, 2):
        tags.add("escape_custom_layers")
    if net_name == "":
        tags.add("escape_empty_net_name")
    return FreezeCase(
        input={
            "kernel": "escape",
            "net_name": net_name,
            "layer2": layer2,
            "layer3": layer3,
            "primary": primary,
            "secondary": secondary,
        },
        tags=frozenset(tags),
    )


def _curated_cases() -> list[FreezeCase]:
    cases: list[FreezeCase] = []
    # --- pitch: mirrored from the retired differential. ---
    cases.append(_pitch_case([(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]))
    cases.append(_pitch_case([(0.0, 0.0), (0.5, 0.0), (0.25, 0.25)]))
    cases.append(_pitch_case([]))
    cases.append(_pitch_case([(0.0, 0.0)]))
    cases.append(_pitch_case([(1.0, 1.0), (1.0, 1.0)]))
    cases.append(_pitch_case([(0.0, 0.0), (0.0, 0.0), (1.0, 1.0)]))
    cases.append(_pitch_case([(-2.5, 3.5), (-2.5, 3.5), (7.0, 7.0)]))
    cases.append(_pitch_case([(0.1, 0.2), (0.3, 0.4), (1.7, 2.9)]))
    cases.append(_pitch_case([(-1.0, -1.0), (1.0, 1.0), (3.0, -2.0)]))
    cases.append(_pitch_case([(3.0, 4.0), (0.0, 0.0), (6.0, 8.0)]))  # 3-4-5 exact
    cases.append(_pitch_case([(0.0, 0.0), (0.1, 0.0), (0.2, 0.0)]))  # 0.1 bits
    # --- escape: mirrored from the retired differential. ---
    l2 = {"PWM_H", "PWM_L", "SPI_CLK"}
    l3 = {"I_SENSE", "TEMP_SENSE"}
    for net in ["PWM_H", "SPI_CLK", "I_SENSE", "TEMP_SENSE", "GATE_H", "OTHER", ""]:
        cases.append(_escape_case(net, l2, l3))
    cases.append(_escape_case("A", {"A"}, {"B"}))
    cases.append(_escape_case("B", {"A"}, {"B"}))
    cases.append(_escape_case("C", {"A"}, {"B"}))
    cases.append(_escape_case("A", {"A"}, {"B"}, primary=5, secondary=9))
    cases.append(_escape_case("C", {"A"}, {"B"}, primary=5, secondary=9))
    cases.append(_escape_case("X", {"X"}, {"X"}))  # l3 precedence
    return cases


def _random_cases(n: int, seed: int) -> list[FreezeCase]:
    rng = SplitMix64(seed)
    out: list[FreezeCase] = []
    net_pool = ["PWM_H", "SPI_CLK", "I_SENSE", "TEMP_SENSE", "GATE_H", "NET_7", "NET_8", ""]
    for _ in range(n):
        if rng.boolean():
            n_pins = rng.index(5)
            pins = []
            for _p in range(n_pins):
                pins.append((rng.range(-10.0, 10.0), rng.range(-10.0, 10.0)))
            out.append(_pitch_case(pins))
        else:
            l2 = {net_pool[rng.index(len(net_pool))] for _ in range(rng.index(4))}
            l3 = {net_pool[rng.index(len(net_pool))] for _ in range(rng.index(4))}
            net_name = net_pool[rng.index(len(net_pool))]
            primary = rng.index(8) + 1
            secondary = rng.index(8) + 1
            out.append(_escape_case(net_name, l2, l3, primary, secondary))
    return out


def gen_cases() -> list[FreezeCase]:
    return _curated_cases() + _random_cases(40, seed=0xF1E5E)


def run_oracle(case_input: dict):
    oracle = _oracle_module()
    kernel = case_input["kernel"]
    if kernel == "pitch":
        pins = [_Pin(p) for p in case_input["pins"]]
        return oracle._calculate_min_pin_pitch(pins)
    if kernel == "escape":
        return oracle._get_escape_layer_for_net(
            case_input["net_name"],
            case_input["layer2"],
            case_input["layer3"],
            case_input["primary"],
            case_input["secondary"],
        )
    raise ValueError(f"unknown kernel {kernel!r}")


# ---------------------------------------------------------------------------
# Rust rendering
# ---------------------------------------------------------------------------


def _f64(x: float) -> str:
    return rust_f64_literal(x)


def _bits(x: float) -> int:
    return struct.unpack(">Q", struct.pack(">d", x))[0]


def _pins_rs(pins) -> str:
    return ", ".join(f"({_f64(x)}, {_f64(y)})" for x, y in pins)


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    pitch_rows = [r for r in results if r[0].input["kernel"] == "pitch"]
    escape_rows = [r for r in results if r[0].input["kernel"] == "escape"]
    assert pitch_rows and escape_rows, "corpus must cover both kernels"

    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for `min_pin_pitch` / `escape_layer_for_net`")
    lines.append("    /// (FREEZE, batch 2 — retired tests/deterministic/stages/_fine_pitch_escape_py_oracle.py).")
    lines.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec fine_pitch_escape`")
    lines.append("    /// (requires reviving the deleted oracle from git history first -- see")
    lines.append("    /// scripts/oracle_freeze_specs/fine_pitch_escape.py's module docstring).")
    lines.append("    #[cfg(test)]")
    lines.append("    mod frozen_fine_pitch_tests {")
    lines.append("        use super::*;")
    lines.append("        use std::collections::HashSet;")
    lines.append("")
    lines.append("        struct FrozenPitchCase {")
    lines.append("            pins: &'static [(f64, f64)],")
    lines.append("            expected_bits: Option<u64>,")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_PITCH_GOLDEN: &[FrozenPitchCase] = &[")
    for case, output in pitch_rows:
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        exp_rs = "None" if output is None else f"Some({_bits(output):#018x}_u64)"
        lines.append("            FrozenPitchCase {")
        lines.append(f"                pins: &[{_pins_rs(case.input['pins'])}],")
        lines.append(f"                expected_bits: {exp_rs},")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")
    lines.append("        struct FrozenEscapeCase {")
    lines.append("            net_name: &'static str,")
    lines.append("            layer2: &'static [&'static str],")
    lines.append("            layer3: &'static [&'static str],")
    lines.append("            primary: i64,")
    lines.append("            secondary: i64,")
    lines.append("            expected: (i64, &'static str),")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_ESCAPE_GOLDEN: &[FrozenEscapeCase] = &[")
    for case, output in escape_rows:
        inp = case.input
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        l2_rs = ", ".join(f'"{s}"' for s in sorted(inp["layer2"]))
        l3_rs = ", ".join(f'"{s}"' for s in sorted(inp["layer3"]))
        layer, name = output
        lines.append("            FrozenEscapeCase {")
        lines.append(f'                net_name: "{inp["net_name"]}",')
        lines.append(f"                layer2: &[{l2_rs}],")
        lines.append(f"                layer3: &[{l3_rs}],")
        lines.append(f"                primary: {inp['primary']}i64,")
        lines.append(f"                secondary: {inp['secondary']}i64,")
        lines.append(f'                expected: ({layer}i64, "{name}"),')
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")
    lines.append("        #[test]")
    lines.append("        fn frozen_fine_pitch_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_PITCH_GOLDEN {")
    lines.append("                let got = min_pin_pitch(case.pins);")
    lines.append("                let want = case.expected_bits.map(f64::from_bits);")
    lines.append("                let ok = match (got, want) {")
    lines.append("                    (None, None) => true,")
    lines.append("                    (Some(g), Some(w)) => g.to_bits() == w.to_bits(),")
    lines.append("                    _ => false,")
    lines.append("                };")
    lines.append(
        '                assert!(ok, "pitch tags={:?}: got {:?} want {:?}", case.tags, got, want);'
    )
    lines.append("            }")
    lines.append("            for case in FROZEN_ESCAPE_GOLDEN {")
    lines.append("                let l3: HashSet<String> = case.layer3.iter().map(|s| s.to_string()).collect();")
    lines.append("                let l2: HashSet<String> = case.layer2.iter().map(|s| s.to_string()).collect();")
    lines.append("                // NOTE: pure escape_layer_for_net takes (net, l3, l2, primary, secondary).")
    lines.append("                let got = escape_layer_for_net(case.net_name, &l3, &l2, case.primary, case.secondary);")
    lines.append('                assert_eq!(got, case.expected, "escape tags={:?}", case.tags);')
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were")
    lines.append("        /// ever hand-edited down to something trivially satisfiable.")
    lines.append("        #[test]")
    lines.append("        fn frozen_fine_pitch_corpus_is_non_vacuous() {")
    lines.append(
        "            let n = (FROZEN_PITCH_GOLDEN.len() + FROZEN_ESCAPE_GOLDEN.len()) as u32;"
    )
    lines.append(
        '            let count = |tag: &str| FROZEN_PITCH_GOLDEN.iter()'
        ".filter(|c| c.tags.contains(&tag)).count() as u32"
        " + FROZEN_ESCAPE_GOLDEN.iter().filter(|c| c.tags.contains(&tag)).count() as u32;"
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


_NON_VACUITY = [
    NonVacuityCheck(
        tag="kernel:pitch",
        description="pitch golden vectors must be present",
        min_count=8,
    ),
    NonVacuityCheck(
        tag="kernel:escape",
        description="escape golden vectors must be present",
        min_count=8,
    ),
    NonVacuityCheck(
        tag="pitch_fewer_than_two",
        description="<2 pins -> None branch",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="pitch_min_dist",
        description="minimum-distance branch (non-coincident pins)",
        min_count=5,
    ),
    NonVacuityCheck(
        tag="pitch_identical_pins_zero",
        description="coincident pins -> exactly 0.0 (kept, not inf)",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="pitch_negative_coords",
        description="negative coordinates must be exercised",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="escape_l3",
        description="layer-3 (B.Cu) branch",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="escape_l2",
        description="layer-2 (In2.Cu) branch",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="escape_default",
        description="default (In1.Cu) branch",
        min_count=4,
    ),
    NonVacuityCheck(
        tag="escape_custom_layers",
        description="non-default primary/secondary layer parameters",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="escape_l3_precedence",
        description="net in both sets -> layer 3 wins (checked first)",
        min_count=1,
    ),
]


SPEC = FreezeSpec(
    name="fine_pitch_escape",
    description=(
        "deterministic/stages/fine_pitch_escape.py kernels -- _calculate_min_pin_pitch "
        "/ _get_escape_layer_for_net."
    ),
    oracle_provenance=(
        "packages/temper-placer/tests/deterministic/stages/_fine_pitch_escape_py_oracle.py, "
        "pinned at 1e1243795, unchanged 1420 commits as of freeze"
    ),
    kernel_provenance=(
        "packages/temper-design-bundle/src/deterministic_leaves.rs :: "
        "min_pin_pitch / escape_layer_for_net"
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
