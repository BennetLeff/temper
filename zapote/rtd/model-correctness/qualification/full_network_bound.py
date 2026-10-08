#!/usr/bin/env python3
"""Bounded passive runtime-open model for the RTDIN comparator window.

The MAX31865 ADC and SINC filter are intentionally absent. RTDIN_P and RTDIN_N
(the `sensep`/`sensem` nodes at the ADC pins) are the only dynamic nodes; every
other node is solved algebraically from the actual resistor network at each
time step.  The capacitor model is
0.94..1.10 nF differential (1 nF C0G, +5% tolerance, 30 ppm/C, with outward
rounding) and 0..200 pF to ground at each node (a conservative independent-pin
superset of the 200 pF harness/board allowance).  The latter is a
conservative common-mode capacitance model, not a cable measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
import json
from pathlib import Path

# A source open is an ideal missing edge in the analytic graph.  The SPICE
# decks use Roff=1e12 only as a simulator representation and report that
# distinction explicitly.
OPEN = float("inf")
RRETURN = 1.0e-3
RWIN = 100_000.0
# C0603C102J5GACTU is 1 nF C0G, +/-5%; 30 ppm/C and outward rounding produce
# the declared 0.94..1.10 nF differential interval.
CD = 1.10e-9
CG = 100e-12
DT = 1.0e-6
TMAX = 0.100
TLV_PROP_NS = 55.0
LOGIC_PROP_NS = 10.0
HARNESS_VMIN = -0.2
HARNESS_VMAX = 2.5
HARNESS_RSOURCE = 1_000.0
HARNESS_EDGE_US = 10.0
HARNESS_PULSE_MS = 1.0
HARNESS_REPETITION_HZ = 1.0
# Four post-ferrite 100 nF bypasses are present (MAX VDD, low/high
# comparators, and window AND).  The model accepts each only after a
# temperature/voltage characterization or lot bound of >=45 nF; hence the
# aggregate Cmin is 180 nF rather than the nominal 400 nF.
LOCAL_RAIL_CMIN = 180e-9
FAULT_OVERDRIVE_V = 0.020

ALL_NODES = (
    "forcep_i", "sensorp", "sensorn", "forcen_i", "sensep", "sensem",
    "windowp", "lowth", "highth",
)
DYNAMIC = ("sensep", "sensem")
STATIC = tuple(node for node in ALL_NODES if node not in DYNAMIC)


@dataclass(frozen=True)
class Params:
    vb: float = 2.06
    rref: float = 430.0
    vref: float = 1.25
    rlt: float = 61900.0
    rlb: float = 10000.0
    rht: float = 5900.0
    rhb: float = 10000.0
    rdiag: float = 1e6
    voffl: float = 0.004
    voffh: float = 0.004
    ileak_max_p: float = 14e-9
    ileak_max_n: float = 14e-9
    ileak_window: float = 20e-9
    ileak_low: float = 5e-9
    ileak_high: float = 5e-9
    rwin: float = 100000.0
    cdiff: float = 1.10e-9
    cground: float = 100e-12
    rdiag_n: float | None = None


def linear_solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    augmented = [row[:] + [value] for row, value in zip(matrix, rhs)]
    n = len(rhs)
    for column in range(n):
        pivot = max(range(column, n), key=lambda row: abs(augmented[row][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        if abs(scale) < 1e-30:
            raise ValueError("singular transient model matrix")
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(n):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [
                    augmented[row][i] - factor * augmented[column][i]
                    for i in range(n + 1)
                ]
    return [augmented[row][-1] for row in range(n)]


def network(case: str, rtd: float, lead: float | tuple[float, float, float, float], p: Params) -> tuple[list[list[float]], list[float]]:
    index = {node: i for i, node in enumerate(ALL_NODES)}
    n = len(ALL_NODES)
    if isinstance(lead, tuple):
        lead_fp, lead_fn, lead_sp, lead_sn = lead
    else:
        lead_fp = lead_fn = lead_sp = lead_sn = lead
    matrix = [[0.0] * n for _ in range(n)]
    rhs = [0.0] * n

    def edge(a: str, b: str, resistance: float) -> None:
        g = 1.0 / resistance
        for source, other in ((a, b), (b, a)):
            if source not in index:
                continue
            row = index[source]
            matrix[row][row] += g
            if other in index:
                matrix[row][index[other]] -= g
            elif other == "bias":
                rhs[row] += g * p.vb
            elif other == "refsrc":
                rhs[row] += g * p.vref

    def current(node: str, leaving: float) -> None:
        rhs[index[node]] -= leaving

    edge("bias", "forcep_i", p.rref)
    edge("forcep_i", "sensorp", OPEN if case == "FORCE+" else lead_fp)
    edge("sensorp", "sensorn", rtd)
    edge("sensorn", "forcen_i", OPEN if case == "FORCE-" else lead_fn)
    edge("forcen_i", "gnd", RRETURN)
    edge("sensorp", "sensep", OPEN if case == "SENSE+" else lead_sp)
    edge("sensorn", "sensem", OPEN if case == "SENSE-" else lead_sn)
    edge("bias", "sensep", p.rdiag)
    edge("bias", "sensem", p.rdiag if p.rdiag_n is None else p.rdiag_n)
    current("sensep", p.ileak_max_p)
    current("sensem", p.ileak_max_n)
    edge("sensep", "windowp", p.rwin)
    current("windowp", p.ileak_window)
    current("lowth", p.ileak_low)
    current("highth", p.ileak_high)
    edge("refsrc", "lowth", p.rlt)
    edge("lowth", "sensem", p.rlb)
    edge("refsrc", "highth", p.rht)
    edge("highth", "gnd", p.rhb)
    return matrix, rhs


def partition(case: str, rtd: float, lead: float, p: Params) -> tuple[list[list[float]], list[float]]:
    matrix, rhs = network(case, rtd, lead, p)
    ix = {node: i for i, node in enumerate(ALL_NODES)}
    ia = [ix[node] for node in STATIC]
    idyn = [ix[node] for node in DYNAMIC]
    aa = [[matrix[row][col] for col in ia] for row in ia]
    ad = [[matrix[row][col] for col in idyn] for row in ia]
    da = [[matrix[row][col] for col in ia] for row in idyn]
    dd = [[matrix[row][col] for col in idyn] for row in idyn]
    ba = [rhs[row] for row in ia]
    bd = [rhs[row] for row in idyn]
    aa_inv_columns = []
    for col in range(2):
        unit = [1.0 if row == col else 0.0 for row in range(len(ia))]
        aa_inv_columns.append(linear_solve(aa, unit))

    def current_for(vdyn: list[float]) -> tuple[list[float], dict[str, float]]:
        rhs_static = [ba[row] - sum(ad[row][col] * vdyn[col] for col in range(2)) for row in range(len(ia))]
        vstatic = linear_solve(aa, rhs_static)
        full = {node: 0.0 for node in ALL_NODES}
        for pos, node in enumerate(STATIC):
            full[node] = vstatic[pos]
        for pos, node in enumerate(DYNAMIC):
            full[node] = vdyn[pos]
        cur = [bd[row] - sum(da[row][col] * vstatic[col] for col in range(len(ia))) -
               sum(dd[row][col] * vdyn[col] for col in range(2)) for row in range(2)]
        return cur, full

    # Return the affine dynamic current function and keep the static solver
    # closure.  The unused inverse columns make the intended linear partition
    # explicit and are checked by the same Gaussian solver.
    del aa_inv_columns
    return current_for, {}


def dc(case: str, rtd: float, lead: float | tuple[float, float, float, float], p: Params) -> dict[str, float]:
    matrix, rhs = network(case, _safe_rtd(rtd), lead, p)
    values = linear_solve(matrix, rhs)
    return dict(zip(ALL_NODES, values))


def _safe_rtd(rtd: float) -> float:
    """Use a numerical limiting value; exact zero is the merged-node model."""
    return max(rtd, 1.0e-6)


def _integrate_transition(
    initial_case: str,
    initial_rtd: float,
    target_case: str,
    target_rtd: float,
    lead: float,
    p: Params,
    target: str,
) -> tuple[float | None, float]:
    initial = dc(initial_case, initial_rtd, lead, p)
    current_for, _ = partition(target_case, target_rtd, lead, p)
    cap = [[p.cground + p.cdiff, -p.cdiff], [-p.cdiff, p.cground + p.cdiff]]
    q, _ = current_for([0.0, 0.0])
    c1, _ = current_for([1.0, 0.0])
    c2, _ = current_for([0.0, 1.0])
    conductance = [[q[row] - c1[row], q[row] - c2[row]] for row in range(2)]
    # The network contains sub-nanosecond resistive modes from the 1 ohm
    # harness. Implicit Euler is A-stable here; an explicit RK step would
    # become unstable long before the millisecond diagnostic transition.
    system = [[cap[row][col] / DT + conductance[row][col] for col in range(2)] for row in range(2)]

    state = [initial[node] for node in DYNAMIC]
    crossing: float | None = None
    steps = int(TMAX / DT)
    for step in range(steps + 1):
        t = step * DT
        _, full = current_for(state)
        low = full["windowp"] - full["lowth"] - p.voffl
        high = full["highth"] - full["windowp"] - p.voffh
        margin = low if target == "low_margin" else high
        # The TLV propagation allocation is only applied after a conservative
        # 20 mV comparator overdrive. The continuous certificate separately
        # proves positive final overdrive reserve for each case.
        if margin <= -FAULT_OVERDRIVE_V and crossing is None:
            crossing = t
        if step == steps:
            break
        next_rhs = [cap[row][0] / DT * state[0] + cap[row][1] / DT * state[1] + q[row] for row in range(2)]
        state = linear_solve(system, next_rhs)
    return crossing, margin


def integrate(case: str, rtd: float, lead: float, p: Params) -> tuple[float | None, float]:
    target = "low_margin" if case in ("FORCE+", "SENSE-") else "high_margin"
    return _integrate_transition("healthy", rtd, case, rtd, lead, p, target)


def integrate_short(
    initial_rtd: float, target_rtd: float, lead: float, p: Params
) -> tuple[float | None, float]:
    """Bound a resistance step from a healthy RTD to a short condition."""
    # The physical zero-ohm case is an exact node merge.  The time-domain
    # helper uses its analytic 1-uOhm limiting value only to retain a finite
    # nodal matrix; the independent SPICE check uses an ideal 0-V source.
    target = _safe_rtd(target_rtd)
    return _integrate_transition(
        "healthy", initial_rtd, "healthy", target, lead, p, "low_margin"
    )


def _solve_static_partition(case: str, rtd: float, lead: float | tuple[float, float, float, float], p: Params,
                            initial_rtd: float | None = None, low_fault: bool = False):
    """Return target G, output affine margin, and initial/final states."""
    matrix, rhs = network(case, _safe_rtd(rtd), lead, p)
    ix = {node: i for i, node in enumerate(ALL_NODES)}
    ia = [ix[node] for node in STATIC]
    idyn = [ix[node] for node in DYNAMIC]
    aa = [[matrix[row][col] for col in ia] for row in ia]
    ad = [[matrix[row][col] for col in idyn] for row in ia]
    da = [[matrix[row][col] for col in ia] for row in idyn]
    dd = [[matrix[row][col] for col in idyn] for row in idyn]
    ba = [rhs[row] for row in ia]
    bd = [rhs[row] for row in idyn]

    def f(x: list[float]) -> tuple[list[float], dict[str, float]]:
        static_rhs = [ba[row] - sum(ad[row][col] * x[col] for col in range(2))
                      for row in range(len(ia))]
        static = linear_solve(aa, static_rhs)
        full = {node: 0.0 for node in ALL_NODES}
        full.update({node: static[j] for j, node in enumerate(STATIC)})
        full.update({node: x[j] for j, node in enumerate(DYNAMIC)})
        current = [bd[row] - sum(da[row][col] * static[col] for col in range(len(ia)))
                   - sum(dd[row][col] * x[col] for col in range(2)) for row in range(2)]
        return current, full

    q, zero = f([0.0, 0.0])
    c1, one = f([1.0, 0.0])
    c2, two = f([0.0, 1.0])
    g = [[q[row] - c1[row], q[row] - c2[row]] for row in range(2)]
    target_margin = (lambda full: full["windowp"] - full["lowth"] - p.voffl
                     if low_fault or case in ("FORCE+", "SENSE-")
                     else full["highth"] - full["windowp"] - p.voffh)
    k = target_margin(zero)
    w = [target_margin(one) - k, target_margin(two) - k]
    initial = dc("healthy", rtd if initial_rtd is None else initial_rtd, lead, p)
    final = dc(case, _safe_rtd(rtd), lead, p)
    e = [initial[node] - final[node] for node in DYNAMIC]
    return g, w, e, target_margin(final)


def _mat_inv(a: list[list[float]]) -> list[list[float]]:
    det = a[0][0] * a[1][1] - a[0][1] * a[1][0]
    return [[a[1][1] / det, -a[0][1] / det],
            [-a[1][0] / det, a[0][0] / det]]


def _quad(a: list[list[float]], x: list[float]) -> float:
    return sum(x[i] * a[i][j] * x[j] for i in range(2) for j in range(2))


def _lambda_min(g: list[list[float]], c: list[list[float]]) -> float:
    # Generalized 2x2 eigenvalues of G x = lambda C x.
    ci = _mat_inv(c)
    a = ci[0][0] * g[0][0] + ci[0][1] * g[1][0]
    b = ci[0][0] * g[0][1] + ci[0][1] * g[1][1]
    d = ci[1][0] * g[0][1] + ci[1][1] * g[1][1]
    tr = a + d
    det = a * d - b * (ci[1][0] * g[0][0] + ci[1][1] * g[1][0])
    disc = max(0.0, tr * tr - 4.0 * det)
    return (tr - disc ** 0.5) / 2.0


def energy_certificate(case: str, rtd: float, lead: float | tuple[float, float, float, float], p: Params,
                       initial_rtd: float | None = None) -> dict[str, float]:
    """Passive G-energy certificate for one parameter point.

    For e=x-x_final, E=e'G e obeys dE/dt <= -2 lambda E where lambda is
    the least generalized eigenvalue of (G,C).  Cauchy-Schwarz in the
    G metric bounds |w'e| by sqrt((e0'G e0)(w'G^-1w))*exp(-lambda*t).
    This is an exact matrix bound at this parameter point; the qualification
    runner reports the envelope over its declared parameter boxes.
    """
    g, w, e, final_margin = _solve_static_partition(case, rtd, lead, p, initial_rtd)
    c = [[p.cground + p.cdiff, -p.cdiff], [-p.cdiff, p.cground + p.cdiff]]
    gi = _mat_inv(g)
    lam = _lambda_min(g, c)
    e0 = _quad(g, e)
    dual = _quad(gi, w)
    k = max(0.0, e0 * dual) ** 0.5
    remaining = -FAULT_OVERDRIVE_V - final_margin
    if remaining <= 0.0:
        raise ValueError(f"fault endpoint lacks overdrive: {case} {rtd} {final_margin}")
    bound_s = max(0.0, __import__("math").log(max(k / remaining, 1.0)) / lam)
    return {"final_margin_v": final_margin, "lambda_per_s": lam,
            "e0_g_energy": e0, "output_dual_g": dual, "k_v": k,
            "remaining_v": remaining, "bound_ms": bound_s * 1e3}


def _ranges() -> dict[str, tuple[float, float]]:
    def span(nominal: float, tol: float, tcr: float) -> tuple[float, float]:
        # Independent tolerance and temperature terms multiply.  Retain
        # full precision here; certificate output is rounded only for prose.
        dt = tcr * 60.0
        return nominal * (1.0 - tol) * (1.0 - dt), nominal * (1.0 + tol) * (1.0 + dt)
    return {
        "vb": (1.95, 2.06),
        "rref": span(430.0, 0.0005, 5e-6),
        # Outward-rounded REF2025 contract used by the Rust consumer.
        "vref": (1.24869, 1.25131),
        "rlt": span(61900.0, 0.001, 25e-6),
        "rlb": span(10000.0, 0.001, 25e-6),
        "rht": span(5900.0, 0.001, 25e-6),
        "rhb": span(10000.0, 0.001, 25e-6),
        "rdiag": (0.944e6, 1.057e6),
        # R13 (100 kΩ): +/-1%, 100 ppm/C over 60 C; outward rounded.
        "rwin": (98_000.0, 102_000.0),
        "cdiff": (0.94e-9, 1.10e-9),
        # A conservative independent-pin superset of the <=200 pF total
        # parasitic contract; C_upper remains valid for any split.
        "cground": (0.0, 200e-12),
    }


def _corner_params(rtd: float, values: tuple[float, ...], source: tuple[float, ...]) -> Params:
    rref, rlt, rlb, rht, rhb, rdp, rdn, rwin, cdiff, cground = values
    vb, vref, voffl, voffh, ip, inn, iw, il, ih = source
    return Params(vb=vb, rref=rref, vref=vref, rlt=rlt, rlb=rlb,
                  rht=rht, rhb=rhb, rdiag=rdp, voffl=voffl, voffh=voffh,
                  ileak_max_p=ip, ileak_max_n=inn, ileak_window=iw,
                  ileak_low=il, ileak_high=ih, rwin=rwin, cdiff=cdiff,
                  cground=cground, rdiag_n=rdn)


def _parallel(a: float, b: float) -> float:
    return a * b / (a + b)


def analytic_bounds(ranges: dict[str, tuple[float, float]]) -> dict[str, object]:
    """Closed bounds for states and final margins over continuous intervals."""
    vbmin, vbmax = ranges["vb"]
    vrefmin, vrefmax = ranges["vref"]
    rrefmin, rrefmax = ranges["rref"]
    rltmin, rltmax, rlbmin, rlbmax = ranges["rlt"][0], ranges["rlt"][1], ranges["rlb"][0], ranges["rlb"][1]
    rhtmin, rhtmax, rhbmin, rhbmax = ranges["rht"][0], ranges["rht"][1], ranges["rhb"][0], ranges["rhb"][1]
    rdmin, rdmax, rwmax = ranges["rdiag"][0], ranges["rdiag"][1], ranges["rwin"][1]
    L = 58e-9
    Rp = 50.0 + 194.1 + 50.0 + RRETURN
    Rn = 50.0 + 50.0 + RRETURN
    healthy_lo, healthy_hi = -L * Rp, vbmax + L * Rp
    p_lo, p_hi = vbmin - rdmax * 34e-9, vbmax + rdmax * 34e-9
    delta_p = max(p_hi - healthy_lo, healthy_hi - p_lo)
    gmm_sminus = 1.0 / rdmax + 1.0 / (rltmax + rlbmax)
    sensem_lo = vrefmin - 19e-9 / gmm_sminus
    sensem_hi = vbmax + 19e-9 / gmm_sminus
    # SENSE- uses the lower-side healthy return path (Rn), not the FORCE+
    # path (Rp); using Rp here needlessly changes the energy numerator.
    delta_m = max(sensem_hi + L * Rn, vbmax + L * Rn - sensem_lo)
    isp = (vbmax + L * Rp) / rdmin + 34e-9
    isn = ((vbmax + L * Rn) / rdmin
           + max(vrefmax + L * Rn, vbmax + L * Rn - vrefmin) / (rltmin + rlbmin)
           + 19e-9)
    delta_sminus_p = isn * Rp
    high_max = vrefmax * rhbmax / (rhtmin + rhbmax) + 5e-9 * _parallel(rhtmax, rhbmax)
    window_min = vbmin - rdmax * 34e-9 - rwmax * 20e-9
    splus_remaining = window_min - high_max - .004 - .020
    low_min_sminus = vrefmin - 19e-9 / gmm_sminus - 5e-9 * _parallel(rltmax, rlbmax)
    sensor_p_max = (vbmax * (194.1 + 50.0 + RRETURN)
                    / (rrefmin + 1.0 + 194.1 + 50.0 + RRETURN)
                    + (vbmax / rdmin + L) * Rp)
    sminus_remaining = low_min_sminus - (sensor_p_max + rwmax * 20e-9) - .004 - .020
    alpha = rltmax / (rltmax + rlbmin)
    low_min_forcep = (vrefmin * rlbmin / (rltmax + rlbmin)
                      - alpha * L * Rn - 5e-9 * _parallel(rltmax, rlbmax))
    jp = 2.0 * vbmax / rdmin + vrefmax / (rltmin + rlbmin) + L
    forcep_remaining = low_min_forcep - (jp * Rp + rwmax * 20e-9) - .004 - .020
    jm = (vbmax - vrefmin) / (rltmin + rlbmin) + L
    window_min_forcem = vbmin - jm * (rrefmax + 50.0 + 50.0) - rwmax * 20e-9
    forcem_remaining = window_min_forcem - high_max - .004 - .020
    iforce = vbmax / (rrefmin + 1.0 + 1.0 + RRETURN)
    wshort = ((iforce + jp) * 10.0
              + (vbmax / rdmin + 34e-9) * 50.0
              + (vbmax / rdmin + vrefmax / (rltmin + rlbmin) + 19e-9) * 50.0
              + rwmax * 20e-9)
    sensem_short_max = (vbmax * (50.0 + RRETURN) / (rrefmin + 1.0 + 50.0 + RRETURN)
                        + jp * Rn)
    low_short_min = (rlbmin / (rltmax + rlbmin) * (vrefmin - sensem_short_max)
                     - 5e-9 * _parallel(rltmax, rlbmax))
    short_remaining = low_short_min - wshort - .004 - .020
    return {
        "healthy_state_bounds_v": [healthy_lo, healthy_hi],
        "delta_p_v": delta_p, "delta_sminus_p_v": delta_sminus_p,
        "delta_m_v": delta_m, "delta_splus_m_v": isp * Rn,
        "reserves_v": {"FORCE+": forcep_remaining, "FORCE-": forcem_remaining,
                       "SENSE+": splus_remaining, "SENSE-": sminus_remaining,
                       "short": short_remaining},
        "assumptions": {"leak_sum_a": L, "rpath_p_ohm": Rp, "rpath_n_ohm": Rn,
                        "alpha_max": alpha, "short_zero_ohm_approx": "exact node merge; 1-uOhm only as numerical limiting value"},
    }


def main() -> None:
    ranges = _ranges()
    analytic = analytic_bounds(ranges)

    def values(which: int) -> list[float]:
        return [ranges["rref"][which], ranges["rlt"][which], ranges["rlb"][which],
                ranges["rht"][which], ranges["rhb"][which], ranges["rdiag"][which],
                ranges["rwin"][which], ranges["cdiff"][which], ranges["cground"][which]]

    def make(v: list[float], rtd: float, lead: tuple[float, float, float, float]) -> Params:
        vv = v[:6] + [v[5]] + v[6:]
        return _corner_params(rtd, tuple(vv),
                              (2.0, 1.25, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))

    lead_min, lead_max = (1.0,) * 4, (50.0,) * 4
    rdmin, rdmax = ranges["rdiag"]
    rltmin, rltmax = ranges["rlt"]
    rlbmin, rlbmax = ranges["rlb"]
    rp = analytic["assumptions"]["rpath_p_ohm"]
    rn = analytic["assumptions"]["rpath_n_ohm"]
    alpha = analytic["assumptions"]["alpha_max"]
    gmax_universal = [[1 / lead_min[2] + 1 / rdmin + 1 / ranges["rwin"][0], 0.0],
                      [0.0, 1 / lead_min[3] + 1 / rdmin + 1 / rlbmin]]
    cmax = [[ranges["cground"][1] + ranges["cdiff"][1], -ranges["cdiff"][1]],
            [-ranges["cdiff"][1], ranges["cground"][1] + ranges["cdiff"][1]]]

    def gmin_from_network(case: str, rtd: float, low_fault: bool) -> list[list[float]]:
        p = make(values(1), rtd, lead_max)
        return _solve_static_partition(case, rtd, lead_max, p, rtd, low_fault)[0]

    cases = ("FORCE+", "FORCE-", "SENSE+", "SENSE-", "SHORT")
    records = []
    for case in cases:
        if case == "SHORT":
            gmin = gmin_from_network("healthy", 10.0, True)
            gmax = [row[:] for row in gmax_universal]
            delta = [2.1, 2.1]
            coeff = [1.0, alpha]
            remaining = analytic["reserves_v"]["short"]
            transition = "short"
        elif case == "SENSE+":
            # A conservative diagonal lower box avoids relying on the RTD
            # branch that may be absent in the isolated-open topology.
            gmin = [[1 / rdmax, 0.0], [0.0, 1 / rn]]
            gmax = [[1 / rdmin, 0.0],
                    [0.0, 1 / lead_min[3] + 1 / rdmin
                     + 1 / (rltmin + rlbmin)]]
            delta = [analytic["delta_p_v"], analytic["delta_splus_m_v"]]
            coeff = [1.0, 0.0]
            remaining = analytic["reserves_v"][case]
            transition = "open"
        elif case == "SENSE-":
            gmin = [[1 / rp, 0.0], [0.0, 1 / rdmax + 1 / (rltmax + rlbmax)]]
            gmax = [[1 / lead_min[2] + 1 / rdmin, 0.0],
                    [0.0, 1 / rdmin + 1 / (rltmin + rlbmin)]]
            delta = [analytic["delta_sminus_p_v"], analytic["delta_m_v"]]
            coeff = [1.0, alpha]
            remaining = analytic["reserves_v"][case]
            transition = "open"
        else:
            gmin = gmin_from_network(case, 194.1, case == "FORCE+")
            gmax = [row[:] for row in gmax_universal]
            delta = [2.1, 2.1]
            coeff = [1.0, alpha] if case == "FORCE+" else [1.0, 0.0]
            remaining = analytic["reserves_v"][case]
            transition = "open"

        gi = _mat_inv(gmin)
        dual = sum(coeff[i] * abs(gi[i][j]) * coeff[j]
                   for i in range(2) for j in range(2))
        energy = sum(gmax[i][i] * delta[i] ** 2 for i in range(2))
        lam = _lambda_min(gmin, cmax)
        k = (energy * dual) ** 0.5
        passive_bound = max(0.0, math.log(max(k / remaining, 1.0)) / lam * 1e3)
        total_bound = passive_bound + (TLV_PROP_NS + LOGIC_PROP_NS) / 1e6
        record = {
            "case": case,
            "transition": transition,
            "initial_rt_range_ohm": [100.0, 194.1],
            "target_rt_range_ohm": [0.0, 10.0] if case == "SHORT" else [100.0, 194.1],
            "rt_range_ohm": [0.0, 10.0] if case == "SHORT" else [100.0, 194.1],
            "lead_ranges_ohm": [[1.0, 50.0]] * 4,
            "g_min": gmin,
            "g_max_diag": [gmax[0][0], gmax[1][1]],
            "c_max": cmax,
            "delta_v": delta,
            "lambda_min_per_s": lam,
            "energy_max": energy,
            "dual_max": dual,
            "k_upper_v": k,
            "remaining_v": remaining,
            "passive_bound_ms": passive_bound,
            "bound_ms": total_bound,
            "comparator_logic_allocation_ms": (TLV_PROP_NS + LOGIC_PROP_NS) / 1e6,
            "scope": "continuous passive-network certificate; device applicability remains conditional",
        }
        records.append(record)
        print(record)

    receipt = {
        "schema": "rtd_full_network_energy_certificate.v3",
        "parameter_ranges": ranges,
        "analytic_bounds": analytic,
        "records": records,
        "overall_certificate_bound_ms": max(r["bound_ms"] for r in records),
        "capacitor_model": "Cdiff 0.94..1.10 nF including tolerance/TCR outward rounding; each Cground pin 0..200 pF (superset)",
        "transition_coverage": "five canonical fault cases; continuous RTD 100..194.1 ohm opens and 0..10 ohm shorts; four independent leads 1..50 ohm",
        "method": "G-energy decay with conservative diagonal or Schur Gmin, incident-conductance Gmax, and continuous state/margin inequalities",
        "comparator_propagation_ns": {"tlv3201": TLV_PROP_NS, "fault_logic": LOGIC_PROP_NS},
        "short_zero_ohm_model": "exact node merge; Python time-domain helper uses only a numerical limiting conductance",
        "qualification_status": "conditional model certificate; MAX internal paths, comparator applicability, harness and physical validation remain separate",
    }
    Path(__file__).with_suffix(".json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("overall_certificate_bound_ms", receipt["overall_certificate_bound_ms"])


if __name__ == "__main__":
    main()
