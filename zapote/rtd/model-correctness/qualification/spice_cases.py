#!/usr/bin/env python3
"""Independent ngspice checks for the complete RTDIN passive network.

The switches start closed (control=5 V) and open at 10 us (control falls to
zero), so every measured crossing is fault assertion from a healthy initial
state. The Python comparison uses the same nominal values and 1-ohm leads.
These are representative numerical checks, not a whole-range acceptance
policy.
"""
from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
CASES = ("FORCE+", "FORCE-", "SENSE+", "SENSE-")
CROSS_TOLERANCE_US = 2.1  # Python 1 us step + ngspice 1 us step + switch edge.


def _load_model():
    path = HERE / "full_network_bound.py"
    spec = importlib.util.spec_from_file_location("rtd_full_network_bound", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _nominal_params(model):
    return model.Params(
        vb=2.06, rref=430.0, vref=1.25, rlt=61900.0, rlb=10000.0,
        rht=5900.0, rhb=10000.0, rdiag=1e6, rdiag_n=1e6,
        voffl=0.004, voffh=0.004, ileak_max_p=0.0,
        ileak_max_n=0.0, ileak_window=0.0, ileak_low=0.0,
        ileak_high=0.0, rwin=100000.0, cdiff=1.1e-9,
        cground=100e-12,
    )


def deck(case: str) -> str:
    switch = {
        "FORCE+": ("forcep_i", "sensorp", "RFPATH"),
        "FORCE-": ("sensorn", "forcen_i", "RFNATH"),
        "SENSE+": ("sensorp", "sensep", "RSPATH"),
        "SENSE-": ("sensorn", "sensem", "RSNATH"),
    }
    a, b, removed = switch[case]
    paths = {
        "RFPATH": "RFPATH forcep_i sensorp 1",
        "RFNATH": "RFNATH sensorn forcen_i 1",
        "RSPATH": "RSPATH sensorp sensep 1",
        "RSNATH": "RSNATH sensorn sensem 1",
    }
    lines = [
        "* independent full external RTDIN network; open assertion at 10 us",
        "VBIAS bias 0 2.06",
        "VREFSRC refsrc 0 1.25",
        "VCTRL ctrl 0 PULSE(5 0 10u 1n 1n 10m 20m)",
        ".model SWOPEN SW(Ron=1 Roff=1e12 Vt=2 Vh=0)",
        "RREF bias forcep_i 430",
        *[value for key, value in paths.items() if key != removed],
        "RRTD sensorp sensorn 100",
        "RRETURN forcen_i 0 1m",
        "RDIAGP bias sensep 1Meg",
        "RDIAGN bias sensem 1Meg",
        "RWINP sensep windowp 100k",
        "CDIFF sensep sensem 1.1n",
        "CGP sensep 0 100p",
        "CGN sensem 0 100p",
        "RLOWTOPX refsrc lowth 61900",
        "RLOWBOTX lowth sensem 10000",
        "RHIGHTOPX refsrc highth 5900",
        "RHIGHBOTX highth 0 10000",
        f"SOPEN {a} {b} ctrl 0 SWOPEN",
        ".tran 1u 3m",
        ".control",
        "run",
        "let high_margin=v(highth)-v(windowp)-0.004",
        "let low_margin=v(windowp)-v(lowth)-0.004",
        ("meas tran cross WHEN high_margin=-0.020 FALL=1"
         if case in ("SENSE+", "FORCE-")
         else "meas tran cross WHEN low_margin=-0.020 FALL=1"),
        ".endc",
        ".end",
        "",
    ]
    return "\n".join(lines)


def short_deck() -> str:
    # VSHORT is an ideal 0-V source, which merges the remote RTD terminals
    # without the old 1-uOhm surrogate.
    return "\n".join([
        "* independent exact zero-ohm external RTDIN network",
        "VBIAS bias 0 2.06", "VREFSRC refsrc 0 1.25",
        "RREF bias forcep_i 430", "RFPATH forcep_i sensorp 1",
        "VSHORT sensorp sensorn 0", "RFNATH sensorn forcen_i 1",
        "RRETURN forcen_i 0 1m",
        "RSPATH sensorp sensep 1", "RSNATH sensorn sensem 1",
        "RDIAGP bias sensep 1Meg", "RDIAGN bias sensem 1Meg",
        "RWINP sensep windowp 100k", "RLOWTOPX refsrc lowth 61900",
        "RLOWBOTX lowth sensem 10000", "RHIGHTOPX refsrc highth 5900",
        "RHIGHBOTX highth 0 10000", "CDIFF sensep sensem 1.1n",
        "CGP sensep 0 100p", "CGN sensem 0 100p", ".op",
        ".control", "run", "let low_margin=v(windowp)-v(lowth)-0.004",
        "print low_margin", ".endc", ".end", "",
    ])


def short_initial_deck() -> str:
    """Healthy 100-ohm operating point used as the exact-short initial state."""
    return "\n".join([
        "* healthy initial point for exact short transient",
        "VBIAS bias 0 2.06", "VREFSRC refsrc 0 1.25",
        "RREF bias forcep_i 430", "RFPATH forcep_i sensorp 1",
        "RRTD sensorp sensorn 100", "RFNATH sensorn forcen_i 1",
        "RRETURN forcen_i 0 1m", "RSPATH sensorp sensep 1",
        "RSNATH sensorn sensem 1", "RDIAGP bias sensep 1Meg",
        "RDIAGN bias sensem 1Meg", "RWINP sensep windowp 100k",
        "RLOWTOPX refsrc lowth 61900", "RLOWBOTX lowth sensem 10000",
        "RHIGHTOPX refsrc highth 5900", "RHIGHBOTX highth 0 10000",
        "CDIFF sensep sensem 1.1n", "CGP sensep 0 100p",
        "CGN sensem 0 100p", ".op", ".control", "run",
        "print op v(sensep) v(sensem)", ".endc", ".end", "",
    ])


def short_postfault_deck(sensep: float, sensem: float) -> str:
    """Exact zero-ohm post-fault transient, initialized from ngspice healthy OP."""
    return "\n".join([
        "* exact zero-ohm post-fault transient; remote RTD nodes are merged",
        "VBIAS bias 0 2.06", "VREFSRC refsrc 0 1.25",
        "RREF bias forcep_i 430", "RFPATH forcep_i sensorp 1",
        "VSHORT sensorp sensorn 0", "RFNATH sensorn forcen_i 1",
        "RRETURN forcen_i 0 1m", "RSPATH sensorp sensep 1",
        "RSNATH sensorn sensem 1", "RDIAGP bias sensep 1Meg",
        "RDIAGN bias sensem 1Meg", "RWINP sensep windowp 100k",
        "RLOWTOPX refsrc lowth 61900", "RLOWBOTX lowth sensem 10000",
        "RHIGHTOPX refsrc highth 5900", "RHIGHBOTX highth 0 10000",
        "CDIFF sensep sensem 1.1n", "CGP sensep 0 100p",
        "CGN sensem 0 100p", f".ic V(sensep)={sensep:.12g} V(sensem)={sensem:.12g}",
        ".tran 1n 3u uic", ".control", "run",
        "let low_margin=v(windowp)-v(lowth)-0.004",
        "meas tran cross WHEN low_margin=-0.020 FALL=1",
        ".endc", ".end", "",
    ])


def _short_zero_network(model, p):
    """Return a two-state partition for an exact sensorp=sensorn node merge."""
    nodes = ("forcep_i", "sensor", "forcen_i", "sensep", "sensem",
             "windowp", "lowth", "highth")
    dynamic = ("sensep", "sensem")
    static = tuple(n for n in nodes if n not in dynamic)
    ix = {n: i for i, n in enumerate(nodes)}
    matrix = [[0.0] * len(nodes) for _ in nodes]
    rhs = [0.0] * len(nodes)

    def edge(a, b, resistance):
        g = 1.0 / resistance
        for source, other in ((a, b), (b, a)):
            if source not in ix:
                continue
            row = ix[source]
            matrix[row][row] += g
            if other in ix:
                matrix[row][ix[other]] -= g
            elif other == "bias":
                rhs[row] += g * p.vb
            elif other == "refsrc":
                rhs[row] += g * p.vref

    def sink(node, current):
        rhs[ix[node]] -= current

    edge("bias", "forcep_i", p.rref)
    edge("forcep_i", "sensor", 1.0)
    edge("sensor", "forcen_i", 1.0)
    edge("forcen_i", "gnd", model.RRETURN)
    edge("sensor", "sensep", 1.0)
    edge("sensor", "sensem", 1.0)
    edge("bias", "sensep", p.rdiag)
    edge("bias", "sensem", p.rdiag_n or p.rdiag)
    sink("sensep", p.ileak_max_p); sink("sensem", p.ileak_max_n)
    edge("sensep", "windowp", p.rwin); sink("windowp", p.ileak_window)
    sink("lowth", p.ileak_low); sink("highth", p.ileak_high)
    edge("refsrc", "lowth", p.rlt); edge("lowth", "sensem", p.rlb)
    edge("refsrc", "highth", p.rht); edge("highth", "gnd", p.rhb)
    ia = [ix[n] for n in static]; idyn = [ix[n] for n in dynamic]
    aa = [[matrix[r][c] for c in ia] for r in ia]
    ad = [[matrix[r][c] for c in idyn] for r in ia]
    da = [[matrix[r][c] for c in ia] for r in idyn]
    dd = [[matrix[r][c] for c in idyn] for r in idyn]
    ba = [rhs[r] for r in ia]; bd = [rhs[r] for r in idyn]

    def current_for(state):
        srhs = [ba[r] - sum(ad[r][c] * state[c] for c in range(2)) for r in range(len(ia))]
        sv = model.linear_solve(aa, srhs)
        full = {n: 0.0 for n in nodes}
        full.update({n: sv[j] for j, n in enumerate(static)})
        full.update({n: state[j] for j, n in enumerate(dynamic)})
        cur = [bd[r] - sum(da[r][c] * sv[c] for c in range(len(ia)))
               - sum(dd[r][c] * state[c] for c in range(2)) for r in range(2)]
        return cur, full
    q, _ = current_for([0.0, 0.0]); c1, _ = current_for([1.0, 0.0]); c2, _ = current_for([0.0, 1.0])
    g = [[q[r] - c1[r], q[r] - c2[r]] for r in range(2)]
    return current_for, g


def exact_short_python_cross(model, params, initial_sensep: float | None = None,
                             initial_sensem: float | None = None) -> tuple[float | None, float]:
    initial = model.dc("healthy", 100.0, 1.0, params)
    current_for, _ = _short_zero_network(model, params)
    cap = [[params.cground + params.cdiff, -params.cdiff],
           [-params.cdiff, params.cground + params.cdiff]]
    q, _ = current_for([0.0, 0.0]); c1, _ = current_for([1.0, 0.0]); c2, _ = current_for([0.0, 1.0])
    g = [[q[r] - c1[r], q[r] - c2[r]] for r in range(2)]
    dt = 1e-9
    system = [[cap[r][c] / dt + g[r][c] for c in range(2)] for r in range(2)]
    state = [initial["sensep"] if initial_sensep is None else initial_sensep,
             initial["sensem"] if initial_sensem is None else initial_sensem]
    crossing = None; margin = 0.0
    for step in range(3001):
        _, full = current_for(state)
        margin = full["windowp"] - full["lowth"] - params.voffl
        if margin <= -model.FAULT_OVERDRIVE_V and crossing is None:
            crossing = step * dt
        if step == 3000:
            break
        next_rhs = [cap[r][0] / dt * state[0] + cap[r][1] / dt * state[1] + q[r] for r in range(2)]
        state = model.linear_solve(system, next_rhs)
    return crossing, margin


def _cross_seconds(output: str) -> float:
    match = re.search(r"\bcross\s*=\s*([-+0-9.eE]+)", output)
    if not match:
        raise RuntimeError(f"missing cross measurement in ngspice output:\n{output}")
    return float(match.group(1))


def _printed_margin(output: str) -> float:
    match = re.search(r"\blow_margin\s*=\s*([-+0-9.eE]+)", output)
    if not match:
        raise RuntimeError(f"missing short margin in ngspice output:\n{output}")
    return float(match.group(1))


def _node_voltage(output: str, node: str) -> float:
    match = re.search(rf"v\({node}\)\s*=\s*([-+0-9.eE]+)", output, re.IGNORECASE)
    if match is None:
        match = re.search(rf"^\s*{node}\s+([-+0-9.eE]+)\s*$", output,
                          re.IGNORECASE | re.MULTILINE)
    if not match:
        raise RuntimeError(f"missing initial {node} voltage in ngspice output:\n{output}")
    return float(match.group(1))


def main() -> None:
    model = _load_model()
    params = _nominal_params(model)
    out: list[dict[str, object]] = []
    for case in CASES:
        path = HERE / f"ngspice_{case.lower().replace('+', 'p').replace('-', 'm')}.cir"
        path.write_text(deck(case))
        run = subprocess.run(["ngspice", "-b", str(path)], capture_output=True,
                             text=True, check=True)
        (HERE / f"{path.stem}.out").write_text(run.stdout + run.stderr)
        ng_cross_ms = (_cross_seconds(run.stdout + run.stderr) - 10e-6) * 1e3
        py_cross, py_final_margin = model.integrate(case, 100.0, 1.0, params)
        if py_cross is None:
            raise RuntimeError(f"Python model did not cross for {case}")
        py_cross_ms = py_cross * 1e3
        initial = model.dc("healthy", 100.0, 1.0, params)
        py_initial_margin = (initial["highth"] - initial["windowp"] - params.voffh
                             if case in ("SENSE+", "FORCE-")
                             else initial["windowp"] - initial["lowth"] - params.voffl)
        difference_us = abs(ng_cross_ms - py_cross_ms) * 1e3
        if difference_us > CROSS_TOLERANCE_US:
            raise RuntimeError(f"Python/ngspice crossing mismatch {case}: {difference_us} us")
        out.append({
            "case": case,
            "ngspice_cross_ms_after_open": ng_cross_ms,
            "python_cross_ms": py_cross_ms,
            "cross_difference_us": difference_us,
            "python_initial_healthy_margin_v": py_initial_margin,
            "python_final_margin_v": py_final_margin,
            "returncode": run.returncode,
        })

    initial_path = HERE / "ngspice_short0_initial.cir"
    initial_path.write_text(short_initial_deck())
    initial_run = subprocess.run(["ngspice", "-b", str(initial_path)], capture_output=True,
                                 text=True, check=True)
    initial_text = initial_run.stdout + initial_run.stderr
    (HERE / f"{initial_path.stem}.out").write_text(initial_text)
    initial_p = _node_voltage(initial_text, "sensep")
    initial_m = _node_voltage(initial_text, "sensem")
    post_path = HERE / "ngspice_short0_transient.cir"
    post_path.write_text(short_postfault_deck(initial_p, initial_m))
    run = subprocess.run(["ngspice", "-b", str(post_path)], capture_output=True,
                         text=True, check=True)
    post_text = run.stdout + run.stderr
    (HERE / f"{post_path.stem}.out").write_text(post_text)
    ng_cross_ms = (_cross_seconds(post_text)) * 1e3
    py_cross, py_final_margin = exact_short_python_cross(model, params, initial_p, initial_m)
    if py_cross is None:
        raise RuntimeError("Python exact-short model did not cross")
    py_cross_ms = py_cross * 1e3
    difference_us = abs(ng_cross_ms - py_cross_ms) * 1e3
    if difference_us > CROSS_TOLERANCE_US:
        raise RuntimeError(f"Python/ngspice exact-short mismatch: {difference_us} us")
    out.append({
        "case": "SHORT_0OHM_EXACT",
        "ngspice_cross_ms_after_fault": ng_cross_ms,
        "python_cross_ms_after_fault": py_cross_ms,
        "cross_difference_us": difference_us,
        "python_final_margin_v": py_final_margin,
        "initial_sensep_v_from_ngspice": initial_p,
        "initial_sensem_v_from_ngspice": initial_m,
        "zero_ohm_model": "VSHORT ideal 0-V node merge with ngspice healthy OP initial state",
        "returncode": run.returncode,
    })
    receipt = {
        "schema": "rtd_fullnetwork_ngspice_cases.v2",
        "cases": out,
        "switch_protocol": "closed at t=0, falling control opens at 10 us",
        "cross_comparison_tolerance_us": CROSS_TOLERANCE_US,
        "scope": "independent representative checks; not whole-range proof",
    }
    (HERE / "ngspice_cases.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
