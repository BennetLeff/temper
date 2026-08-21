"""FREEZE spec: ``deterministic/stages/zone_aware_slot_generation.py``'s four
geometry kernels (U4 oracle retirement, batch 3).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/deterministic/stages/_zone_aware_slot_generation_py_oracle.py
  VERBATIM copy as of commit ``84d31f22f``; unchanged 538 commits as of freeze.

Kernels (all pure functions, no pyo3 objects in or out):
  - ``point_in_polygon`` → deterministic_phase.rs::point_in_polygon (bool)
  - ``slot_intersects_iso`` → deterministic_phase.rs::slot_intersects_iso (bool)
  - ``min_distance_to_polygon`` → deterministic_phase.rs::min_distance_to_polygon (f64)
  - ``point_to_segment_distance`` → temper_geometry::creepage_check::point_to_segment_distance (f64)
    (re-pinned issue #987 to mirror the canonical hypot contract)

Disposition: FREEZE. Not a safety kernel: copper-zone containment / slot
isolation / distance helpers for placement-slot generation, not
creepage/clearance/via/keepout DRC enforcement. No host-facility or entropy
dependency: pure f64 arithmetic over simple Vec inputs.
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
        return importlib.import_module("tests.deterministic.stages._zone_aware_slot_generation_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle this spec freezes has been deleted (FREEZE retired it "
            "on purpose) -- this is EXPECTED after the corpus has been generated once. "
            "To regenerate/extend the frozen corpus, revive it for one session first: "
            "`git show 84d31f22f:packages/temper-placer/tests/deterministic/stages/"
            "_zone_aware_slot_generation_py_oracle.py > packages/temper-placer/tests/deterministic/stages/"
            "_zone_aware_slot_generation_py_oracle.py`, run this generator, then discard the revived "
            "file again (it must not be re-committed)."
        ) from exc


def run_oracle(case_input: dict):
    oracle = _oracle_module()
    fn = case_input["fn"]
    if fn == "pip":
        return oracle.point_in_polygon(case_input["x"], case_input["y"], case_input["polygon"])
    elif fn == "iso":
        return oracle.slot_intersects_iso(case_input["slot"], case_input["aabbs"])
    elif fn == "mdp":
        return oracle.min_distance_to_polygon(case_input["x"], case_input["y"], case_input["polygon"])
    elif fn == "ptsd":
        return oracle.point_to_segment_distance(case_input["px"], case_input["py"], case_input["p1"], case_input["p2"])
    raise ValueError(f"unknown fn: {fn}")


# ---- point_in_polygon ----

_SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
_CONCAVE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (5.0, 5.0), (0.0, 10.0)]
_PENT = [(0.0, 0.0), (10.0, 0.0), (10.0, 4.0), (5.0, 8.0), (0.0, 4.0)]
_TRI_NEG = [(-5.0, -5.0), (5.0, -5.0), (0.0, 5.0)]


def _pip_tagged(name, x, y, polygon):
    output = run_oracle({"fn": "pip", "x": x, "y": y, "polygon": polygon})
    tags: set[str] = {"pip"}
    if output:
        tags.add("pip:inside")
    else:
        tags.add("pip:outside")
    if len(polygon) < 3:
        tags.add("pip:degenerate")
    if len(polygon) >= 2 and any(polygon[i][1] == polygon[(i + 1) % len(polygon)][1] for i in range(len(polygon))):
        tags.add("pip:horizontal_edge")
    if any(c < 0 for p in polygon for c in p) or x < 0 or y < 0:
        tags.add("pip:negative_coords")
    if len(polygon) >= 5:
        tags.add("pip:concave")
    if name:
        tags.add(f"named:{name}")
    return FreezeCase(input={"fn": "pip", "x": x, "y": y, "polygon": polygon}, tags=frozenset(tags))


def _pip_curated():
    cases = [
        ("inside", 5.0, 5.0, _SQUARE),
        ("outside_left", -1.0, 5.0, _SQUARE),
        ("outside_above", 5.0, 11.0, _SQUARE),
        ("outside_right", 11.0, 5.0, _SQUARE),
        ("top_edge", 5.0, 10.0, _SQUARE),
        ("bottom_edge", 5.0, 0.0, _SQUARE),
        ("left_edge", 0.0, 5.0, _SQUARE),
        ("right_edge", 10.0, 5.0, _SQUARE),
        ("vertex_00", 0.0, 0.0, _SQUARE),
        ("vertex_1010", 10.0, 10.0, _SQUARE),
        ("degenerate_2", 5.0, 5.0, [(0.0, 0.0), (10.0, 10.0)]),
        ("degenerate_1", 5.0, 5.0, [(0.0, 0.0)]),
        ("degenerate_0", 5.0, 5.0, []),
        ("concave_notch", 2.0, 8.0, _CONCAVE),
        ("concave_vertex", 5.0, 5.0, _CONCAVE),
        ("concave_right", 7.0, 8.0, _CONCAVE),
        ("pent_h_edge", 5.0, 2.0, _PENT),
        ("pent_on_h", 1.0, 4.0, _PENT),
        ("pent_on_h2", 9.0, 4.0, _PENT),
        ("neg_tri_center", 0.0, 0.0, _TRI_NEG),
        ("neg_tri_edge", -4.0, -4.9, _TRI_NEG),
        ("neg_tri_bottom", 0.0, -5.0, _TRI_NEG),
    ]
    return [_pip_tagged(name, x, y, poly) for name, x, y, poly in cases]


def _pip_random(n, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        nv = rng.randint(0, 8)
        poly = [(rng.uniform(-20, 20), rng.uniform(-20, 20)) for _ in range(nv)]
        out.append(_pip_tagged(None, rng.uniform(-25, 25), rng.uniform(-25, 25), poly))
    return out


# ---- slot_intersects_iso ----

def _iso_tagged(name, slot, aabbs):
    output = run_oracle({"fn": "iso", "slot": slot, "aabbs": aabbs})
    tags: set[str] = {"iso"}
    if output:
        tags.add("iso:hit")
    else:
        tags.add("iso:miss")
    if not aabbs:
        tags.add("iso:empty_aabbs")
    sx, sy = slot
    for (xlo, ylo), (xhi, yhi) in aabbs:
        if sx == xlo or sx == xhi or sy == ylo or sy == yhi:
            tags.add("iso:boundary_inclusive")
            break
    if len(aabbs) > 1:
        tags.add("iso:multiple_aabbs")
    if name:
        tags.add(f"named:{name}")
    return FreezeCase(input={"fn": "iso", "slot": slot, "aabbs": aabbs}, tags=frozenset(tags))


def _iso_curated():
    cases = [
        ("inside", (2.0, 2.0), [((0.0, 0.0), (4.0, 4.0))]),
        ("inside_2", (1.0, 1.0), [((0.0, 0.0), (4.0, 4.0))]),
        ("inside_3", (3.0, 3.0), [((0.0, 0.0), (4.0, 4.0))]),
        ("inside_neg", (-3.0, -3.0), [((-5.0, -5.0), (-1.0, -1.0))]),
        ("outside", (5.0, 5.0), [((0.0, 0.0), (4.0, 4.0))]),
        ("boundary_x", (4.0, 2.0), [((0.0, 0.0), (4.0, 4.0))]),
        ("boundary_y", (2.0, 4.0), [((0.0, 0.0), (4.0, 4.0))]),
        ("boundary_corner", (4.0, 4.0), [((0.0, 0.0), (4.0, 4.0))]),
        ("multi_hit", (6.0, 6.0), [((0.0, 0.0), (4.0, 4.0)), ((5.0, 5.0), (9.0, 9.0))]),
        ("multi_miss", (4.5, 4.5), [((0.0, 0.0), (4.0, 4.0)), ((5.0, 5.0), (9.0, 9.0))]),
        ("empty", (2.0, 2.0), []),
        ("negative", (-3.0, -3.0), [((-5.0, -5.0), (-1.0, -1.0))]),
    ]
    return [_iso_tagged(name, slot, aabbs) for name, slot, aabbs in cases]


def _iso_random(n, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        na = rng.randint(0, 5)
        aabbs = []
        for _ in range(na):
            x0, y0 = rng.uniform(-10, 10), rng.uniform(-10, 10)
            aabbs.append(((x0, y0), (x0 + rng.uniform(0, 10), y0 + rng.uniform(0, 10))))
        out.append(_iso_tagged(None, (rng.uniform(-12, 22), rng.uniform(-12, 22)), aabbs))
    return out


# ---- point_to_segment_distance ----

def _ptsd_tagged(name, px, py, p1, p2):
    output = run_oracle({"fn": "ptsd", "px": px, "py": py, "p1": p1, "p2": p2})
    tags: set[str] = {"ptsd"}
    if p1 == p2:
        tags.add("ptsd:degenerate_segment")
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    denom = dx * dx + dy * dy
    if denom == 0.0:
        tags.add("ptsd:zero_denom")
    else:
        t = ((px - x1) * dx + (py - y1) * dy) / denom
        if t < 0:
            tags.add("ptsd:clamped_before")
        elif t > 1:
            tags.add("ptsd:clamped_after")
        else:
            tags.add("ptsd:interior_projection")
    if px < 0 or py < 0 or x1 < 0 or y1 < 0 or x2 < 0 or y2 < 0:
        tags.add("ptsd:negative_coords")
    if name:
        tags.add(f"named:{name}")
    return FreezeCase(input={"fn": "ptsd", "px": px, "py": py, "p1": p1, "p2": p2}, tags=frozenset(tags))


def _ptsd_curated():
    cases = [
        ("degen_same", 0.0, 0.0, (1.0, 1.0), (1.0, 1.0)),
        ("degen_offset", 3.0, 4.0, (0.0, 0.0), (0.0, 0.0)),
        ("degen_origin", 5.0, 5.0, (0.0, 0.0), (0.0, 0.0)),
        ("interior", 0.0, 1.0, (0.0, 0.0), (2.0, 0.0)),
        ("interior_diag", 0.5, 0.5, (0.0, 0.0), (1.0, 1.0)),
        ("clamp_before", -1.0, 1.0, (0.0, 0.0), (1.0, 0.0)),
        ("clamp_after", 2.0, 1.0, (0.0, 0.0), (1.0, 0.0)),
        ("vertical", 1.0, 0.5, (0.0, 0.0), (0.0, 2.0)),
        ("negative", -5.0, -5.0, (-10.0, 0.0), (0.0, -10.0)),
    ]
    return [_ptsd_tagged(name, px, py, p1, p2) for name, px, py, p1, p2 in cases]


def _ptsd_random(n, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        px, py = rng.uniform(-50, 50), rng.uniform(-50, 50)
        p1 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        p2 = (rng.uniform(-50, 50), rng.uniform(-50, 50))
        out.append(_ptsd_tagged(None, px, py, p1, p2))
    return out


# ---- min_distance_to_polygon ----

def _mdp_tagged(name, x, y, polygon):
    output = run_oracle({"fn": "mdp", "x": x, "y": y, "polygon": polygon})
    tags: set[str] = {"mdp"}
    if math.isinf(output):
        tags.add("mdp:inf_result")
    if len(polygon) < 2:
        tags.add("mdp:degenerate_polygon")
    if len(polygon) == 2:
        tags.add("mdp:collinear")
    if x < 0 or y < 0 or any(c < 0 for p in polygon for c in p):
        tags.add("mdp:negative_coords")
    if name:
        tags.add(f"named:{name}")
    return FreezeCase(input={"fn": "mdp", "x": x, "y": y, "polygon": polygon}, tags=frozenset(tags))


def _mdp_curated():
    cases = [
        ("triangle_above", 0.0, 1.0, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]),
        ("triangle_inside", 0.5, 0.5, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)]),
        ("square_inside", 5.0, 5.0, _SQUARE),
        ("degen_1", 0.0, 0.0, [(0.0, 0.0)]),
        ("degen_0", 0.0, 0.0, []),
        ("collinear", 5.0, 1.0, [(0.0, 0.0), (10.0, 0.0)]),
        ("negative", -3.0, -3.0, _TRI_NEG),
    ]
    return [_mdp_tagged(name, x, y, poly) for name, x, y, poly in cases]


def _mdp_random(n, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        nv = rng.randint(0, 8)
        poly = [(rng.uniform(-20, 20), rng.uniform(-20, 20)) for _ in range(nv)]
        out.append(_mdp_tagged(None, rng.uniform(-25, 25), rng.uniform(-25, 25), poly))
    return out


# ---- gen_cases ----

def gen_cases() -> list[FreezeCase]:
    return (
        _pip_curated() + _pip_random(100, 13)
        + _iso_curated() + _iso_random(80, 17)
        + _ptsd_curated() + _ptsd_random(120, 19)
        + _mdp_curated() + _mdp_random(100, 29)
    )


_NON_VACUITY = [
    NonVacuityCheck(tag="pip", description="point_in_polygon must be exercised", min_count=50),
    NonVacuityCheck(tag="pip:inside", description="inside (true) results must be present", min_count=10),
    NonVacuityCheck(tag="pip:outside", description="outside (false) results must be present", min_count=10),
    NonVacuityCheck(tag="pip:degenerate", description="degenerate (< 3 vertices) polygons must be exercised", min_count=3),
    NonVacuityCheck(tag="pip:horizontal_edge", description="horizontal edges (p1y==p2y ternary) must be exercised", min_count=3),
    NonVacuityCheck(tag="pip:negative_coords", description="negative-coordinate polygons must be exercised", min_count=5),
    NonVacuityCheck(tag="pip:concave", description="concave (5+ vertex) polygons must be exercised", min_count=3),
    NonVacuityCheck(tag="iso", description="slot_intersects_iso must be exercised", min_count=30),
    NonVacuityCheck(tag="iso:hit", description="hit (true) results must be present", min_count=10),
    NonVacuityCheck(tag="iso:miss", description="miss (false) results must be present", min_count=10),
    NonVacuityCheck(tag="iso:boundary_inclusive", description="inclusive-boundary cases must be exercised", min_count=3),
    NonVacuityCheck(tag="iso:empty_aabbs", description="empty AABB list must be exercised", min_count=1),
    NonVacuityCheck(tag="ptsd", description="point_to_segment_distance must be exercised", min_count=50),
    NonVacuityCheck(tag="ptsd:degenerate_segment", description="degenerate (zero-length) segments must be exercised", min_count=3),
    NonVacuityCheck(tag="ptsd:interior_projection", description="interior projection (0<t<1) cases must be exercised", min_count=10),
    NonVacuityCheck(tag="ptsd:clamped_before", description="clamp-before (t<0) cases must be exercised", min_count=5),
    NonVacuityCheck(tag="ptsd:clamped_after", description="clamp-after (t>1) cases must be exercised", min_count=5),
    NonVacuityCheck(tag="mdp", description="min_distance_to_polygon must be exercised", min_count=50),
    NonVacuityCheck(tag="mdp:inf_result", description="inf result (degenerate polygon) must be exercised", min_count=3),
    NonVacuityCheck(tag="mdp:collinear", description="collinear (2-vertex) polygons must be exercised", min_count=2),
]


def _render_polygon(poly: list[tuple[float, float]]) -> str:
    items = ", ".join(f"({rust_f64_literal(x)}, {rust_f64_literal(y)})" for x, y in poly)
    return f"&[{items}]"


def _render_aabbs(aabbs: list) -> str:
    items = ", ".join(
        f"(({rust_f64_literal(xlo)}, {rust_f64_literal(ylo)}), "
        f"({rust_f64_literal(xhi)}, {rust_f64_literal(yhi)}))"
        for (xlo, ylo), (xhi, yhi) in aabbs
    )
    return f"&[{items}]"


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    pip_cases = [(c, o) for c, o in results if c.input["fn"] == "pip"]
    iso_cases = [(c, o) for c, o in results if c.input["fn"] == "iso"]
    ptsd_cases = [(c, o) for c, o in results if c.input["fn"] == "ptsd"]
    mdp_cases = [(c, o) for c, o in results if c.input["fn"] == "mdp"]

    lines: list[str] = []
    lines.append("    /// Frozen golden vectors for zone_aware_slot_generation geometry kernels")
    lines.append("    /// (FREEZE, U4/U5, batch 3 — retired stages/_zone_aware_slot_generation_py_oracle.py).")
    lines.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec zone_aware_slot_generation`")
    lines.append("    /// (requires reviving the deleted oracle from git history first — see")
    lines.append("    /// scripts/oracle_freeze_specs/zone_aware_slot_generation.py's module docstring).")
    lines.append("    #[cfg(test)]")
    lines.append("    mod frozen_zone_aware_tests {")
    lines.append("        use super::*;")
    lines.append("        use temper_geometry::creepage_check::point_to_segment_distance;")
    lines.append("")

    # point_in_polygon
    lines.append("        struct FrozenPipCase {")
    lines.append("            x: f64, y: f64,")
    lines.append("            polygon: &'static [(f64, f64)],")
    lines.append("            expected: bool,")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_PIP_GOLDEN: &[FrozenPipCase] = &[")
    for case, output in pip_cases:
        ci = case.input
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenPipCase {")
        lines.append(f"                x: {rust_f64_literal(float(ci['x']))}, y: {rust_f64_literal(float(ci['y']))},")
        lines.append(f"                polygon: {_render_polygon(ci['polygon'])},")
        lines.append(f"                expected: {'true' if output else 'false'},")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")

    # slot_intersects_iso
    lines.append("        struct FrozenIsoCase {")
    lines.append("            slot: (f64, f64),")
    lines.append("            aabbs: &'static [((f64, f64), (f64, f64))],")
    lines.append("            expected: bool,")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_ISO_GOLDEN: &[FrozenIsoCase] = &[")
    for case, output in iso_cases:
        ci = case.input
        sx, sy = ci["slot"]
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenIsoCase {")
        lines.append(f"                slot: ({rust_f64_literal(float(sx))}, {rust_f64_literal(float(sy))}),")
        lines.append(f"                aabbs: {_render_aabbs(ci['aabbs'])},")
        lines.append(f"                expected: {'true' if output else 'false'},")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")

    # point_to_segment_distance
    lines.append("        struct FrozenPtsdCase {")
    lines.append("            px: f64, py: f64,")
    lines.append("            p1: (f64, f64), p2: (f64, f64),")
    lines.append("            expected: f64,")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_PTSD_GOLDEN: &[FrozenPtsdCase] = &[")
    for case, output in ptsd_cases:
        ci = case.input
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenPtsdCase {")
        lines.append(f"                px: {rust_f64_literal(float(ci['px']))}, py: {rust_f64_literal(float(ci['py']))},")
        lines.append(f"                p1: ({rust_f64_literal(float(ci['p1'][0]))}, {rust_f64_literal(float(ci['p1'][1]))}),")
        lines.append(f"                p2: ({rust_f64_literal(float(ci['p2'][0]))}, {rust_f64_literal(float(ci['p2'][1]))}),")
        lines.append(f"                expected: {rust_f64_literal(float(output))},")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")

    # min_distance_to_polygon
    lines.append("        struct FrozenMdpCase {")
    lines.append("            x: f64, y: f64,")
    lines.append("            polygon: &'static [(f64, f64)],")
    lines.append("            expected: f64,")
    lines.append("            tags: &'static [&'static str],")
    lines.append("        }")
    lines.append("")
    lines.append("        const FROZEN_MDP_GOLDEN: &[FrozenMdpCase] = &[")
    for case, output in mdp_cases:
        ci = case.input
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        lines.append("            FrozenMdpCase {")
        lines.append(f"                x: {rust_f64_literal(float(ci['x']))}, y: {rust_f64_literal(float(ci['y']))},")
        lines.append(f"                polygon: {_render_polygon(ci['polygon'])},")
        lines.append(f"                expected: {rust_f64_literal(float(output))},")
        lines.append(f"                tags: &[{tags_rs}],")
        lines.append("            },")
    lines.append("        ];")
    lines.append("")

    # Test functions
    lines.append("        #[test]")
    lines.append("        fn frozen_pip_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_PIP_GOLDEN {")
    lines.append("                let got = point_in_polygon(case.x, case.y, case.polygon);")
    lines.append('                assert_eq!(got, case.expected, "tags={:?}", case.tags);')
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        #[test]")
    lines.append("        fn frozen_iso_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_ISO_GOLDEN {")
    lines.append("                let got = slot_intersects_iso(case.slot, case.aabbs);")
    lines.append('                assert_eq!(got, case.expected, "tags={:?}", case.tags);')
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        #[test]")
    lines.append("        fn frozen_ptsd_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_PTSD_GOLDEN {")
    lines.append("                let got = point_to_segment_distance(")
    lines.append("                    case.px, case.py,")
    lines.append("                    case.p1.0, case.p1.1, case.p2.0, case.p2.1,")
    lines.append("                );")
    lines.append('                assert_eq!(got, case.expected, "tags={:?}", case.tags);')
    lines.append("            }")
    lines.append("        }")
    lines.append("")
    lines.append("        #[test]")
    lines.append("        fn frozen_mdp_matches_golden_corpus() {")
    lines.append("            for case in FROZEN_MDP_GOLDEN {")
    lines.append("                let got = min_distance_to_polygon(case.x, case.y, case.polygon);")
    lines.append('                assert_eq!(got, case.expected, "tags={:?}", case.tags);')
    lines.append("            }")
    lines.append("        }")
    lines.append("")

    # Non-vacuity guard
    lines.append("        /// Q2 non-vacuity guard: fails closed if the frozen corpus above were")
    lines.append("        /// ever hand-edited down to something trivially satisfiable.")
    lines.append("        #[test]")
    lines.append("        fn frozen_zone_aware_corpus_is_non_vacuous() {")
    lines.append("            let pip_n = FROZEN_PIP_GOLDEN.len() as u32;")
    lines.append("            let iso_n = FROZEN_ISO_GOLDEN.len() as u32;")
    lines.append("            let ptsd_n = FROZEN_PTSD_GOLDEN.len() as u32;")
    lines.append("            let mdp_n = FROZEN_MDP_GOLDEN.len() as u32;")
    lines.append("            let pip_count = |tag: &str| FROZEN_PIP_GOLDEN.iter()")
    lines.append("                .filter(|c| c.tags.contains(&tag)).count() as u32;")
    lines.append("            let iso_count = |tag: &str| FROZEN_ISO_GOLDEN.iter()")
    lines.append("                .filter(|c| c.tags.contains(&tag)).count() as u32;")
    lines.append("            let ptsd_count = |tag: &str| FROZEN_PTSD_GOLDEN.iter()")
    lines.append("                .filter(|c| c.tags.contains(&tag)).count() as u32;")
    lines.append("            let mdp_count = |tag: &str| FROZEN_MDP_GOLDEN.iter()")
    lines.append("                .filter(|c| c.tags.contains(&tag)).count() as u32;")
    for nvc in _NON_VACUITY:
        tag = nvc.tag
        if tag.startswith("pip:"):
            count_fn = "pip_count"
            n_var = "pip_n"
        elif tag.startswith("iso:"):
            count_fn = "iso_count"
            n_var = "iso_n"
        elif tag.startswith("ptsd:"):
            count_fn = "ptsd_count"
            n_var = "ptsd_n"
        elif tag.startswith("mdp:"):
            count_fn = "mdp_count"
            n_var = "mdp_n"
        else:
            # Aggregate tags (pip, iso, ptsd, mdp) - use the per-array count
            count_fn = f"{tag}_count"
            n_var = f"{tag}_n"
        if nvc.min_count:
            lines.append(
                f'            assert!({count_fn}("{tag}") >= {nvc.min_count}, '
                f'"{tag}: only {{}}/{{}} (need >= {nvc.min_count}) -- {nvc.description}", '
                f'{count_fn}("{tag}"), {n_var});'
            )
        else:
            pct = int(round(nvc.min_fraction * 100))
            lines.append(
                f'            assert!({count_fn}("{tag}") * 100 >= {n_var} * {pct}, '
                f'"{tag}: only {{}}/{{}} (need >= {pct}%) -- {nvc.description}", '
                f'{count_fn}("{tag}"), {n_var});'
            )
    lines.append("        }")
    lines.append("    }")
    return "\n".join(lines)


SPEC = FreezeSpec(
    name="zone_aware_slot_generation",
    description=(
        "deterministic/stages/zone_aware_slot_generation.py — four geometry kernels: "
        "point_in_polygon (ray casting), slot_intersects_iso (AABB), "
        "min_distance_to_polygon, point_to_segment_distance (canonical hypot)."
    ),
    oracle_provenance=(
        "packages/temper-placer/tests/deterministic/stages/_zone_aware_slot_generation_py_oracle.py, "
        "VERBATIM from pre-migration, unchanged 538 commits as of freeze"
    ),
    kernel_provenance=(
        "packages/temper-design-bundle/src/deterministic_phase.rs :: point_in_polygon, "
        "slot_intersects_iso, min_distance_to_polygon; "
        "packages/temper-geometry/src/creepage_check.rs :: point_to_segment_distance"
    ),
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-design-bundle/src/deterministic_phase.rs",
    insert_before_marker="    #[test]",
)
