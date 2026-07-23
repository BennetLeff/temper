"""Bounded, datasheet-envelope model for the UCC21550 DT pin.

This is deliberately an *in-box* model: it evaluates the equation and the
published 10/20/50-kOhm min/typ/max characterization points, while allowing
the resistor tolerance, TCR, temperature, and an explicit device-envelope
scale to be varied.  It does not model the IGBT gate, driver output
resistance, parasitic inductance, or probe loading.  Those are the reason a
scope measurement is still required for the assembled board.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product

DT_SLOPE_NS_PER_KOHM = 8.6
DT_INTERCEPT_NS = 13.0


@dataclass(frozen=True)
class DTCorners:
    """Inputs for a reproducible corner sweep.

    ``device_scale`` is intentionally explicit.  The UCC21550 data sheet
    gives approximately +/-10% around the equation at the 20-kOhm and
    50-kOhm characterization points; callers can tighten or widen that
    envelope when a different qualification grade or measured data is used.
    ``tcr_ppm`` is a board-level resistor assumption, not a TI guarantee.
    """

    resistor_kohm: float = 34.0
    resistor_tolerance: float = 0.01
    tcr_ppm_per_c: float = 100.0
    reference_temp_c: float = 25.0
    temperatures_c: tuple[float, ...] = (-40.0, 25.0, 150.0)
    device_scale: tuple[float, float] = (0.90, 1.10)


_DEFAULT_CORNERS = DTCorners()


def resistor_at_temperature(
    nominal_kohm: float,
    tolerance: float,
    tcr_ppm_per_c: float,
    temperature_c: float,
    reference_temp_c: float = 25.0,
) -> float:
    """Return the resistance corner in kOhm at ``temperature_c``."""

    return nominal_kohm * (1.0 + tolerance) * (
        1.0 + tcr_ppm_per_c * 1e-6 * (temperature_c - reference_temp_c)
    )


def programmed_dead_time_ns(resistor_kohm: float, device_scale: float = 1.0) -> float:
    """Evaluate TI's equation with an explicit characterization scale."""

    return (DT_SLOPE_NS_PER_KOHM * resistor_kohm + DT_INTERCEPT_NS) * device_scale


def effective_dead_time_ns(programmed_ns: float, input_dead_time_ns: float) -> float:
    """UCC21550 uses the longer of programmed and input dead time."""

    return max(programmed_ns, input_dead_time_ns)


def corner_results(corners: DTCorners | None = None) -> tuple[float, ...]:
    """Evaluate every resistor/temp/device-scale corner deterministically."""

    corners = _DEFAULT_CORNERS if corners is None else corners
    values = []
    for tolerance, temperature_c, device_scale in product(
        (-corners.resistor_tolerance, corners.resistor_tolerance),
        corners.temperatures_c,
        corners.device_scale,
    ):
        resistance = resistor_at_temperature(
            corners.resistor_kohm,
            tolerance,
            corners.tcr_ppm_per_c,
            temperature_c,
            corners.reference_temp_c,
        )
        values.append(programmed_dead_time_ns(resistance, device_scale))
    return tuple(values)


def corner_summary(corners: DTCorners | None = None) -> tuple[float, float]:
    """Return (minimum, maximum) programmed DT over the corner sweep."""

    values = corner_results(corners)
    return min(values), max(values)


def meets_programmed_dead_time(
    required_ns: float = 300.0, corners: DTCorners | None = None
) -> bool:
    """Whether the *hardware programmed* DT meets a hard corner requirement."""

    return corner_summary(corners)[0] >= required_ns


def recommended_resistor_for_requirement(
    required_ns: float = 300.0,
    *,
    resistor_tolerance: float = 0.01,
    tcr_ppm_per_c: float = 100.0,
    temperatures_c: tuple[float, ...] = _DEFAULT_CORNERS.temperatures_c,
    reference_temp_c: float = 25.0,
    device_scale_min: float = 0.90,
) -> float:
    """Solve for the minimum nominal resistor across every stated corner.

    The resistor must meet the timing requirement at the *minimum* resistance
    corner.  For a positive TCR that is the cold corner, not the hot corner;
    selecting one ``worst_temperature_c`` by intuition previously produced an
    optimistic recommendation.  Evaluate the complete temperature tuple so
    the result remains sound when the qualification envelope changes.
    """

    if not temperatures_c:
        raise ValueError("temperatures_c must contain at least one corner")
    if not 0.0 <= resistor_tolerance < 1.0:
        raise ValueError("resistor_tolerance must be in [0, 1)")
    if device_scale_min <= 0.0:
        raise ValueError("device_scale_min must be positive")

    minimum_temp_factor = min(
        1.0 + tcr_ppm_per_c * 1e-6 * (temperature_c - reference_temp_c)
        for temperature_c in temperatures_c
    )
    resistance_factor = (1.0 - resistor_tolerance) * minimum_temp_factor
    if resistance_factor <= 0.0:
        raise ValueError("TCR/temperature corners produce non-positive resistance")

    return ((required_ns / device_scale_min) - DT_INTERCEPT_NS) / (
        DT_SLOPE_NS_PER_KOHM * resistance_factor
    )
