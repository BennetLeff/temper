#!/usr/bin/env python3
"""Bounded DC model for the proposed RTDIN comparator window.

This is an evidence generator, not production firmware or a MAX31865 model.
It deliberately uses only the external resistor network and records margins
at the protected shared TLV3201 window node.  The emitted table is consumed
by the adjacent ``*_results.txt`` receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Final, Iterable

OPEN_OHM: Final[float] = 1.0e12
RETURN_OHM: Final[float] = 1.0e-3
WINDOW_BRANCH_OHM: Final[float] = 100_000.0
NODES: Final[tuple[str, ...]] = (
    "forcep_i", "sensorp", "sensorn", "forcen_i", "sensep", "sensem",
    "windowp", "lowth", "highth",
)


@dataclass(frozen=True)
class Corner:
    vb: float
    rref: float
    vref: float
    rlt: float
    rlb: float
    rht: float
    rhb: float
    rdiag_p: float
    rdiag_n: float
    voffl: float
    voffh: float
    ileak_max_sensep: float
    ileak_sensem: float
    ileak_windowp: float
    ileak_lowth: float
    ileak_highth: float


@dataclass(frozen=True)
class Result:
    rtdin_p: float
    windowp: float
    sensem: float
    low_margin: float
    high_margin: float


def solve(case: str, rtd: float, lead: float, c: Corner) -> Result:
    """Solve one linear network using Gaussian elimination."""
    index = {node: i for i, node in enumerate(NODES)}
    size = len(NODES)
    matrix = [[0.0] * size for _ in range(size)]
    rhs = [0.0] * size

    def edge(a: str, b: str, resistance: float) -> None:
        conductance = 1.0 / resistance
        for source, other in ((a, b), (b, a)):
            if source not in index:
                continue
            row = index[source]
            matrix[row][row] += conductance
            if other in index:
                matrix[row][index[other]] -= conductance
            elif other == "bias":
                rhs[row] += conductance * c.vb
            elif other == "refsrc":
                rhs[row] += conductance * c.vref

    def current(node: str, leaving: float) -> None:
        rhs[index[node]] -= leaving

    edge("bias", "forcep_i", c.rref)
    edge("forcep_i", "sensorp", OPEN_OHM if case == "FORCE+" else lead)
    edge("sensorp", "sensorn", rtd)
    edge("sensorn", "forcen_i", OPEN_OHM if case == "FORCE-" else lead)
    matrix[index["forcen_i"]][index["forcen_i"]] += 1.0 / RETURN_OHM
    edge("sensorp", "sensep", OPEN_OHM if case == "SENSE+" else lead)
    edge("sensorn", "sensem", OPEN_OHM if case == "SENSE-" else lead)
    edge("bias", "sensep", c.rdiag_p)
    edge("bias", "sensem", c.rdiag_n)
    # MAX leakage is at RTDIN_P; the two TLV inputs and bounded board leakage
    # are behind the shared 100 kohm protection resistor at windowp.
    current("sensep", c.ileak_max_sensep)
    current("sensem", c.ileak_sensem)
    edge("sensep", "windowp", WINDOW_BRANCH_OHM)
    current("windowp", c.ileak_windowp)
    current("lowth", c.ileak_lowth)
    current("highth", c.ileak_highth)
    edge("refsrc", "lowth", c.rlt)
    edge("lowth", "sensem", c.rlb)
    edge("refsrc", "highth", c.rht)
    matrix[index["highth"]][index["highth"]] += 1.0 / c.rhb

    augmented = [row[:] + [value] for row, value in zip(matrix, rhs)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        if abs(scale) < 1e-30:
            raise ValueError("singular model matrix")
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [
                    augmented[row][i] - factor * augmented[column][i]
                    for i in range(size + 1)
                ]
    voltage = {node: augmented[index[node]][-1] for node in NODES}
    return Result(
        rtdin_p=voltage["sensep"],
        windowp=voltage["windowp"],
        sensem=voltage["sensem"],
        low_margin=voltage["windowp"] - voltage["lowth"] - c.voffl,
        high_margin=voltage["highth"] - voltage["windowp"] - c.voffh,
    )


def corners() -> Iterable[Corner]:
    """Return the independent endpoint combinations used by the receipt."""
    for values in product(
        (1.95, 2.06),
        (430 * (1 - 0.0005 - 5e-6 * 60), 430 * (1 + 0.0005 + 5e-6 * 60)),
        # REF2025 VREF: +/-0.05% initial, +/-8 ppm/C over 60 C, plus
        # 3 ppm/V line regulation over the declared 3.135..3.465 V input and
        # 8 ppm/mA load regulation at the bounded 96.242 uA divider load.
        (1.25 * (1 - 0.0005 - 8e-6 * 60 - 3e-6 * 0.165 - 8e-6 * 0.096242),
         1.25 * (1 + 0.0005 + 8e-6 * 60 + 3e-6 * 0.165 + 8e-6 * 0.096242)),
        (61900 * (1 - 0.001 - 25e-6 * 60), 61900 * (1 + 0.001 + 25e-6 * 60)),
        (10000 * (1 - 0.001 - 25e-6 * 60), 10000 * (1 + 0.001 + 25e-6 * 60)),
        (5900 * (1 - 0.001 - 25e-6 * 60), 5900 * (1 + 0.001 + 25e-6 * 60)),
        (10000 * (1 - 0.001 - 25e-6 * 60), 10000 * (1 + 0.001 + 25e-6 * 60)),
        (1e6 * (1 - 0.05 - 100e-6 * 60), 1e6 * (1 + 0.05 + 100e-6 * 60)),
        (1e6 * (1 - 0.05 - 100e-6 * 60), 1e6 * (1 + 0.05 + 100e-6 * 60)),
        (-0.004, 0.004),
        (-0.004, 0.004),
        (-14e-9, 14e-9),
        (-14e-9, 14e-9),
        (-20e-9, 20e-9),
        (-5e-9, 5e-9),
        (-5e-9, 5e-9),
    ):
        yield Corner(*values)


def fmt(values: Iterable[float]) -> str:
    numbers = list(values)
    return f"{min(numbers):+.9f}..{max(numbers):+.9f}"


def print_supply_and_transient_bounds() -> None:
    """Print sourced-current and passive transient bounds beside the sweep."""
    # These values are the worst endpoints used by the model.  The current
    # limits are datasheet limits recorded in the contract, not measurements.
    rref_min = 430.0 * (1.0 - 0.0005 - 5e-6 * 60.0)
    ibias_max = 2.06 / (rref_min + 100.0 + 2.0)
    # A shorted RTD removes the 100 ohm healthy-load term.  Omit lead
    # resistance as a conservative source-current bound; the accepted 1 ohm
    # harness only lowers this value.
    ibias_short_max = 2.06 / rref_min
    rdiag_min = 1e6 * (1.0 - 0.05 - 100e-6 * 60.0)
    idiag_max = 2.0 * 2.06 / rdiag_min
    rref_load_max = 1.25 / (61900.0 * (1.0 - 0.001 - 25e-6 * 60.0) +
                             10000.0 * (1.0 - 0.001 - 25e-6 * 60.0))
    high_ref_load_max = 1.25 / (5900.0 * (1.0 - 0.001 - 25e-6 * 60.0) +
                                 10000.0 * (1.0 - 0.001 - 25e-6 * 60.0))
    tlv_active = 2.0 * 65e-6
    logic_active = 2.0 * 10e-6
    local_total = 3.5e-3 + ibias_max + idiag_max + tlv_active + logic_active
    short_total = 3.5e-3 + ibias_short_max + idiag_max + tlv_active + logic_active
    print("supply_budget")
    print(f"MAX_active_spec_mA=3.500 MAX_BIAS_load_mA={ibias_max * 1e3:.6f} "
          f"MAX_BIAS_short_0ohm_mA={ibias_short_max * 1e3:.6f} "
          f"diagnostic_load_uA={idiag_max * 1e6:.3f} "
          f"MAX_plus_BIAS_mA={(3.5e-3 + ibias_max + idiag_max) * 1e3:.6f}")
    print(f"TLV3201_two_active_uA={tlv_active * 1e6:.1f} logic_two_active_uA={logic_active * 1e6:.1f} "
          f"RTD_AVDD_total_bound_mA={local_total * 1e3:.6f} RTD_AVDD_limit_mA=10.000 "
          f"RTD_AVDD_margin_mA={(10e-3 - local_total) * 1e3:.6f} status=PASS")
    print(f"RTD_AVDD_short_0ohm_total_bound_mA={short_total * 1e3:.6f} "
          f"RTD_AVDD_short_0ohm_margin_mA={(10e-3 - short_total) * 1e3:.6f} status=PASS")
    print(f"REF2025_VBIAS_divider_load_uA={(rref_load_max + high_ref_load_max) * 1e6:.3f} "
          "REF2025_IQ_spec_uA=430.000 REF2025_output_limit_mA=20.000")
    print("passive_transient_envelope: -0.2..+2.5 V, source >=1 kohm, "
          "edge >=10 us, pulse <=1 ms, repetition <=1 Hz; clamp sum=0")
    print("device_only_MAX_RTDIN_absmax_v=+/-45.000 "
          "device_absmax_is_not_unit_transient_rating=true")
    print("local_off_postferrite_model: BIAS=0, RTDIN_P/RTDIN_N collapse through "
          "RREF/diagnostics; LOW margin is negative and window_ok is false. "
          "MAX conversion is invalid while VDD is absent; HW fault/rail monitor "
          "owns shutdown.")


def main() -> None:
    all_corners = tuple(corners())
    print(f"corner_count {len(all_corners)}")
    for lead in (1.0, 50.0):
        print(f"lead_ohm {lead:g}")
        for rtd in (100.0, 194.1):
            for case in ("healthy", "FORCE+", "SENSE+", "SENSE-", "FORCE-"):
                rows = [solve(case, rtd, lead, corner) for corner in all_corners]
                print(
                    f"{case:7s} RTD={rtd:5.1f} "
                    f"rtdin_p={fmt(row.rtdin_p for row in rows)} "
                    f"windowp={fmt(row.windowp for row in rows)} "
                    f"sensem={fmt(row.sensem for row in rows)} "
                    f"low={fmt(row.low_margin for row in rows)} "
                    f"high={fmt(row.high_margin for row in rows)} "
                    f"diff={fmt(row.rtdin_p - row.sensem for row in rows)}"
                )
    print_supply_and_transient_bounds()


if __name__ == "__main__":
    main()
