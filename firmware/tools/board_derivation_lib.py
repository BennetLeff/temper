#!/usr/bin/env python3
"""Shared formula library for board-derived firmware constants.

Single source of truth for the DERIVATION ARITHMETIC behind every
firmware constant that has a board derivation (plan 2026-08-02-027,
R18 -- "Firmware-assumption contract oracle"). Two consumers call these
functions, so the two cannot drift:

1. ``scripts/check_pll_range_consistency.py`` -- the existing
   declared-vs-declared PLL gate (its check 5 derives the ZVS floor).
2. ``scripts/check_firmware_board_contract.py`` -- the board-vs-firmware
   oracle that re-derives each registered constant from the actual
   board's placed components.

The registry ``board_derivations.yaml`` names which formula each constant
uses; the functions here implement them once. Tolerances are applied
INSIDE the derivation (KTD4 of the plan: "tolerances live inside the
derivation, never as an output fudge").

The two seeded derivations
--------------------------
1. ``pll_min_freq_floor`` -- the PLL ZVS floor. Documented in
   ``firmware/components/control/pll_control.h`` and
   ``elec/src/main.ato``, and previously only implemented inside
   ``scripts/check_pll_range_consistency.py``:

       L_loaded(worst) = l_tank_assumed * (1 - l_tank_tolerance) * l_pan_loaded_ratio
       C(worst)        = c_tank_total  * (1 - c_tank_tolerance)
       f_res,loaded    = 1 / (2*pi*sqrt(L_loaded(worst) * C(worst)))
       required floor  = ZVS_MARGIN_MIN * f_res,loaded

   The floor keys off MINIMUM L AND MINIMUM C because f_res ~ 1/sqrt(LC):
   a low-tolerance part on either side resonates higher and needs the
   highest floor.

2. ``max31865_low_threshold_word`` / ``max31865_high_threshold_word`` --
   the MAX31865 RTD fault-threshold register words in
   ``firmware/config.yaml``. The MAX31865 ADC is a 15-bit ratiometric
   converter: code = RTD / RREF * 2^15 (clamped at 32767). Fault
   threshold registers store the code shifted left one bit (a 16-bit
   left-aligned word). The two boundaries round OPPOSITELY, matching the
   fault-trip semantics:

   - LOW threshold trips when RTD is AT or BELOW the boundary, so the
     register holds the smallest code STRICTLY ABOVE the boundary --
     ``ceil``. (10 ohm -> ceil(762.05) = 763 -> word 1526.)
   - HIGH threshold trips when RTD is AT or ABOVE the boundary, so the
     register holds the largest code AT OR BELOW the boundary --
     ``floor``. (300 ohm -> floor(22861.40) = 22861 -> word 45722.)

   This asymmetry is why there are two functions, not one -- a single
   rounding choice would silently disagree with one of the two committed
   words.

Input validation
----------------
Each function validates its inputs and raises :exc:`ValueError` on a
nonsensical value (non-positive inductance/capacitance/resistance, a
coupling ratio outside (0, 1], a tolerance outside [0, 1)). Callers that
need fail-closed-with-named-source behaviour (the PLL gate, the oracle)
do their own sanity checking first so they can attribute the failure;
the library-level check is defense in depth, not the primary error path.

Host pytest: ``firmware/tools/test_board_derivation_lib.py``.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

# Minimum f_sw / f_res,loaded required for zero-voltage switching. Lives
# in THIS library (shared by both consumers), not in any file under test
# -- a margin declared in the file being checked can be relaxed from the
# side being checked. Source: docs/hardware/TANK_COIL_SPECIFICATION.md.
ZVS_MARGIN_MIN = 1.05

# MAX31865 15-bit ratiometric ADC full-scale code (data sheet: 15-bit,
# no missing codes, 0.003% resolution = 1/32768).
MAX31865_ADC_MAX_CODE = 32767


# ---------------------------------------------------------------------------
# PLL ZVS floor
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PllFloorDerivation:
    """Every intermediate quantity of the PLL floor derivation, so a
    derivation change is attributable (plan U1 test scenario 3)."""

    l_nominal_h: float
    l_worst_case_h: float
    l_loaded_worst_case_h: float
    c_nominal_farads: float
    c_worst_case_farads: float
    loaded_ratio: float
    l_tolerance: float
    c_tolerance: float
    zvs_margin: float
    f_res_nominal_hz: float
    f_res_worst_case_hz: float
    required_floor_hz: float

    @property
    def c_farads(self) -> float:
        """Nominal capacitance -- used by the PLL gate's check 6 (the
        c_tank_total mirror), which compares NOMINAL values."""
        return self.c_nominal_farads


def pll_min_freq_floor(
    l_nominal_h: float,
    c_nominal_farads: float,
    loaded_ratio: float,
    l_tolerance: float,
    c_tolerance: float,
    zvs_margin: float = ZVS_MARGIN_MIN,
) -> PllFloorDerivation:
    """Derive the required PLL floor from tank quantities.

    Worst-cases BOTH tank components: f_res ~ 1/sqrt(LC), so a
    low-tolerance part on EITHER side resonates highest and needs the
    highest floor. Deriving at nominal for either would under-protect
    exactly the unit most at risk (see docs/evidence/2026-07-29-pll-
    floor-cap-tolerance.md).
    """
    for value, what in (
        (l_nominal_h, "l_nominal_h"),
        (c_nominal_farads, "c_nominal_farads"),
    ):
        if not math.isfinite(value) or value <= 0.0:
            raise ValueError(f"{what} must be a positive finite number, got {value!r}")
    if not math.isfinite(loaded_ratio) or not (0.0 < loaded_ratio <= 1.0):
        raise ValueError(
            f"loaded_ratio must be in (0, 1], got {loaded_ratio!r} "
            "-- a loaded/unloaded inductance ratio"
        )
    for value, what in ((l_tolerance, "l_tolerance"), (c_tolerance, "c_tolerance")):
        if not math.isfinite(value) or not (0.0 <= value < 1.0):
            raise ValueError(
                f"{what} must be in [0, 1), got {value!r} -- a fractional part tolerance"
            )
    if not math.isfinite(zvs_margin) or zvs_margin <= 1.0:
        raise ValueError(f"zvs_margin must be > 1.0, got {zvs_margin!r}")

    l_worst = l_nominal_h * (1.0 - l_tolerance)
    l_loaded_worst = l_worst * loaded_ratio
    c_worst = c_nominal_farads * (1.0 - c_tolerance)

    def _f_res(l_henries: float, c_farads: float) -> float:
        return 1.0 / (2.0 * math.pi * math.sqrt(l_henries * c_farads))

    f_res_nominal = _f_res(l_nominal_h * loaded_ratio, c_nominal_farads)
    f_res_worst = _f_res(l_loaded_worst, c_worst)

    return PllFloorDerivation(
        l_nominal_h=l_nominal_h,
        l_worst_case_h=l_worst,
        l_loaded_worst_case_h=l_loaded_worst,
        c_nominal_farads=c_nominal_farads,
        c_worst_case_farads=c_worst,
        loaded_ratio=loaded_ratio,
        l_tolerance=l_tolerance,
        c_tolerance=c_tolerance,
        zvs_margin=zvs_margin,
        f_res_nominal_hz=f_res_nominal,
        f_res_worst_case_hz=f_res_worst,
        required_floor_hz=zvs_margin * f_res_worst,
    )


def round_up_to_khz(freq_hz: float) -> int:
    """Smallest round kHz at or above *freq_hz* -- the convention
    firmware commits in ``PLL_MIN_FREQ_HZ`` (e.g. 43823.8 Hz -> 44000)."""
    return int(math.ceil(freq_hz / 1000.0)) * 1000


def pll_min_freq_hz(floor: PllFloorDerivation) -> int:
    """The documented firmware value for a given floor: the smallest
    round kHz above the required floor."""
    return round_up_to_khz(floor.required_floor_hz)


# ---------------------------------------------------------------------------
# MAX31865 fault-threshold words
# ---------------------------------------------------------------------------


def _max31865_code(rtd_ohm: float, r_ref_ohm: float, rounding: str) -> int:
    """15-bit ratiometric ADC code for *rtd_ohm* against *r_ref_ohm*.

    code = RTD / RREF * 2^15, clamped at MAX31865_ADC_MAX_CODE. *rounding*
    is ``"ceil"`` (low threshold: smallest code strictly above the
    boundary, so AT-or-below trips) or ``"floor"`` (high threshold:
    largest code at-or-below the boundary, so AT-or-above trips).
    """
    if not math.isfinite(rtd_ohm) or rtd_ohm < 0.0:
        raise ValueError(f"rtd_ohm must be a finite non-negative number, got {rtd_ohm!r}")
    if not math.isfinite(r_ref_ohm) or r_ref_ohm <= 0.0:
        raise ValueError(f"r_ref_ohm must be a positive finite number, got {r_ref_ohm!r}")

    exact = rtd_ohm / r_ref_ohm * 32768.0
    if rounding == "ceil":
        code = math.ceil(exact)
    elif rounding == "floor":
        code = math.floor(exact)
    else:  # pragma: no cover - internal dispatch only
        raise AssertionError(f"unknown rounding mode {rounding!r}")
    return min(MAX31865_ADC_MAX_CODE, max(0, code))


def max31865_low_threshold_word(rtd_ohm: float, r_ref_ohm: float) -> int:
    """Fault-threshold register word that trips when RTD is AT or BELOW
    *rtd_ohm* (e.g. the 10 ohm short boundary): the smallest 15-bit code
    strictly above the boundary, shifted left one bit."""
    return _max31865_code(rtd_ohm, r_ref_ohm, "ceil") << 1


def max31865_high_threshold_word(rtd_ohm: float, r_ref_ohm: float) -> int:
    """Fault-threshold register word that trips when RTD is AT or ABOVE
    *rtd_ohm* (e.g. the 300 ohm open boundary): the largest 15-bit code
    at-or-below the boundary, shifted left one bit."""
    return _max31865_code(rtd_ohm, r_ref_ohm, "floor") << 1


# ---------------------------------------------------------------------------
# Value parsing ("100nF", "430ohm", "88uH", ...) -- used to read component
# values from the board Value property and from registry decode tables.
# ---------------------------------------------------------------------------

_SI_PREFIX = {
    "T": 1e12,
    "G": 1e9,
    "M": 1e6,
    "k": 1e3,
    "": 1.0,
    "m": 1e-3,
    "u": 1e-6,
    "n": 1e-9,
    "p": 1e-12,
}

# (regex unit group, scale) -- matched as <number><prefix><unit>.
_VALUE_PATTERNS: tuple[tuple[str, float], ...] = (
    # Capacitance (farads) -- longest units first so "uF" beats "F".
    ("(?:mF|uF|nF|pF)", 1.0),
    ("F", 1.0),
    # Inductance (henries).
    ("(?:mH|uH|nH)", 1.0),
    ("H", 1.0),
    # Resistance -- "ohm" and "Ω", with optional "k"/"M" prefix handled
    # by the generic prefix table below.
    ("(?:ohm|Ohm|Ω)", 1.0),
    # Frequency (Hz).
    ("(?:kHz|MHz|GHz)", 1.0),
    ("Hz", 1.0),
)

_UNIT_SCALES: dict[str, float] = {
    "F": 1.0,
    "H": 1.0,
    "ohm": 1.0,
    "Ohm": 1.0,
    "Ω": 1.0,
    "Hz": 1.0,
    # SI prefix is applied on top of these base scales.
}

_VALUE_RE = re.compile(
    r"^\s*(\d+(?:\.\d+)?)\s*([TGMkmunp]?)(mF|uF|nF|pF|mH|uH|nH|ohm|Ohm|Ω|kHz|MHz|GHz|F|H|Hz)\s*$"
)


def parse_si_value(text: str) -> float | None:
    """Parse a value-with-SI-unit string into base SI units.

    Supports capacitance (F), inductance (H), resistance (ohm/Ω) and
    frequency (Hz) with the standard SI prefixes
    (p/n/u/m/k/M/G/T). Returns ``None`` when the string is not a
    parseable value (e.g. the board Value placeholder ``"?"``) -- the
    caller decides what "not parseable" means for its check; it is never
    a silent zero.
    """
    if not isinstance(text, str):
        return None
    m = _VALUE_RE.match(text.strip())
    if not m:
        return None
    magnitude, prefix, unit = m.group(1), m.group(2), m.group(3)
    if prefix not in _SI_PREFIX:
        return None
    base = _UNIT_SCALES.get(unit)
    if base is None:
        return None
    return float(magnitude) * _SI_PREFIX[prefix] * base
