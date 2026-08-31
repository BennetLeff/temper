"""FREEZE spec: ``physics/operating_point.py``'s numeric kernels (U4 oracle
retirement, batch 3).

Oracle (retired by this spec's first run):
  packages/temper-placer/tests/physics/_operating_point_py_oracle.py
  VERBATIM copy as of commit ``facaed149``; unchanged 1711 commits.

Kernel:
  packages/temper-thermal/src/operating_point.rs ::
  l_eff, thermal_chain, extreme_point, interior_k_grid
  All pure functions over f64/bool/usize.

Disposition: FREEZE. Not a safety kernel (physics model, not DRC).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace

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
        return importlib.import_module("tests.physics._operating_point_py_oracle")
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "the pinned oracle has been deleted (FREEZE retired it). "
            "To regenerate, revive from git: "
            "`git show facaed149:packages/temper-placer/tests/physics/"
            "_operating_point_py_oracle.py > ...`, run, then discard."
        ) from exc


def run_oracle(case_input: dict):
    oracle = _oracle_module()
    fn = case_input["fn"]
    if fn == "l_eff":
        cfg = SimpleNamespace(L_coil=case_input["l_coil"], L_leakage=case_input["l_leakage"])
        return oracle._l_eff(cfg, case_input["k"])
    elif fn == "thermal_chain":
        cfg = SimpleNamespace(
            R_theta_jc=case_input["r_theta_jc"],
            R_theta_cs=case_input["r_theta_cs"],
            R_theta_sa=case_input["r_theta_sa"],
            V_BR=case_input["v_br"],
            derate=case_input["derate"],
            T_amb=case_input["t_amb"],
            L_coil=1e-6,
            L_leakage=1e-6,
            V_bus=1.0,
            T_j_max=999.0,
            min_feasible_L_loop=0.0,
        )
        k0, _ = oracle._oracle_compute_extremes(cfg, case_input["p_device"])
        r_th = cfg.R_theta_jc + cfg.R_theta_cs + cfg.R_theta_sa
        v_br_d = cfg.V_BR * cfg.derate
        return (r_th, v_br_d, k0.T_j)
    elif fn == "extreme_point":
        cfg = SimpleNamespace(
            V_bus=case_input["v_bus"],
            L_coil=case_input["l_eff_value"],
            L_leakage=case_input["l_eff_value"],
            V_BR=case_input["v_br"],
            derate=case_input["derate"],
            T_amb=case_input["t_amb"],
            T_j_max=case_input["t_j_max"],
            R_theta_jc=case_input["r_theta_jc"],
            R_theta_cs=case_input["r_theta_cs"],
            R_theta_sa=case_input["r_theta_sa"],
            min_feasible_L_loop=case_input["min_feasible_l_loop"],
        )
        k0, k1 = oracle._oracle_compute_extremes(cfg, case_input["p_device"])
        ep = k0 if case_input.get("use_k1", False) is False else k1
        return (ep.di_dt, ep.L_loop_max, ep.feasible)
    elif fn == "interior_k_grid":
        n = case_input["n"]
        div = n - 1
        return [float(i) / div for i in range(1, n - 1)]
    raise ValueError(f"unknown fn: {fn}")


def _l_eff_tagged(name, l_coil, l_leakage, k):
    output = run_oracle({"fn": "l_eff", "l_coil": l_coil, "l_leakage": l_leakage, "k": k})
    tags: set[str] = {"l_eff"}
    if k == 0.0:
        tags.add("l_eff:k0")
    if k == 1.0:
        tags.add("l_eff:k1")
    if 0 < k < 1:
        tags.add("l_eff:interior")
    if l_coil == l_leakage:
        tags.add("l_eff:equal")
    if l_coil < 0 or l_leakage < 0:
        tags.add("l_eff:negative")
    if name:
        tags.add(f"named:{name}")
    return FreezeCase(input={"fn": "l_eff", "l_coil": l_coil, "l_leakage": l_leakage, "k": k}, tags=frozenset(tags))


def _thermal_tagged(name, p_device, t_amb, r_theta_jc, r_theta_cs, r_theta_sa, v_br, derate):
    output = run_oracle({"fn": "thermal_chain", "p_device": p_device, "t_amb": t_amb,
                         "r_theta_jc": r_theta_jc, "r_theta_cs": r_theta_cs, "r_theta_sa": r_theta_sa,
                         "v_br": v_br, "derate": derate})
    tags: set[str] = {"thermal_chain"}
    if p_device == 0.0:
        tags.add("thermal:zero_power")
    if derate == 1.0:
        tags.add("thermal:full_derate")
    if t_amb < 0:
        tags.add("thermal:negative_amb")
    if name:
        tags.add(f"named:{name}")
    return FreezeCase(input={"fn": "thermal_chain", "p_device": p_device, "t_amb": t_amb,
                             "r_theta_jc": r_theta_jc, "r_theta_cs": r_theta_cs, "r_theta_sa": r_theta_sa,
                             "v_br": v_br, "derate": derate}, tags=frozenset(tags))


def _extreme_tagged(name, v_bus, l_eff_value, v_br, derate, t_amb, t_j_max, r_theta_jc, r_theta_cs, r_theta_sa, min_feasible_l_loop, p_device, use_k1=False):
    output = run_oracle({"fn": "extreme_point", "v_bus": v_bus, "l_eff_value": l_eff_value,
                         "v_br": v_br, "derate": derate, "t_amb": t_amb, "t_j_max": t_j_max,
                         "r_theta_jc": r_theta_jc, "r_theta_cs": r_theta_cs, "r_theta_sa": r_theta_sa,
                         "min_feasible_l_loop": min_feasible_l_loop, "p_device": p_device, "use_k1": use_k1})
    tags: set[str] = {"extreme_point"}
    if output[2]:
        tags.add("extreme:feasible")
    else:
        tags.add("extreme:infeasible")
    if output[1] == 0.0:
        tags.add("extreme:zero_loop")
    if v_br * derate <= v_bus:
        tags.add("extreme:no_headroom")
    if name:
        tags.add(f"named:{name}")
    return FreezeCase(input={"fn": "extreme_point", "v_bus": v_bus, "l_eff_value": l_eff_value,
                             "v_br": v_br, "derate": derate, "t_amb": t_amb, "t_j_max": t_j_max,
                             "r_theta_jc": r_theta_jc, "r_theta_cs": r_theta_cs, "r_theta_sa": r_theta_sa,
                             "min_feasible_l_loop": min_feasible_l_loop, "p_device": p_device, "use_k1": use_k1}, tags=frozenset(tags))


def _grid_tagged():
    oracle = _oracle_module()
    n = oracle._INTERIOR_GRID_POINTS
    output = run_oracle({"fn": "interior_k_grid", "n": n})
    tags = frozenset({"interior_k_grid", f"grid:n={n}"})
    return FreezeCase(input={"fn": "interior_k_grid", "n": n}, tags=tags)


def gen_cases() -> list[FreezeCase]:
    # l_eff curated
    l_eff_cases = [
        ("k0", 100e-6, 10e-6, 0.0),
        ("k1", 100e-6, 10e-6, 1.0),
        ("k_mid", 100e-6, 10e-6, 0.5),
        ("equal", 50e-6, 50e-6, 0.5),
        ("k_third", 100e-6, 10e-6, 1.0/3.0),
        ("large", 1e-2, 1e-9, 0.1),
        ("tiny", 1e-9, 1e-12, 0.9),
    ]
    cases = [_l_eff_tagged(name, lc, ll, k) for name, lc, ll, k in l_eff_cases]

    # l_eff random
    rng = SplitMix64(0x0A4)
    for _ in range(50):
        lc = rng.range(1e-9, 1e-2)
        ll = rng.range(1e-12, 1e-2)
        k = rng.range(0.0, 1.0)
        cases.append(_l_eff_tagged(None, lc, ll, k))

    # thermal_chain curated
    thermal_cases = [
        ("prod", 16.0, 40.0, 0.6, 0.25, 1.0, 1200.0, 0.80),
        ("zero_power", 0.0, 40.0, 0.6, 0.25, 1.0, 1200.0, 0.80),
        ("full_derate", 16.0, 25.0, 0.5, 0.2, 0.8, 600.0, 1.0),
        ("neg_amb", 10.0, -40.0, 0.3, 0.1, 0.5, 1200.0, 0.7),
        ("high_power", 100.0, 85.0, 0.1, 0.05, 0.2, 1700.0, 0.5),
    ]
    cases.extend([_thermal_tagged(name, *tc) for name, *tc in thermal_cases])

    # thermal_chain random
    for _ in range(30):
        pd = rng.range(0.001, 100.0)
        ta = rng.range(-40.0, 85.0)
        r1 = rng.range(0.05, 3.0)
        r2 = rng.range(0.01, 2.0)
        r3 = rng.range(0.1, 10.0)
        vb = rng.range(1.0, 1700.0)
        dr = rng.range(0.05, 1.0)
        cases.append(_thermal_tagged(None, pd, ta, r1, r2, r3, vb, dr))

    # extreme_point curated
    extreme_cases = [
        ("feasible", 325.0, 100e-6, 1200.0, 0.80, 40.0, 150.0, 0.6, 0.25, 1.0, 5e-9, 16.0),
        ("infeasible", 325.0, 10e-6, 1200.0, 0.80, 40.0, 150.0, 0.6, 0.25, 1.0, 5e-9, 16.0, True),
        ("no_headroom", 1200.0, 100e-6, 1200.0, 0.80, 40.0, 150.0, 0.6, 0.25, 1.0, 5e-9, 16.0),
        ("zero_power", 325.0, 100e-6, 1200.0, 0.80, 25.0, 150.0, 0.6, 0.25, 1.0, 5e-9, 0.0),
    ]
    cases.extend([_extreme_tagged(name, *ec) for name, *ec in extreme_cases])

    # extreme_point random
    for _ in range(30):
        vbus = rng.range(1.0, 800.0)
        leff = rng.range(1e-9, 1e-2)
        vbr = rng.range(1.0, 1700.0)
        dr = rng.range(0.05, 1.0)
        ta = rng.range(-40.0, 85.0)
        tjmax = rng.range(80.0, 200.0)
        r1 = rng.range(0.05, 3.0)
        r2 = rng.range(0.01, 2.0)
        r3 = rng.range(0.1, 10.0)
        mfl = rng.range(1e-12, 1e-6)
        pd = rng.range(0.001, 100.0)
        uk1 = rng.boolean()
        cases.append(_extreme_tagged(None, vbus, leff, vbr, dr, ta, tjmax, r1, r2, r3, mfl, pd, uk1))

    # interior_k_grid
    cases.append(_grid_tagged())

    return cases


_NON_VACUITY = [
    NonVacuityCheck(tag="l_eff", description="l_eff must be exercised", min_count=30),
    NonVacuityCheck(tag="l_eff:k0", description="k=0 endpoint must be exercised", min_count=1),
    NonVacuityCheck(tag="l_eff:k1", description="k=1 endpoint must be exercised", min_count=1),
    NonVacuityCheck(tag="l_eff:interior", description="interior k values must be exercised", min_count=20),
    NonVacuityCheck(tag="thermal_chain", description="thermal_chain must be exercised", min_count=20),
    NonVacuityCheck(tag="extreme_point", description="extreme_point must be exercised", min_count=20),
    NonVacuityCheck(tag="extreme:feasible", description="feasible results must be present", min_count=3),
    NonVacuityCheck(tag="extreme:infeasible", description="infeasible results must be present", min_count=3),
    NonVacuityCheck(tag="extreme:zero_loop", description="zero L_loop_max (no headroom) must be exercised", min_count=1),
    NonVacuityCheck(tag="interior_k_grid", description="interior_k_grid must be exercised", min_count=1),
]


def render_rust(results: list[tuple[FreezeCase, object]]) -> str:
    le_cases = [(c, o) for c, o in results if c.input["fn"] == "l_eff"]
    tc_cases = [(c, o) for c, o in results if c.input["fn"] == "thermal_chain"]
    ep_cases = [(c, o) for c, o in results if c.input["fn"] == "extreme_point"]
    grid_cases = [(c, o) for c, o in results if c.input["fn"] == "interior_k_grid"]

    L: list[str] = []
    L.append("    /// Frozen golden vectors for operating_point numeric kernels")
    L.append("    /// (FREEZE, U4/U5, batch 3 -- retired physics/_operating_point_py_oracle.py).")
    L.append("    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec operating_point`")
    L.append("    #[cfg(test)]")
    L.append("    mod frozen_op_tests {")
    L.append("        use super::*;")
    L.append("")

    # l_eff
    L.append("        struct FrozenLeCase {")
    L.append("            l_coil: f64, l_leakage: f64, k: f64,")
    L.append("            expected: f64,")
    L.append("            tags: &'static [&'static str],")
    L.append("        }")
    L.append("")
    L.append("        const FROZEN_LE_GOLDEN: &[FrozenLeCase] = &[")
    for case, output in le_cases:
        ci = case.input
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        L.append("            FrozenLeCase {")
        L.append(f"                l_coil: {rust_f64_literal(ci['l_coil'])}, l_leakage: {rust_f64_literal(ci['l_leakage'])}, k: {rust_f64_literal(ci['k'])},")
        L.append(f"                expected: {rust_f64_literal(float(output))},")
        L.append(f"                tags: &[{tags_rs}],")
        L.append("            },")
    L.append("        ];")
    L.append("")

    # thermal_chain
    L.append("        struct FrozenTcCase {")
    L.append("            p_device: f64, t_amb: f64,")
    L.append("            r_theta_jc: f64, r_theta_cs: f64, r_theta_sa: f64,")
    L.append("            v_br: f64, derate: f64,")
    L.append("            expected: (f64, f64, f64),")
    L.append("            tags: &'static [&'static str],")
    L.append("        }")
    L.append("")
    L.append("        const FROZEN_TC_GOLDEN: &[FrozenTcCase] = &[")
    for case, output in tc_cases:
        ci = case.input
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        L.append("            FrozenTcCase {")
        L.append(f"                p_device: {rust_f64_literal(ci['p_device'])}, t_amb: {rust_f64_literal(ci['t_amb'])},")
        L.append(f"                r_theta_jc: {rust_f64_literal(ci['r_theta_jc'])}, r_theta_cs: {rust_f64_literal(ci['r_theta_cs'])}, r_theta_sa: {rust_f64_literal(ci['r_theta_sa'])},")
        L.append(f"                v_br: {rust_f64_literal(ci['v_br'])}, derate: {rust_f64_literal(ci['derate'])},")
        L.append(f"                expected: ({rust_f64_literal(float(output[0]))}, {rust_f64_literal(float(output[1]))}, {rust_f64_literal(float(output[2]))}),")
        L.append(f"                tags: &[{tags_rs}],")
        L.append("            },")
    L.append("        ];")
    L.append("")

    # extreme_point
    L.append("        struct FrozenEpCase {")
    L.append("            v_bus: f64, l_eff_value: f64,")
    L.append("            chain: ThermalChain,")
    L.append("            t_j_max: f64, min_feasible_l_loop: f64,")
    L.append("            expected: ExtremePoint,")
    L.append("            tags: &'static [&'static str],")
    L.append("        }")
    L.append("")
    L.append("        const FROZEN_EP_GOLDEN: &[FrozenEpCase] = &[")
    for case, output in ep_cases:
        ci = case.input
        chain = ThermalChain(ci)
        tags_rs = ", ".join(f'"{t}"' for t in sorted(case.tags))
        L.append("            FrozenEpCase {")
        L.append(f"                v_bus: {rust_f64_literal(ci['v_bus'])}, l_eff_value: {rust_f64_literal(ci['l_eff_value'])},")
        L.append(f"                chain: ThermalChain {{ r_th_total: {rust_f64_literal(chain[0])}, v_br_derated: {rust_f64_literal(chain[1])}, t_j: {rust_f64_literal(chain[2])} }},")
        L.append(f"                t_j_max: {rust_f64_literal(ci['t_j_max'])}, min_feasible_l_loop: {rust_f64_literal(ci['min_feasible_l_loop'])},")
        L.append(f"                expected: ExtremePoint {{ di_dt: {rust_f64_literal(float(output[0]))}, l_loop_max: {rust_f64_literal(float(output[1]))}, feasible: {'true' if output[2] else 'false'} }},")
        L.append(f"                tags: &[{tags_rs}],")
        L.append("            },")
    L.append("        ];")
    L.append("")

    # interior_k_grid
    L.append("        const FROZEN_GRID_N: usize = 11;")
    grid_vals = grid_cases[0][1] if grid_cases else []
    grid_rs = ", ".join(rust_f64_literal(float(v)) for v in grid_vals)
    L.append(f"        const FROZEN_GRID_EXPECTED: &[f64] = &[{grid_rs}];")
    L.append("")

    # Test functions
    L.append("        #[test]")
    L.append("        fn frozen_l_eff_matches_golden_corpus() {")
    L.append("            for case in FROZEN_LE_GOLDEN {")
    L.append("                let got = l_eff(case.l_coil, case.l_leakage, case.k);")
    L.append('                assert_eq!(got, case.expected, "tags={:?}", case.tags);')
    L.append("            }")
    L.append("        }")
    L.append("")
    L.append("        #[test]")
    L.append("        fn frozen_thermal_chain_matches_golden_corpus() {")
    L.append("            for case in FROZEN_TC_GOLDEN {")
    L.append("                let got = thermal_chain(case.p_device, case.t_amb,")
    L.append("                    case.r_theta_jc, case.r_theta_cs, case.r_theta_sa,")
    L.append("                    case.v_br, case.derate);")
    L.append('                assert_eq!(got, ThermalChain { r_th_total: case.expected.0, v_br_derated: case.expected.1, t_j: case.expected.2 }, "tags={:?}", case.tags);')
    L.append("            }")
    L.append("        }")
    L.append("")
    L.append("        #[test]")
    L.append("        fn frozen_extreme_point_matches_golden_corpus() {")
    L.append("            for case in FROZEN_EP_GOLDEN {")
    L.append("                let got = extreme_point(case.v_bus, case.l_eff_value,")
    L.append("                    case.chain, case.t_j_max, case.min_feasible_l_loop);")
    L.append('                assert_eq!(got, case.expected, "tags={:?}", case.tags);')
    L.append("            }")
    L.append("        }")
    L.append("")
    L.append("        #[test]")
    L.append("        fn frozen_interior_k_grid_matches() {")
    L.append("            let got = interior_k_grid(FROZEN_GRID_N);")
    L.append("            assert_eq!(got.as_slice(), FROZEN_GRID_EXPECTED);")
    L.append("        }")
    L.append("")

    # Non-vacuity guard
    L.append("        #[test]")
    L.append("        fn frozen_op_corpus_is_non_vacuous() {")
    L.append("            let le_n = FROZEN_LE_GOLDEN.len() as u32;")
    L.append("            let tc_n = FROZEN_TC_GOLDEN.len() as u32;")
    L.append("            let ep_n = FROZEN_EP_GOLDEN.len() as u32;")
    L.append("        let le_count = |t: &str| FROZEN_LE_GOLDEN.iter().filter(|c| c.tags.contains(&t)).count() as u32;")
    L.append("        let tc_count = |t: &str| FROZEN_TC_GOLDEN.iter().filter(|c| c.tags.contains(&t)).count() as u32;")
    L.append("        let ep_count = |t: &str| FROZEN_EP_GOLDEN.iter().filter(|c| c.tags.contains(&t)).count() as u32;")
    L.append("        let grid_present = FROZEN_GRID_N == 11;")
    for nvc in _NON_VACUITY:
        tag = nvc.tag
        if tag.startswith("l_eff"):
            cf, nv = "le_count", "le_n"
        elif tag.startswith("thermal"):
            cf, nv = "tc_count", "tc_n"
        elif tag.startswith("extreme"):
            cf, nv = "ep_count", "ep_n"
        elif tag == "interior_k_grid":
            L.append(f'            assert!(grid_present, "interior_k_grid: not present");')
            continue
        else:
            cf, nv = "le_count", "le_n"
        if nvc.min_count:
            L.append(f'            assert!({cf}("{tag}") >= {nvc.min_count}, "{tag}: only {{}}/{{}} (need >= {nvc.min_count})", {cf}("{tag}"), {nv});')
        else:
            pct = int(round(nvc.min_fraction * 100))
            L.append(f'            assert!({cf}("{tag}") * 100 >= {nv} * {pct}, "{tag}: only {{}}/{{}} (need >= {pct}%)", {cf}("{tag}"), {nv});')
    L.append("        }")
    L.append("    }")
    return "\n".join(L)


def ThermalChain(ci):
    r_th = ci["r_theta_jc"] + ci["r_theta_cs"] + ci["r_theta_sa"]
    v_br_d = ci["v_br"] * ci["derate"]
    t_j = ci["t_amb"] + ci["p_device"] * r_th
    return (r_th, v_br_d, t_j)


SPEC = FreezeSpec(
    name="operating_point",
    description=(
        "physics/operating_point.py -- l_eff, thermal_chain, extreme_point, "
        "interior_k_grid numeric kernels."
    ),
    oracle_provenance=(
        "packages/temper-placer/tests/physics/_operating_point_py_oracle.py, "
        "VERBATIM from pre-migration, unchanged 1711 commits as of freeze"
    ),
    kernel_provenance=(
        "packages/temper-thermal/src/operating_point.rs :: l_eff, thermal_chain, "
        "extreme_point, interior_k_grid"
    ),
    gen_cases=gen_cases,
    run_oracle=run_oracle,
    non_vacuity=_NON_VACUITY,
    render_rust=render_rust,
    rust_target_file="packages/temper-thermal/src/operating_point.rs",
    insert_before_marker="    #[cfg_attr(test, test)]",
)
