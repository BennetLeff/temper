"""FREEZE spec: ``deterministic/stages/power_plane.py``'s reassignment
kernel (``recompute_plane_assignments``) (U4 oracle retirement, batch 2).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/deterministic/stages/_power_plane_py_oracle.py
  VERBATIM pin of the pre-migration ``PowerPlaneStage.run`` reassignment
  loop; the oracle file was created at ``19ddfc1fe`` and never touched
  again — unchanged for 1442 commits as of this freeze (measured
  2026-08-20 against ``origin/main``), far past the plan's 10-consecutive-
  commit R19-shaped retirement bar.

Kernel:
  packages/temper-design-bundle/src/deterministic_leaves.rs ::
  recompute_plane_assignments
  A pure ``(&[(String, i64, bool, bool)], &[String], &HashMap<String, i64>,
  &[String]) -> Vec<(String, i64, bool, bool)>`` function — no pyo3 objects
  in or out — so the golden-vector test is plain Rust data + an assert
  loop, exactly the copper_reach / measure_closure FREEZE model.

Differential (retired by this same change):
  packages/temper-placer/tests/deterministic/stages/test_power_plane_rust_differential.py
  11/11 passed at freeze time (2026-08-20). The file contains ONLY
  oracle-comparison tests of this one kernel — no shipped-module wiring
  check exists for ``recompute_plane_assignments`` (the production
  ``PowerPlaneStage.run`` delegates through the same
  ``deterministic_leaves`` submodule the differential drives; there is no
  separate entry point to wire-proof). After this freeze the file is
  reduced to a short header pointing at the frozen corpus, matching the
  copper_reach precedent of removing oracle-comparison tests entirely.

Disposition: FREEZE, not KEEP or REIMPLEMENT.
  - Not a safety kernel: plane-net layer reassignment is a routing-layout
    heuristic, not creepage/clearance/via-keepout geometry (those live in
    temper-drc-rs and are explicitly excluded from this batch).
  - No host-facility or entropy dependency: pure integer/string/boolean
    list-and-set logic with two ``unwrap_or(1)`` fallbacks.
  - Input domain (four small lists/mappings of strings and ints) is small
    and well enumerable — exactly FREEZE's "enumerable or samplable"
    criterion.

Known boundary of the frozen corpus (deliberate): the oracle collapses
duplicate net names in ``existing_assignments`` through its
``{a.net_name: a for a in existing_assignments}`` dict, while the Rust
kernel iterates the ``existing`` slice directly — the two arms DIVERGE on
duplicate net names, and the differential never tested that input class.
The corpus therefore excludes duplicates (a freeze of that class would
fail the golden test by construction). If the divergence is ever resolved,
the corpus can be extended.

Reproduction / regeneration note: ``run_oracle`` below imports the pinned
oracle module directly so the corpus generation step is byte-for-byte the
oracle's own output. Once this spec has been run and the oracle file
deleted (which happens in the same commit), re-running this generator will
fail with an import error by design — the frozen corpus is meant to be
extended, if ever, by reviving the oracle from git history
(`git show 19ddfc1fe:packages/temper-placer/tests/deterministic/stages/
_power_plane_py_oracle.py`) for that one session, not by leaving a live
copy around indefinitely (which would defeat the retirement).
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
        return importlib.import_module("tests.deterministic.stages._power_plane_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first: "
            "`git show 19ddfc1fe:packages/temper-placer/tests/deterministic/stages/"
            "_power_plane_py_oracle.py > packages/temper-placer/tests/deterministic/stages/"
            "_power_plane_py_oracle.py`, run this generator, then discard the revived "
            "file again (it must not be re-committed)."
        ) from exc


# ---------------------------------------------------------------------------
# Case model
# ---------------------------------------------------------------------------

# ``existing`` entries are (net_name, layer, allow_layer_change, is_plane)
# tuples; ``plane_layers`` is a list of (net_name, layer) pairs (rendered
# deterministically, unlike a dict).


def _case(existing, plane_nets, plane_layers, all_nets) -> FreezeCase:
    tags = {"kernel:recompute"}
    existing_nets = {n for (n, _l, _a, _i) in existing}
    for (n, _l, a, is_plane) in existing:
        if n in plane_nets:
            tags.add("existing_upgrade")
        else:
            tags.add("existing_non_plane")
        if not a:
            tags.add("allow_false_preserved")
        if is_plane and n not in plane_nets:
            tags.add("existing_plane_kept")
    layer_map = dict(plane_layers)
    for n in plane_nets:
        if n not in existing_nets:
            if n in all_nets:
                tags.add("new_plane_added")
            else:
                tags.add("plane_dropped_not_in_netlist")
        if n not in layer_map:
            tags.add("layer_fallback_1")
    for n in all_nets:
        if n not in existing_nets and n not in plane_nets:
            tags.add("remaining_layer0")
    if not existing and not plane_nets and not all_nets:
        tags.add("empty_inputs")
    return FreezeCase(
        input={
            "kernel": "recompute",
            "existing": existing,
            "plane_nets": plane_nets,
            "plane_layers": plane_layers,
            "all_nets": all_nets,
        },
        tags=frozenset(tags),
    )


def _curated_cases() -> list[FreezeCase]:
    # Mirrors the retired differential's test cases one-for-one.
    return [
        _case(
            [("GND", 1, True, False), ("SPI_CLK", 0, True, False)],
            ["GND", "+5V"],
            [("GND", 1), ("+5V", 2)],
            ["GND", "SPI_CLK", "+5V"],
        ),
        _case([("SPI_CLK", 0, True, False)], ["GND"], [("GND", 1)], ["GND", "SPI_CLK"]),
        _case([], ["GND"], [], ["GND"]),
        _case([("GND", 0, True, False)], ["GND"], [], ["GND"]),
        _case([], [], {}, ["SPI_CLK", "GATE_HI"]),
        _case([("SPI_CLK", 0, False, False)], [], [], ["SPI_CLK"]),
        _case([("GND", 1, True, False)], ["GND", "NONEXISTENT"], [("GND", 1)], ["GND"]),
        _case([], ["GND"], [("GND", 1)], []),
        _case([], [], [], []),
        _case([("GND", 0, True, False)], ["GND"], [("GND", 2)], ["GND"]),
        _case(
            [("A", 0, True, False), ("B", 0, True, False)],
            ["Z"],
            [("Z", 2)],
            ["A", "B", "Z", "C"],
        ),
        # Extra curated families beyond the retired differential.
        _case([("GND", 3, True, True)], ["GND"], [("GND", 1)], ["GND"]),  # existing plane kept
        _case([("NET", 2, False, True)], [], [], ["NET"]),  # non-plane list, plane flag kept
        _case([("X", 0, True, False)], ["X"], [("X", 4)], ["X", "Y"]),  # upgrade + new remaining
    ]


def _random_cases(n: int, seed: int) -> list[FreezeCase]:
    rng = SplitMix64(seed)
    out: list[FreezeCase] = []
    names = [f"N{i}" for i in range(6)]
    for _ in range(n):
        existing = []
        for name in names[: rng.index(4)]:
            layer = rng.index(4)
            allow = rng.boolean()
            is_plane = rng.boolean()
            existing.append((name, layer, allow, is_plane))
        plane_nets = [names[i] for i in sorted({rng.index(len(names)) for _ in range(rng.index(4))})]
        all_nets = [names[i] for i in sorted({rng.index(len(names)) for _ in range(rng.index(5))})]
        plane_layers = [
            (name, rng.index(4)) for name in plane_nets if rng.boolean()
        ]
        out.append(_case(existing, plane_nets, plane_layers, all_nets))
    return out


def gen_cases() -> list[FreezeCase]:
    return _curated_cases() + _random_cases(40, seed=0x7AB1E5)


def run_oracle(case_input: dict):
    oracle = _oracle_module()
    LA = oracle.LayerAssignment
    existing_objs = [
        LA(net_name=n, layer=l, allow_layer_change=a, is_plane=i)
        for (n, l, a, i) in case_input["existing"]
    ]
    plane_layers = dict(case_input["plane_layers"])
    out = oracle.recompute_plane_assignments(
        existing_objs, case_input["plane_nets"], plane_layers, case_input["all_nets"]
    )
    return [(a.net_name, a.layer, a.allow_layer_change, a.is_plane) for a in out]


# ---------------------------------------------------------------------------
# Rust rendering
# ---------------------------------------------------------------------------


def _rs_str_list(items) -> str:
    return ", ".join(f'"{s}"' for s in items)


def _rs_tuple4(t) -> str:
    n, l, a, i = t
    return f'("{n}", {l}i64, {str(a).lower()}, {str(i).lower()})'


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for `recompute_plane_assignments` (FREEZE, batch 2).")
    lines.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec power_plane`")
    lines.append("    /// (requires reviving the deleted oracle from git history first -- see")
    lines.append("    /// scripts/oracle_freeze_specs/power_plane.py's module docstring).")
    lines.append("    #[cfg(test)]")
    lines.append("    mod frozen_power_plane_tests {")
    lines.append("        use super::*;")
    lines.append("        use std::collections::HashMap;")
    lines.append("")
    lines.append("        struct FrozenPowerPlaneCase {")
    lines.append("            existing: &'static [(&'static str, i64, bool, bool)],")
    lines.append("            plane_nets: &'static [&'static str],")
    lines.append("            plane_layers: &'static [(&'static str, i64)],")
    lines.append("            all_nets: &'static [&'static str],")
    lines.append("            expected: &'static [(&'static str, i64, bool, bool)],")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_POWER_PLANE_GOLDEN: &[FrozenPowerPlaneCase] = &[")
    for case, output in results:
        inp = case.input
        existing_rs = ", ".join(_rs_tuple4(t) for t in inp["existing"])
        plane_nets_rs = _rs_str_list(inp["plane_nets"])
        plane_layers_rs = ", ".join(f'("{k}", {v}i64)' for k, v in inp["plane_layers"])
        all_nets_rs = _rs_str_list(inp["all_nets"])
        expected_rs = ", ".join(_rs_tuple4(t) for t in output)
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenPowerPlaneCase {")
        lines.append(f"                existing: &[{existing_rs}],")
        lines.append(f"                plane_nets: &[{plane_nets_rs}],")
        lines.append(f"                plane_layers: &[{plane_layers_rs}],")
        lines.append(f"                all_nets: &[{all_nets_rs}],")
        lines.append(f"                expected: &[{expected_rs}],")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")
    lines.append("        #[test]")
    lines.append("        fn frozen_power_plane_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_POWER_PLANE_GOLDEN {")
    lines.append("                let existing: Vec<(String, i64, bool, bool)> = case.existing")
    lines.append("                    .iter().map(|&(n, l, a, i)| (n.to_string(), l, a, i)).collect();")
    lines.append("                let plane_nets: Vec<String> = case.plane_nets.iter().map(|s| s.to_string()).collect();")
    lines.append("                let mut plane_layers: HashMap<String, i64> = HashMap::new();")
    lines.append("                for &(k, v) in case.plane_layers { plane_layers.insert(k.to_string(), v); }")
    lines.append("                let all_nets: Vec<String> = case.all_nets.iter().map(|s| s.to_string()).collect();")
    lines.append("                let got = recompute_plane_assignments(&existing, &plane_nets, &plane_layers, &all_nets);")
    lines.append("                let want: Vec<(String, i64, bool, bool)> = case.expected")
    lines.append("                    .iter().map(|&(n, l, a, i)| (n.to_string(), l, a, i)).collect();")
    lines.append('                assert_eq!(got, want, "tags={:?}", case.tags);')
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were")
    lines.append("        /// ever hand-edited down to something trivially satisfiable.")
    lines.append("        #[test]")
    lines.append("        fn frozen_power_plane_corpus_is_non_vacuous() {")
    lines.append("            let n = FROZEN_POWER_PLANE_GOLDEN.len() as u32;")
    lines.append(
        '            let count = |tag: &str| FROZEN_POWER_PLANE_GOLDEN.iter()'
        ".filter(|c| c.tags.contains(&tag)).count() as u32;"
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
        tag="kernel:recompute",
        description="recompute golden vectors must be present",
        min_count=10,
    ),
    NonVacuityCheck(
        tag="existing_upgrade",
        description="existing plane-net assignment upgrade branch (is_plane=True)",
        min_count=4,
    ),
    NonVacuityCheck(
        tag="existing_non_plane",
        description="existing non-plane assignment pass-through branch",
        min_count=4,
    ),
    NonVacuityCheck(
        tag="new_plane_added",
        description="plane net not in existing, present in netlist -> appended",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="plane_dropped_not_in_netlist",
        description="plane net absent from the netlist is silently dropped",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="layer_fallback_1",
        description="`plane_layers.get(net_name, 1)` default must be exercised",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="remaining_layer0",
        description="netlist nets with no assignment -> layer 0, non-plane",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="allow_false_preserved",
        description="allow_layer_change=False must survive the upgrade branch",
        min_count=2,
    ),
    NonVacuityCheck(
        tag="empty_inputs",
        description="all-empty inputs must return the empty list",
        min_count=1,
    ),
]


SPEC = FreezeSpec(
    name="power_plane",
    description="deterministic/stages/power_plane.py::recompute_plane_assignments -- the three-pass plane-net reassignment.",
    oracle_provenance=(
        "packages/temper-placer/tests/deterministic/stages/_power_plane_py_oracle.py, "
        "pinned at 19ddfc1fe, unchanged 1442 commits as of freeze"
    ),
    kernel_provenance=(
        "packages/temper-design-bundle/src/deterministic_leaves.rs :: "
        "recompute_plane_assignments"
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
