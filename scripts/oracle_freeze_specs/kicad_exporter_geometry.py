"""FREEZE spec: ``io/kicad_exporter.py``'s two geometry kernels (U4 oracle
retirement, batch 3).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/io/_kicad_exporter_py_oracle.py
  VERBATIM copy as of commit ``62a27ff5c``; unchanged 1342 commits.

Kernel:
  packages/temper-design-bundle/src/kicad_exporter_geometry.rs ::
  snap_to_nearest_pad (f64 x/y, pad_centers, tolerance -> (f64,f64))
  generate_connector_segments (FlatSegment list, pad_centers, max_dist -> Vec<FlatSegment>)
  FlatSegment = (String, (f64,f64), (f64,f64), f64, String) = (net, start, end, width, layer)

Disposition: FREEZE. Not a safety kernel. Pure f64/string arithmetic.
"""

from __future__ import annotations

import math
import random
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
    if str(_PLACER_TESTS_ROOT) not in sys.path:
        sys.path.insert(0, str(_PLACER_TESTS_ROOT))
    import importlib
    try:
        return importlib.import_module("tests.io._kicad_exporter_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle has been deleted (FREEZE retired it). "
            "To regenerate, revive from git: "
            "`git show 62a27ff5c:packages/temper-placer/tests/io/"
            "_kicad_exporter_py_oracle.py > ...`, run, then discard."
        ) from exc


def run_oracle(case_input: dict):
    oracle = _oracle_module()
    fn = case_input["fn"]
    if fn == "snap":
        return oracle.snap_to_nearest_pad(
            case_input["x"], case_input["y"],
            case_input["pad_centers"], case_input["tolerance"],
        )
    elif fn == "connector":
        from temper_placer.io.export_types import TraceSegment
        segs = [
            TraceSegment(net=s[0], start=s[1], end=s[2], width=s[3], layer=s[4])
            for s in case_input["segments"]
        ]
        pads = dict(case_input["pad_centers"])
        result = oracle._generate_connector_segments(segs, pads, case_input["max_dist"])
        return [(s.net, s.start, s.end, s.width, s.layer) for s in result]
    raise ValueError(f"unknown fn: {fn}")


# ---- snap_to_nearest_pad ----

def _snap_tagged(name, x, y, pad_centers, tolerance):
    output = run_oracle({"fn": "snap", "x": x, "y": y, "pad_centers": pad_centers, "tolerance": tolerance})
    tags: set[str] = {"snap"}
    if output == (x, y):
        tags.add("snap:unchanged")
    else:
        tags.add("snap:snapped")
    if not pad_centers:
        tags.add("snap:empty_pads")
    dists = [math.sqrt((x - px) ** 2 + (y - py) ** 2) for px, py in pad_centers]
    if dists and min(dists) == tolerance:
        tags.add("snap:exact_tolerance_boundary")
    if dists and min(dists) < tolerance:
        tags.add("snap:within_tolerance")
    if len(pad_centers) >= 2:
        sorted_d = sorted(dists)
        if len(sorted_d) >= 2 and sorted_d[0] == sorted_d[1]:
            tags.add("snap:exact_tie")
    if name:
        tags.add(f"named:{name}")
    return FreezeCase(
        input={"fn": "snap", "x": x, "y": y, "pad_centers": pad_centers, "tolerance": tolerance},
        tags=frozenset(tags),
    )


def _snap_curated():
    cases = [
        ("basic", 0.0, 0.0, [(0.05, 0.05)], 0.15),
        ("multi_pads", 0.0, 0.0, [(1.0, 0.0), (0.0, 1.0), (0.05, 0.05)], 0.15),
        ("outside_tol", 0.0, 0.0, [(5.0, 5.0)], 0.15),
        ("empty_pads", 0.0, 0.0, [], 0.15),
        ("fractional", 1.2345, -6.789, [(1.23, -6.79), (1.3, -6.8)], 0.15),
        ("exact_boundary", 0.0, 0.0, [(0.15, 0.0)], 0.15),
        ("first_wins_tie", 0.0, 0.0, [(0.1, 0.0), (-0.1, 0.0)], 0.15),
        ("default_tol", 0.0, 0.0, [(0.1, 0.0), (0.02, 0.0)], 0.15),
        ("negative_coords", -5.0, -5.0, [(-4.9, -4.9)], 0.15),
        ("large_tol", 0.0, 0.0, [(100.0, 100.0)], 200.0),
    ]
    return [_snap_tagged(name, x, y, pads, tol) for name, x, y, pads, tol in cases]


def _snap_random(n, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        x, y = rng.uniform(-10, 10), rng.uniform(-10, 10)
        npads = rng.randint(0, 5)
        pads = [(rng.uniform(-10, 10), rng.uniform(-10, 10)) for _ in range(npads)]
        tol = rng.choice([0.05, 0.15, 0.5, 1.0, 5.0])
        out.append(_snap_tagged(None, x, y, pads, tol))
    return out


# ---- generate_connector_segments ----

def _conn_tagged(name, segments, pad_centers, max_dist):
    output = run_oracle({"fn": "connector", "segments": segments, "pad_centers": pad_centers, "max_dist": max_dist})
    tags: set[str] = {"conn"}
    if not output:
        tags.add("conn:empty_result")
    else:
        tags.add("conn:has_connectors")
    if not segments:
        tags.add("conn:empty_segments")
    if not pad_centers:
        tags.add("conn:empty_pads")
    if len(pad_centers) > 1:
        tags.add("conn:multi_net")
    # Check for boundary cases
    for net, pads in pad_centers:
        for seg in segments:
            if seg[0] == net:
                for px, py in pads:
                    for ex, ey in [seg[1], seg[2]]:
                        d = math.sqrt((ex - px) ** 2 + (ey - py) ** 2)
                        if d == max_dist:
                            tags.add("conn:exact_max_dist_boundary")
                        if abs(ex - px) < 0.01 and abs(ey - py) < 0.01:
                            tags.add("conn:exact_match")
    if name:
        tags.add(f"named:{name}")
    return FreezeCase(
        input={"fn": "connector", "segments": segments, "pad_centers": pad_centers, "max_dist": max_dist},
        tags=frozenset(tags),
    )


def _conn_curated():
    S = lambda net, sx, sy, ex, ey, w, layer: (net, (sx, sy), (ex, ey), w, layer)
    cases = [
        ("bridge_dangling", [S("GND", 0, 0, 1, 0, 0.25, "F.Cu")], [("GND", [(2.5, 0.0)])], 2.0),
        ("skip_connected", [S("GND", 0, 0, 1, 0, 0.25, "F.Cu")], [("GND", [(1.0, 0.0)])], 2.0),
        ("boundary_001", [S("GND", 0.01, 0, 5, 0, 0.25, "F.Cu")], [("GND", [(0.0, 0.0)])], 2.0),
        ("skip_beyond_max", [S("GND", 0, 0, 1, 0, 0.25, "F.Cu")], [("GND", [(10.0, 0.0)])], 2.0),
        ("exact_max_dist", [S("GND", 0, 0, 1, 0, 0.25, "F.Cu")], [("GND", [(3.0, 0.0)])], 2.0),
        ("no_segments", [], [("GND", [(1.0, 0.0)])], 2.0),
        ("multi_net", [S("GND", 0, 0, 1, 0, 0.25, "F.Cu"), S("VCC", 0, 0, 2, 0, 0.3, "B.Cu")], [("GND", [(1.5, 0.0)]), ("VCC", [(2.5, 0.0)])], 2.0),
        ("ref_seg_width", [S("PWR", 0, 0, 5, 5, 0.5, "In1.Cu")], [("PWR", [(5.5, 5.5)])], 2.0),
        ("empty_all", [], [], 2.0),
        ("sequential_pads", [S("GND", 0, 0, 1, 0, 0.25, "F.Cu")], [("GND", [(1.5, 0.0), (2.5, 0.0)])], 2.0),
        ("exact_match_skip2", [S("VCC", 0, 0, 5, 5, 0.3, "B.Cu")], [("VCC", [(5.0, 5.0), (6.0, 6.0)])], 2.0),
    ]
    return [_conn_tagged(name, segs, pads, md) for name, segs, pads, md in cases]


def _conn_random(n, seed):
    rng = random.Random(seed)
    nets = ["GND", "VCC", "SIG", "PWR"]
    layers = ["F.Cu", "B.Cu", "In1.Cu"]
    out = []
    for _ in range(n):
        nsegs = rng.randint(0, 4)
        segs = []
        for _ in range(nsegs):
            net = rng.choice(nets)
            sx, sy = rng.uniform(-10, 10), rng.uniform(-10, 10)
            ex, ey = rng.uniform(-10, 10), rng.uniform(-10, 10)
            w = rng.choice([0.15, 0.2, 0.25, 0.5])
            layer = rng.choice(layers)
            segs.append((net, (sx, sy), (ex, ey), w, layer))
        npads = rng.randint(0, 3)
        pads = []
        for _ in range(npads):
            net = rng.choice(nets)
            npad = rng.randint(1, 3)
            pad_list = [(rng.uniform(-10, 10), rng.uniform(-10, 10)) for _ in range(npad)]
            pads.append((net, pad_list))
        md = rng.choice([1.0, 2.0, 5.0, 10.0])
        out.append(_conn_tagged(None, segs, pads, md))
    return out


def gen_cases() -> list[FreezeCase]:
    return _snap_curated() + _snap_random(60, 42) + _conn_curated()


_NON_VACUITY = [
    NonVacuityCheck(tag="snap", description="snap_to_nearest_pad must be exercised", min_count=30),
    NonVacuityCheck(tag="snap:snapped", description="snapped (changed) results must be present", min_count=10),
    NonVacuityCheck(tag="snap:unchanged", description="unchanged (outside tolerance) results must be present", min_count=5),
    NonVacuityCheck(tag="snap:empty_pads", description="empty pad_centers must be exercised", min_count=2),
    NonVacuityCheck(tag="snap:exact_tolerance_boundary", description="exact tolerance boundary (strict <) must be exercised", min_count=1),
    NonVacuityCheck(tag="snap:exact_tie", description="exact distance ties (first wins) must be exercised", min_count=1),
    NonVacuityCheck(tag="conn", description="generate_connector_segments must be exercised", min_count=10),
    NonVacuityCheck(tag="conn:has_connectors", description="non-empty connector results must be present", min_count=3),
    NonVacuityCheck(tag="conn:empty_result", description="empty result cases must be exercised", min_count=3),
    NonVacuityCheck(tag="conn:empty_segments", description="empty segments input must be exercised", min_count=2),
    NonVacuityCheck(tag="conn:multi_net", description="multi-net inputs must be exercised", min_count=1),
    NonVacuityCheck(tag="conn:exact_match", description="exact endpoint-pad match (skip) must be exercised", min_count=2),
]


def _esc(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    snap_cases = [(c, o) for c, o in results if c.input["fn"] == "snap"]
    conn_cases = [(c, o) for c, o in results if c.input["fn"] == "connector"]
    L: list[str] = []
    L.append("    /// Frozen golden vectors for kicad_exporter geometry kernels")
    L.append("    /// (FREEZE, U4/U5, batch 3 -- retired io/_kicad_exporter_py_oracle.py).")
    L.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec kicad_exporter_geometry`")
    L.append("    #[cfg(test)]")
    L.append("    mod frozen_kicad_geom_tests {")
    L.append("        use super::*;")
    L.append("")

    # snap_to_nearest_pad
    L.append("        struct FrozenSnapCase {")
    L.append("            x: f64, y: f64,")
    L.append("            pad_centers: &'static [(f64, f64)],")
    L.append("            tolerance: f64,")
    L.append("            expected: (f64, f64),")
    L.append("            tags: &'static [&'static str],")
    L.append("        }")
    L.append("")
    L.append("        const FROZEN_SNAP_GOLDEN: &[FrozenSnapCase] = &[")
    for case, output in snap_cases:
        ci = case.input
        pads_rs = ", ".join(f"({rust_f64_literal(px)}, {rust_f64_literal(py)})" for px, py in ci["pad_centers"])
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        L.append("            FrozenSnapCase {")
        L.append(f"                x: {rust_f64_literal(float(ci['x']))}, y: {rust_f64_literal(float(ci['y']))},")
        L.append(f"                pad_centers: &[{pads_rs}],")
        L.append(f"                tolerance: {rust_f64_literal(float(ci['tolerance']))},")
        L.append(f"                expected: ({rust_f64_literal(float(output[0]))}, {rust_f64_literal(float(output[1]))}),")
        L.append(f"                tags: &[{tags_rs}],")
        L.append("            },")
    L.append("        ];")
    L.append("")

    # generate_connector_segments
    L.append("        // FrozenSegment = (&str, (f64,f64), (f64,f64), f64, &str)")
    L.append("        type FrozenSeg = (&'static str, (f64, f64), (f64, f64), f64, &'static str);")
    L.append("        type FrozenPad = (&'static str, &'static [(f64, f64)]);")
    L.append("")
    L.append("        struct FrozenConnCase {")
    L.append("            segments: &'static [FrozenSeg],")
    L.append("            pad_centers: &'static [FrozenPad],")
    L.append("            max_dist: f64,")
    L.append("            expected: &'static [FrozenSeg],")
    L.append("            tags: &'static [&'static str],")
    L.append("        }")
    L.append("")
    L.append("        const FROZEN_CONN_GOLDEN: &[FrozenConnCase] = &[")
    for case, output in conn_cases:
        ci = case.input
        segs_rs = ", ".join(
            f'("{_esc(s[0])}", ({rust_f64_literal(s[1][0])}, {rust_f64_literal(s[1][1])}), '
            f'({rust_f64_literal(s[2][0])}, {rust_f64_literal(s[2][1])}), '
            f'{rust_f64_literal(float(s[3]))}, "{_esc(s[4])}")'
            for s in ci["segments"]
        )
        pads_rs_parts = []
        for net, pad_list in ci["pad_centers"]:
            inner = ", ".join(f"({rust_f64_literal(px)}, {rust_f64_literal(py)})" for px, py in pad_list)
            pads_rs_parts.append(f'("{_esc(net)}", &[{inner}])')
        pads_rs = ", ".join(pads_rs_parts)
        exp_rs = ", ".join(
            f'("{_esc(s[0])}", ({rust_f64_literal(s[1][0])}, {rust_f64_literal(s[1][1])}), '
            f'({rust_f64_literal(s[2][0])}, {rust_f64_literal(s[2][1])}), '
            f'{rust_f64_literal(float(s[3]))}, "{_esc(s[4])}")'
            for s in output
        )
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        L.append("            FrozenConnCase {")
        L.append(f"                segments: &[{segs_rs}],")
        L.append(f"                pad_centers: &[{pads_rs}],")
        L.append(f"                max_dist: {rust_f64_literal(float(ci['max_dist']))},")
        L.append(f"                expected: &[{exp_rs}],")
        L.append(f"                tags: &[{tags_rs}],")
        L.append("            },")
    L.append("        ];")
    L.append("")

    # Conversion + test functions
    L.append("        fn frozen_seg_to_flat(s: &FrozenSeg) -> FlatSegment {")
    L.append("            (s.0.to_string(), s.1, s.2, s.3, s.4.to_string())")
    L.append("        }")
    L.append("")
    L.append("        fn frozen_pad_to_flat(p: &FrozenPad) -> (String, Vec<(f64, f64)>) {")
    L.append("            (p.0.to_string(), p.1.to_vec())")
    L.append("        }")
    L.append("")
    L.append("        #[test]")
    L.append("        fn frozen_snap_matches_golden_corpus() {")
    L.append("            for case in FROZEN_SNAP_GOLDEN {")
    L.append("                let got = snap_to_nearest_pad(case.x, case.y, case.pad_centers, case.tolerance);")
    L.append('                assert_eq!(got, case.expected, "tags={:?}", case.tags);')
    L.append("            }")
    L.append("        }")
    L.append("")
    L.append("        #[test]")
    L.append("        fn frozen_conn_matches_golden_corpus() {")
    L.append("            for case in FROZEN_CONN_GOLDEN {")
    L.append("                let segs: Vec<FlatSegment> = case.segments.iter().map(frozen_seg_to_flat).collect();")
    L.append("                let pads: Vec<(String, Vec<(f64, f64)>)> = case.pad_centers.iter().map(frozen_pad_to_flat).collect();")
    L.append("                let got = generate_connector_segments(&segs, &pads, case.max_dist);")
    L.append("                let exp: Vec<FlatSegment> = case.expected.iter().map(frozen_seg_to_flat).collect();")
    L.append('                assert_eq!(got, exp, "tags={:?}", case.tags);')
    L.append("            }")
    L.append("        }")
    L.append("")

    # Non-vacuity guard
    L.append("        #[test]")
    L.append("        fn frozen_kicad_geom_corpus_is_non_vacuous() {")
    L.append("            let snap_n = FROZEN_SNAP_GOLDEN.len() as u32;")
    L.append("            let conn_n = FROZEN_CONN_GOLDEN.len() as u32;")
    L.append("            let snap_count = |tag: &str| FROZEN_SNAP_GOLDEN.iter()")
    L.append("                .filter(|c| c.tags.contains(&tag)).count() as u32;")
    L.append("            let conn_count = |tag: &str| FROZEN_CONN_GOLDEN.iter()")
    L.append("                .filter(|c| c.tags.contains(&tag)).count() as u32;")
    for nvc in _NON_VACUITY:
        tag = nvc.tag
        if tag.startswith("snap"):
            cf, nv = "snap_count", "snap_n"
        else:
            cf, nv = "conn_count", "conn_n"
        if nvc.min_count:
            L.append(f'            assert!({cf}("{tag}") >= {nvc.min_count}, "{tag}: only {{}}/{{}} (need >= {nvc.min_count})", {cf}("{tag}"), {nv});')
        else:
            pct = int(round(nvc.min_fraction * 100))
            L.append(f'            assert!({cf}("{tag}") * 100 >= {nv} * {pct}, "{tag}: only {{}}/{{}} (need >= {pct}%)", {cf}("{tag}"), {nv});')
    L.append("        }")
    L.append("    }")
    return "\n".join(L)


SPEC = FreezeSpec(
    name="kicad_exporter_geometry",
    description=(
        "io/kicad_exporter.py -- snap_to_nearest_pad and generate_connector_segments "
        "(tolerance-gated pad snapping and dangling-endpoint bridge generation)."
    ),
    oracle_provenance=(
        "packages/temper-placer/tests/io/_kicad_exporter_py_oracle.py, "
        "VERBATIM from pre-migration, unchanged 1342 commits as of freeze"
    ),
    kernel_provenance=(
        "packages/temper-design-bundle/src/kicad_exporter_geometry.rs :: "
        "snap_to_nearest_pad / generate_connector_segments"
    ),
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-design-bundle/src/kicad_exporter_geometry.rs",
    insert_before_marker="    #[test]",
)
