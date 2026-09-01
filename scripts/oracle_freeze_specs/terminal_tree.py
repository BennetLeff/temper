"""FREEZE spec: ``router_v6/terminal_tree.py``'s ``plan_terminal_tree``
kernel (U4 oracle retirement, batch 3).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/router_v6/_terminal_tree_py_oracle.py
  VERBATIM ``git show`` extraction of ``terminal_tree.py`` at commit
  ``550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5``; unchanged since creation
  (single commit in its history) as of this freeze.

Kernel:
  packages/temper-rust-router/src/terminal_planning.rs ::
  plan_terminal_tree -- a PURE Rust core over plain ``TreePad`` structs
  (no pyo3 in or out), so the golden-vector test is plain Rust data + an
  assert loop with no Python interpreter needed.

Disposition: FREEZE, not KEEP or REIMPLEMENT.
  - Not a safety kernel: a Prim-style topology planner over pad
    identities, not creepage/clearance/via/keepout geometry.
  - No host-facility or entropy dependency: the oracle's
    ``connected``/``remaining`` set iteration order provably cannot leak
    into the output (the min-key embeds both candidate PadIdentity VALUES;
    see the oracle module docstring) -- measured across ten interpreter
    processes with PYTHONHASHSEED unset.
  - Input domain (pad lists with string refs + f64 coords) is well suited
    to curated edge cases + a seeded randomized corpus.

Golden-vector encoding: identities in the expected plan are stored as
INDICES into the case's own pad list (the kernel's output identities are
field-value copies of input identities, so index == identity exactly).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib.oracle_freeze import (  # noqa: E402
    FreezeCase,
    FreezeSpec,
    NonVacuityCheck,
    rust_f64_literal,
)

_PLACER_TESTS_ROOT = Path(__file__).resolve().parent.parent.parent / "packages" / "temper-placer"


def _oracle_module():
    if str(_PLACER_TESTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_PLACER_TESTS_ROOT))
    import importlib

    try:
        return importlib.import_module("tests.router_v6._terminal_tree_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first: "
            "`git show 550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5:"
            "packages/temper-placer/tests/router_v6/_terminal_tree_py_oracle.py > "
            "packages/temper-placer/tests/router_v6/_terminal_tree_py_oracle.py`, "
            "run this generator, then discard the revived file again (it must not be "
            "re-committed)."
        ) from exc


def _make_pads(pad_specs):
    """Build the live CopperPad fixtures the differential suite uses."""
    from temper_placer.router_v6.connectivity import CopperPad, PadIdentity
    from temper_placer.router_v6.constraints_geometry import Point

    pads = []
    for spec in pad_specs:
        ref, index, x, y = spec["ref"], spec["index"], spec["x"], spec["y"]
        layers = tuple(spec.get("layers", (0,)))
        # x/y coerced to float: real pad positions are always the float
        # output of pin_world_position (same rationale as the differential).
        x, y = float(x), float(y)
        pads.append(
            CopperPad(
                PadIdentity(ref, str(index), "NET", x, y, layers),
                Point(x, y),
                "rect",
                (1, 1),
            )
        )
    return pads


def _identity_wire(ident) -> tuple:
    return (ident.component_ref, ident.pad, ident.net, ident.x, ident.y, list(ident.layers))


def run_oracle(case_input: dict):
    """Run the oracle on one case.

    Returns ``{"root": wire, "edges": [(wire, wire), ...]}`` on success or
    ``{"error": "<message>"}`` when the oracle raises (empty-pad case).
    """
    oracle = _oracle_module()
    pads = _make_pads(case_input["pads"])
    try:
        plan = oracle.plan_terminal_tree(pads)
    except Exception as exc:  # noqa: BLE001 - error parity IS the frozen output
        return {"error": str(exc)}
    return {
        "root": _identity_wire(plan.root),
        "edges": [(_identity_wire(e.source), _identity_wire(e.target)) for e in plan.edges],
    }


def _tags_for(pad_specs, output) -> set[str]:
    tags: set[str] = set()
    if "error" in output:
        tags.add("empty")
        return tags
    if len(pad_specs) == 1:
        tags.add("single_pad")
    refs = {spec["ref"] for spec in pad_specs}
    if len(refs) > 1:
        tags.add("multi_component")
    if any(tuple(spec.get("layers", (0,))) != (0,) for spec in pad_specs):
        tags.add("multi_layer")
    if any(spec["x"] < 0 or spec["y"] < 0 for spec in pad_specs):
        tags.add("negative_coord")
    if any(float(spec["x"]) != int(spec["x"]) or float(spec["y"]) != int(spec["y"]) for spec in pad_specs):
        tags.add("fractional_coord")
    identities = [(spec["ref"], str(spec["index"])) for spec in pad_specs]
    if len(identities) != len(set(identities)):
        tags.add("duplicate_identity")
    # Tied Manhattan distances between some connected/unconnected pair:
    # conservative superset detection -- equal pairwise distances from any
    # one pad to two others.
    n = len(pad_specs)
    for i in range(n):
        dists = [
            abs(float(pad_specs[i]["x"]) - float(pad_specs[j]["x"]))
            + abs(float(pad_specs[i]["y"]) - float(pad_specs[j]["y"]))
            for j in range(n)
            if j != i
        ]
        if len(dists) != len(set(dists)):
            tags.add("tied_distance")
            break
    if len(pad_specs) >= 5:
        tags.add("large_pad_count")
    return tags


def _tagged_case(name, pad_specs):
    output = run_oracle({"pads": pad_specs})
    tags = _tags_for(pad_specs, output)
    if name is not None:
        tags.add(f"named:{name}")
    return FreezeCase(input={"pads": pad_specs}, tags=frozenset(tags))


_NAMED_CASES = [
    (
        "three_pad_line",
        [
            {"ref": "U1", "index": 2, "x": 10, "y": 0},
            {"ref": "U1", "index": 1, "x": 0, "y": 0},
            {"ref": "U1", "index": 3, "x": 0, "y": 10},
        ],
    ),
    ("single_pad", [{"ref": "U1", "index": 1, "x": 5, "y": 5}]),
    (
        "two_pads",
        [
            {"ref": "U1", "index": 1, "x": 0, "y": 0},
            {"ref": "U1", "index": 2, "x": 3, "y": 4},
        ],
    ),
    (
        "star",
        [
            {"ref": "U1", "index": 0, "x": 0, "y": 0},
            {"ref": "U1", "index": 1, "x": 10, "y": 0},
            {"ref": "U1", "index": 2, "x": -10, "y": 0},
            {"ref": "U1", "index": 3, "x": 0, "y": 10},
            {"ref": "U1", "index": 4, "x": 0, "y": -10},
        ],
    ),
    (
        "multi_component",
        [
            {"ref": "U1", "index": 1, "x": 0, "y": 0},
            {"ref": "J1", "index": 1, "x": 20, "y": 0},
            {"ref": "R1", "index": 1, "x": 20, "y": 20},
            {"ref": "C1", "index": 1, "x": 0, "y": 20},
        ],
    ),
    (
        "tied_distances",
        [
            {"ref": "A", "index": 1, "x": 0, "y": 0},
            {"ref": "B", "index": 1, "x": 5, "y": 0},
            {"ref": "C", "index": 1, "x": 0, "y": 5},
        ],
    ),
    (
        "negative_and_fractional",
        [
            {"ref": "U1", "index": 1, "x": -1.5, "y": -2.25},
            {"ref": "U1", "index": 2, "x": 3.75, "y": 0.5},
            {"ref": "U1", "index": 3, "x": -0.25, "y": 4.0},
        ],
    ),
    (
        "multi_layer_identity",
        [
            {"ref": "U1", "index": 1, "x": 0, "y": 0, "layers": (0, 31)},
            {"ref": "U1", "index": 2, "x": 5, "y": 0, "layers": (0,)},
            {"ref": "U1", "index": 3, "x": 0, "y": 5, "layers": (31,)},
        ],
    ),
    (
        "duplicate_identity",
        [
            {"ref": "U1", "index": 1, "x": 0, "y": 0},
            {"ref": "U1", "index": 1, "x": 0, "y": 0},
            {"ref": "U1", "index": 2, "x": 10, "y": 0},
        ],
    ),
]


def _curated_cases() -> list[FreezeCase]:
    cases = [_tagged_case(name, specs) for name, specs in _NAMED_CASES]
    cases.append(_tagged_case("empty_raises", []))
    # Extra curated shapes the differential did not carry.
    cases.append(
        _tagged_case(
            "grid_3x3",
            [
                {"ref": "U1", "index": i, "x": float(col) * 2, "y": float(row) * 2}
                for i, (row, col) in enumerate(
                    [(r, c) for r in range(3) for c in range(3)]
                )
            ],
        )
    )
    cases.append(
        _tagged_case(
            "duplicate_identity_divergent_center",
            [
                {"ref": "U1", "index": 1, "x": 0, "y": 0},
                {"ref": "U1", "index": 1, "x": 7, "y": 7},
                {"ref": "U1", "index": 2, "x": 10, "y": 0},
            ],
        )
    )
    return cases


def _random_cases(n: int, seed: int) -> list[FreezeCase]:
    import random

    rng = random.Random(seed)
    out: list[FreezeCase] = []
    for i in range(n):
        count = rng.randint(1, 8)
        specs = []
        seen = set()
        for j in range(count):
            # Half the pads land on small integer lattice points -- the
            # densest natural source of genuine Manhattan-distance ties.
            if rng.random() < 0.5:
                x = float(rng.randint(-10, 10))
                y = float(rng.randint(-10, 10))
            else:
                x = round(rng.uniform(-100, 100), 3)
                y = round(rng.uniform(-100, 100), 3)
            # Mostly unique identities; occasionally inject a duplicate.
            if seen and rng.random() < 0.1:
                ref, index = rng.choice(list(seen))
            else:
                ref = rng.choice(["U1", "U2", "J1", "R1"])
                index = j
                seen.add((ref, index))
            layers = (0, 31) if rng.random() < 0.15 else (0,)
            specs.append({"ref": ref, "index": index, "x": x, "y": y, "layers": layers})
        out.append(_tagged_case(f"rand_{i}", specs))
    return out


def gen_cases() -> list[FreezeCase]:
    return _curated_cases() + _random_cases(80, seed=33)


_NON_VACUITY = [
    NonVacuityCheck(
        tag="multi_component",
        description="cross-component identities must be exercised (root selection)",
        min_fraction=0.15,
    ),
    NonVacuityCheck(
        tag="tied_distance",
        description="the identity tie-break must be exercised (the hash-order trap)",
        min_count=10,
    ),
    NonVacuityCheck(
        tag="negative_coord",
        description="negative coordinates must be exercised",
        min_count=10,
    ),
    NonVacuityCheck(
        tag="fractional_coord",
        description="fractional coordinates must be exercised",
        min_count=10,
    ),
    NonVacuityCheck(
        tag="duplicate_identity",
        description="the dedup-by-identity path must be exercised",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="multi_layer",
        description="non-default layer tuples in the identity key must be exercised",
        min_count=3,
    ),
    NonVacuityCheck(
        tag="empty",
        description="the empty-input ValueError branch must be exercised",
        min_count=1,
    ),
    NonVacuityCheck(
        tag="single_pad",
        description="the zero-edge single-terminal plan must be exercised",
        min_count=2,
    ),
]


def _ident_index(pad_specs, wire) -> int:
    """Map an output identity wire back to its input pad index."""
    target = (wire[0], wire[1], wire[2], wire[3], wire[4], list(wire[5]))
    for i, spec in enumerate(pad_specs):
        cand = (
            spec["ref"],
            str(spec["index"]),
            "NET",
            float(spec["x"]),
            float(spec["y"]),
            list(spec.get("layers", (0,))),
        )
        if cand == target:
            return i
    raise AssertionError(f"output identity {target!r} not found among inputs")


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for `plan_terminal_tree` (FREEZE, U4/U5, batch 3).")
    lines.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec terminal_tree`")
    lines.append("    /// (requires reviving the deleted oracle from git history first -- see")
    lines.append("    /// scripts/oracle_freeze_specs/terminal_tree.py's module docstring).")
    lines.append("    /// Expected identities are stored as INDICES into the case's pad list;")
    lines.append("    /// `expected_error` is Some for the empty-input ValueError case.")
    lines.append("    #[cfg(test)]")
    lines.append("    mod frozen_terminal_tree_tests {")
    lines.append("        use super::*;")
    lines.append("")
    lines.append("        struct FrozenPad {")
    lines.append("            component_ref: &'static str,")
    lines.append("            pad: &'static str,")
    lines.append("            net: &'static str,")
    lines.append("            x: f64,")
    lines.append("            y: f64,")
    lines.append("            layers: &'static [i64],")
    lines.append("            center_x: f64,")
    lines.append("            center_y: f64,")
    lines.append("        }")
    lines.append("")
    lines.append("        struct FrozenTerminalTreeCase {")
    lines.append("            name: &'static str,")
    lines.append("            tags: &'static [&'static str],")
    lines.append("            pads: &'static [FrozenPad],")
    lines.append("            expected_root: usize,")
    lines.append("            expected_edges: &'static [(usize, usize)],")
    lines.append("            expected_error: Option<&'static str>,")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_TERMINAL_TREE_GOLDEN: &[FrozenTerminalTreeCase] = &[")
    for case, output in results:
        pad_specs = case.input["pads"]
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenTerminalTreeCase {")
        lines.append(f'                name: "{case.tags and next(t.split("named:", 1)[1] for t in sorted(case.tags) if t.startswith("named:"))}",')
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("                pads: &[")
        for spec in pad_specs:
            x, y = float(spec["x"]), float(spec["y"])
            layers = ", ".join(str(int(l)) for l in spec.get("layers", (0,)))
            cx = rust_f64_literal(x)
            cy = rust_f64_literal(y)
            lines.append("                    FrozenPad {")
            lines.append(f'                        component_ref: "{spec["ref"]}",')
            lines.append(f'                        pad: "{spec["index"]}",')
            lines.append('                        net: "NET",')
            lines.append(f"                        x: {cx},")
            lines.append(f"                        y: {cy},")
            lines.append(f"                        layers: &[{layers}],")
            lines.append(f"                        center_x: {cx},")
            lines.append(f"                        center_y: {cy},")
            lines.append("                    },")
        lines.append("                ],")
        if "error" in output:
            msg = str(output["error"]).replace("\\", "\\\\").replace('"', '\\"')
            lines.append("                expected_root: 0,")
            lines.append("                expected_edges: &[],")
            lines.append(f'                expected_error: Some("{msg}"),')
        else:
            root_idx = _ident_index(pad_specs, output["root"])
            edges = [
                (_ident_index(pad_specs, s), _ident_index(pad_specs, t))
                for s, t in output["edges"]
            ]
            edges_rs = ", ".join(f"({s}, {t})" for s, t in edges)
            lines.append(f"                expected_root: {root_idx},")
            lines.append(f"                expected_edges: &[{edges_rs}],")
            lines.append("                expected_error: None,")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")
    lines.append("        fn frozen_pad_identity(p: &FrozenPad) -> PadIdentity {")
    lines.append("            PadIdentity {")
    lines.append("                component_ref: p.component_ref.to_string(),")
    lines.append("                pad: p.pad.to_string(),")
    lines.append("                net: p.net.to_string(),")
    lines.append("                x: p.x,")
    lines.append("                y: p.y,")
    lines.append("                layers: p.layers.to_vec(),")
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        #[test]")
    lines.append("        fn frozen_terminal_tree_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_TERMINAL_TREE_GOLDEN {")
    lines.append("                let pads: Vec<TreePad> = case.pads.iter()")
    lines.append("                    .map(|p| TreePad {")
    lines.append("                        identity: frozen_pad_identity(p),")
    lines.append("                        center: (p.center_x, p.center_y),")
    lines.append("                    })")
    lines.append("                    .collect();")
    lines.append("                match plan_terminal_tree(&pads) {")
    lines.append("                    Err(msg) => assert_eq!(")
    lines.append("                        Some(msg.as_str()),")
    lines.append("                        case.expected_error,")
    lines.append('                        "case {}: error mismatch",')
    lines.append("                        case.name")
    lines.append("                    ),")
    lines.append("                    Ok(plan) => {")
    lines.append("                        assert!(")
    lines.append("                            case.expected_error.is_none(),")
    lines.append('                            "case {}: expected error, got a plan",')
    lines.append("                            case.name")
    lines.append("                        );")
    lines.append("                        let idx_of = |id: &PadIdentity| -> usize {")
    lines.append("                            case.pads")
    lines.append("                                .iter()")
    lines.append("                                .position(|p| {")
    lines.append("                                    let fid = frozen_pad_identity(p);")
    lines.append("                                    fid.component_ref == id.component_ref")
    lines.append("                                        && fid.pad == id.pad")
    lines.append("                                        && fid.net == id.net")
    lines.append("                                        && fid.x == id.x")
    lines.append("                                        && fid.y == id.y")
    lines.append("                                        && fid.layers == id.layers")
    lines.append("                                })")
    lines.append("                                .unwrap_or_else(|| {")
    lines.append("                                    panic!(")
    lines.append('                                        "case {}: output identity not among inputs",')
    lines.append("                                        case.name")
    lines.append("                                    )")
    lines.append("                                })")
    lines.append("                        };")
    lines.append("                        assert_eq!(idx_of(&plan.root), case.expected_root, \"case {} root\", case.name);")
    lines.append("                        let got_edges: Vec<(usize, usize)> = plan")
    lines.append("                            .edges")
    lines.append("                            .iter()")
    lines.append("                            .map(|(s, t)| (idx_of(s), idx_of(t)))")
    lines.append("                            .collect();")
    lines.append("                        assert_eq!(&got_edges[..], case.expected_edges, \"case {} edges\", case.name);")
    lines.append("                    }")
    lines.append("                }")
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were")
    lines.append("        /// ever hand-edited down to something trivially satisfiable.")
    lines.append("        #[test]")
    lines.append("        fn frozen_terminal_tree_corpus_is_non_vacuous() {")
    lines.append("            let n = FROZEN_TERMINAL_TREE_GOLDEN.len() as u32;")
    lines.append("            let count = |tag: &str| FROZEN_TERMINAL_TREE_GOLDEN.iter()")
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
    name="terminal_tree",
    description=(
        "router_v6/terminal_tree.py::plan_terminal_tree -- deterministic "
        "Prim-style component-aware spanning tree over pad identities."
    ),
    oracle_provenance=(
        "packages/temper-placer/tests/router_v6/_terminal_tree_py_oracle.py, "
        "VERBATIM git-show extraction of terminal_tree.py at commit "
        "550cab2a3a0fcfd4a6c29063d30d3a83837ebcb5, unchanged since creation "
        "as of freeze"
    ),
    kernel_provenance=(
        "packages/temper-rust-router/src/terminal_planning.rs :: plan_terminal_tree"
    ),
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-rust-router/src/terminal_planning.rs",
    insert_before_marker="pub(crate) mod tests {",
)
