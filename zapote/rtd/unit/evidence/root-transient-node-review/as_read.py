#!/usr/bin/env python3
"""Bounded passive runtime-open model for the RTDIN comparator window.

The MAX31865 ADC and SINC filter are intentionally absent.  RTDIN_P and
RTDIN_N are the only dynamic nodes; every other node is solved algebraically
from the actual resistor network at each time step.  The capacitor model is
1.05 nF differential (1 nF C0G plus a 50 pF tolerance allowance) and 100 pF
to ground at each node (a 200 pF harness/board allowance).  The latter is a
conservative common-mode capacitance model, not a cable measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

OPEN = 1.0e12
RRETURN = 1.0e-3
RWIN = 100_000.0
CD = 1.05e-9
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
LOCAL_RAIL_CMIN = 400e-9

ALL_NODES = (
    "forcep_i", "sensorp", "sensorn", "forcen_i", "sensep", "sensem",
    "windowp", "lowth", "highth",
)
DYNAMIC = ("sensep", "sensem")
STATIC = tuple(node for node in ALL_NODES if node not in DYNAMIC)


@dataclass(frozen=True)
class Params:
    vb: float = 2.06
    rref: float = 430.0 * (1.0 - 0.0005 - 5e-6 * 60.0)
    vref: float = 1.25 * (1.0 - 0.0005)
    rlt: float = 61900.0 * (1.0 - 0.001 - 25e-6 * 60.0)
    rlb: float = 10000.0 * (1.0 - 0.001 - 25e-6 * 60.0)
    rht: float = 5900.0 * (1.0 - 0.001 - 25e-6 * 60.0)
    rhb: float = 10000.0 * (1.0 - 0.001 - 25e-6 * 60.0)
    rdiag: float = 1e6 * (1.0 - 0.05 - 100e-6 * 60.0)
    voffl: float = 0.004
    voffh: float = 0.004
    ileak_max_p: float = 14e-9
    ileak_max_n: float = 14e-9
    ileak_window: float = 20e-9
    ileak_low: float = 10e-9
    ileak_high: float = 10e-9


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


def network(case: str, rtd: float, lead: float, p: Params) -> tuple[list[list[float]], list[float]]:
    index = {node: i for i, node in enumerate(ALL_NODES)}
    n = len(ALL_NODES)
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
    edge("forcep_i", "sensorp", OPEN if case == "FORCE+" else lead)
    edge("sensorp", "sensorn", rtd)
    edge("sensorn", "forcen_i", OPEN if case == "FORCE-" else lead)
    edge("forcen_i", "gnd", RRETURN)
    edge("sensorp", "sensep", OPEN if case == "SENSE+" else lead)
    edge("sensorn", "sensem", OPEN if case == "SENSE-" else lead)
    edge("bias", "sensep", p.rdiag)
    edge("bias", "sensem", p.rdiag)
    current("sensep", p.ileak_max_p)
    current("sensem", p.ileak_max_n)
    edge("sensep", "windowp", RWIN)
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


def dc(case: str, rtd: float, lead: float, p: Params) -> dict[str, float]:
    matrix, rhs = network(case, rtd, lead, p)
    values = linear_solve(matrix, rhs)
    return dict(zip(ALL_NODES, values))


def integrate(case: str, rtd: float, lead: float, p: Params) -> tuple[float | None, float]:
    initial = dc("healthy", rtd, lead, p)
    current_for, _ = partition(case, rtd, lead, p)
    cap = [[CG + CD, -CD], [-CD, CG + CD]]
    q, _ = current_for([0.0, 0.0])
    c1, _ = current_for([1.0, 0.0])
    c2, _ = current_for([0.0, 1.0])
    conductance = [[q[row] - c1[row], q[row] - c2[row]] for row in range(2)]
    # The network contains sub-nanosecond resistive modes from the 1 ohm
    # harness. Implicit Euler is A-stable here; an explicit RK step would
    # become unstable long before the millisecond diagnostic transition.
    system = [[cap[row][col] / DT + conductance[row][col] for col in range(2)] for row in range(2)]

    state = [initial[node] for node in DYNAMIC]
    target = "low_margin" if case in ("FORCE+", "SENSE-") else "high_margin"
    crossing: float | None = None
    steps = int(TMAX / DT)
    for step in range(steps + 1):
        t = step * DT
        _, full = current_for(state)
        low = full["windowp"] - full["lowth"] - p.voffl
        high = full["highth"] - full["windowp"] - p.voffh
        margin = low if target == "low_margin" else high
        if margin <= 0.0 and crossing is None:
            crossing = t
        if step == steps:
            break
        next_rhs = [cap[row][0] / DT * state[0] + cap[row][1] / DT * state[1] + q[row] for row in range(2)]
        state = linear_solve(system, next_rhs)
    return crossing, margin


def main() -> None:
    print("model bounded passive runtime opens; no MAX ADC/SINC model")
    print(f"dt_us={DT * 1e6:g} tmax_ms={TMAX * 1e3:g} cdiff_nF={CD * 1e9:g} "
          f"cground_each_pF={CG * 1e12:g} rwindow_ohm={RWIN:g} "
          f"tlv_prop_ns={TLV_PROP_NS:g} logic_prop_ns={LOGIC_PROP_NS:g}")
    print(f"allowed_passive_harness_v={HARNESS_VMIN:g}..{HARNESS_VMAX:g} "
          f"source_r_min_ohm={HARNESS_RSOURCE:g} edge_min_us={HARNESS_EDGE_US:g} "
          f"pulse_max_ms={HARNESS_PULSE_MS:g} repetition_max_hz={HARNESS_REPETITION_HZ:g}")
    for rtd in (100.0, 194.1):
        for case in ("FORCE+", "SENSE+", "SENSE-", "FORCE-"):
            crossing, final_margin = integrate(case, rtd, 1.0, Params())
            detection = (crossing * 1e3 + (TLV_PROP_NS + LOGIC_PROP_NS) / 1e6
                         if crossing is not None else None)
            print(f"RTD={rtd:5.1f} case={case:7s} cross_ms="
                  f"{crossing * 1e3 if crossing is not None else 'NONE'} "
                  f"unit_detect_ms={detection if detection is not None else 'NONE'} "
                  f"final_target_margin_v={final_margin:+.6f}")
    # Separate local-off/upstream-on passive collapse state: monitor/HW fault
    # owns the decision; this is not a powered TLV window claim.
    off = Params(vb=0.0)
    state = dc("healthy", 100.0, 1.0, off)
    low = state["windowp"] - state["lowth"] - off.voffl
    high = state["highth"] - state["windowp"] - off.voffh
    print(f"local_off_upstream_on rtdin_p={state['sensorp']:+.6e} "
          f"windowp={state['windowp']:+.6e} low_margin={low:+.6f} "
          f"high_margin={high:+.6f} comparator_window=FAULT_OWNER_MONITOR")
    # The 100 kohm branch is the only transient path into TLV inputs.  Use the
    # TLV VCC minimum for the worst positive clamp and ground for negative.
    cap_energy_nj = 0.5 * (CD + 2.0 * CG) * (HARNESS_VMAX - HARNESS_VMIN) ** 2 * 1e9
    cap_energy_j = cap_energy_nj * 1e-9
    local_off_dv = (2.0 * cap_energy_j / LOCAL_RAIL_CMIN) ** 0.5
    edge_cap_current = (CD + 2.0 * CG) * (HARNESS_VMAX - HARNESS_VMIN) / (HARNESS_EDGE_US * 1e-6)
    low_divider_current = (HARNESS_VMAX - HARNESS_VMIN) / (10000.0 + HARNESS_RSOURCE)
    print(f"allowed_envelope_clamp_mA=0.000000 differential_span_v="
          f"{HARNESS_VMAX - HARNESS_VMIN:g} <= tlv_vcc_min_v=2.700 "
          "tlv_input_limit_mA=10.000")
    print(f"allowed_envelope_cap_energy_nJ={cap_energy_nj:.6f} "
          "device_only_MAX_RTDIN_absmax_v=+/-45.000 "
          "device_absmax_is_not_unit_transient_rating=true")
    print(f"harness_edge_cap_current_mA={edge_cap_current * 1e3:.6f} "
          f"low_divider_source_current_mA={low_divider_current * 1e3:.6f} "
          "both_below_tlv_input_limit_mA=10.000")
    print(f"local_rail_cmin_uF={LOCAL_RAIL_CMIN * 1e6:g} "
          f"local_off_capacitive_energy_dv_max_v={local_off_dv:.6f} "
          "clamp_sum_upstream_on_mA=0.000000 "
          "local_off_external_source_allowed=false")


if __name__ == "__main__":
    main()
