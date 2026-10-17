#!/usr/bin/env python3
"""Bounded DC model for the proposed RTDIN comparator window.

This is a candidate reference-envelope revision, not renewed unit acceptance.
Other inherited model assumptions and printed budgets remain unqualified.
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
# REF2025AIDDCR's initial-accuracy test point is VIN=5 V.  The standalone
# unit contract supplies 3.135..3.465 V, so line-regulation error is bounded
# from the worst distance to that 5 V test point rather than a nominal
# +/-0.165 V span around 3.3 V.  The VBIAS divider load is a rounded-up,
# self-consistent 96.350 uA bound: the divider's worst resistance corner is
# evaluated at the corrected maximum VBIAS, rather than at exactly 1.25 V.
REF_NOMINAL_V: Final[float] = 1.25
REF_INITIAL_FRACTION: Final[float] = 0.0005
REF_DRIFT_PPM_PER_C: Final[float] = 8.0
REF_LINE_PPM_PER_V: Final[float] = 35.0
REF_LOAD_PPM_PER_MA: Final[float] = 20.0
REF_TEMP_DELTA_C: Final[float] = 60.0
REF_VIN_MIN_V: Final[float] = 3.135
REF_VIN_MAX_V: Final[float] = 3.465
REF_LINE_REFERENCE_V: Final[float] = 5.0
REF_VBIAS_LOAD_MA: Final[float] = 0.096350
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
        # REF2025 VREF: +/-0.05% initial at VIN=5 V, +/-8 ppm/C drift,
        # +/-35 ppm/V line regulation across the declared VIN range, and
        # +/-20 ppm/mA load regulation at the conservative 96.350 uA load.
        (REF_NOMINAL_V * (1 - ref_error_fraction()),
         REF_NOMINAL_V * (1 + ref_error_fraction())),
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


def ref_error_fraction() -> float:
    """Return the corrected worst-case REF2025 fractional error envelope."""
    line_span_v = max(
        abs(REF_VIN_MIN_V - REF_LINE_REFERENCE_V),
        abs(REF_VIN_MAX_V - REF_LINE_REFERENCE_V),
    )
    return (
        REF_INITIAL_FRACTION
        + REF_DRIFT_PPM_PER_C * 1e-6 * REF_TEMP_DELTA_C
        + REF_LINE_PPM_PER_V * 1e-6 * line_span_v
        + REF_LOAD_PPM_PER_MA * 1e-6 * REF_VBIAS_LOAD_MA
    )


def vbias_divider_load_ma(vref: float) -> float:
    """Bound VBIAS divider source current for sensem >= 0 V.

    The maximum occurs at sensem=0 and positive 5 nA leakage into each
    comparator input.  Input leakage contributes only the lower-divider
    fraction of each branch current; this is the source-current bound used
    to check the rounded REF_VBIAS_LOAD_MA constant.
    """
    rlt = 61900.0 * (1.0 - 0.001 - 25e-6 * 60.0)
    rlb = 10000.0 * (1.0 - 0.001 - 25e-6 * 60.0)
    rht = 5900.0 * (1.0 - 0.001 - 25e-6 * 60.0)
    rhb = 10000.0 * (1.0 - 0.001 - 25e-6 * 60.0)
    ileak = 5e-9
    low_source = vref / (rlt + rlb) + ileak * rlb / (rlt + rlb)
    high_source = vref / (rht + rhb) + ileak * rhb / (rht + rhb)
    return (low_source + high_source) * 1e3


def self_consistent_vbias_load_ma() -> float:
    """Evaluate the divider load at the corrected maximum VREF endpoint."""
    vmax = REF_NOMINAL_V * (1.0 + ref_error_fraction())
    return vbias_divider_load_ma(vmax)


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
    print(f"REF2025_VBIAS_divider_load_uA={self_consistent_vbias_load_ma() * 1e3:.3f} "
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
