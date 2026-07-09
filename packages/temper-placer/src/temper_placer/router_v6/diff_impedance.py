"""
Edge-coupled microstrip differential impedance calculator.

Implements IPC-2141 formulas for edge-coupled surface microstrip,
used to verify that USB differential pair geometry (w=0.3mm, s=0.2mm)
achieves 90R +-10% on the JLC04161H-7628 stackup (0.2mm prepreg, er ~4.2).

Part of W2/U5 — 4-layer functional stackup.
"""

from __future__ import annotations

import math


def _microstrip_z0_single(w_mm: float, h_mm: float, er: float) -> float:
    """Single-ended microstrip characteristic impedance (IPC-2141).

    Uses the IPC-2141 / Wheeler formulas with consistent effective-
    dielectric computation at both sides of W/H=1 so the result is
    continuous and monotonic.

    Args:
        w_mm: Trace width in mm
        h_mm: Dielectric height to reference plane in mm
        er: Relative dielectric constant
    """
    ratio = w_mm / h_mm

    # Effective dielectric constant (continuous across W/H=1).
    if ratio <= 1.0:
        ee = (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * (
            1.0 / math.sqrt(1.0 + 12.0 / ratio)
            + 0.04 * (1.0 - ratio) ** 2
        )
        return (60.0 / math.sqrt(ee)) * math.log(
            8.0 / ratio + ratio / 4.0
        )
    else:
        ee = (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * (
            1.0 / math.sqrt(1.0 + 12.0 / ratio)
        )
        return (120.0 * math.pi) / (
            math.sqrt(ee)
            * (ratio + 1.393 + 0.667 * math.log(ratio + 1.444))
        )


def edge_coupled_microstrip_z0(
    w_mm: float,
    s_mm: float,
    h_mm: float,
    er: float,
) -> float:
    """Differential impedance for edge-coupled surface microstrip.

    Uses the IPC-2141 formula: Z0_single computed from w/h/er, then
    differential correction via coupling factor.

        Zdiff = 2 * Z0 * (1 - 0.48 * exp(-0.96 * S / H))

    Args:
        w_mm: Trace width in mm.
        s_mm: Edge-to-edge spacing between the pair in mm.
        h_mm: Dielectric height to the reference plane in mm.
        er: Relative dielectric constant (er).

    Returns:
        Differential impedance in ohms.

    Example:
        # JLC04161H-7628: 0.2mm prepreg, er=4.2
        >>> z = edge_coupled_microstrip_z0(0.3, 0.2, 0.2, 4.2)
        >>> 81.0 <= z <= 99.0  # within +-10% of 90R target
        True
    """
    z0 = _microstrip_z0_single(w_mm, h_mm, er)
    coupling = 0.48 * math.exp(-0.96 * s_mm / h_mm)
    return 2.0 * z0 * (1.0 - coupling)


def edge_coupled_microstrip_geometry(
    z0_target: float,
    h_mm: float,
    er: float,
) -> tuple[float, float]:
    """Find (w_mm, s_mm) for a target differential impedance.

    Searches w in [0.5*h, 3.0*h] and s in [0.3*h, 3.0*h] in 0.1*h
    increments, returning the geometry whose predicted impedance is
    closest to ``z0_target``.

    For the JLC04161H-7628 stackup (h=0.2mm, er=4.2, Zdiff=90R):
        result is approximately w=0.3mm, s=0.2mm.

    Args:
        z0_target: Target differential impedance in ohms.
        h_mm: Dielectric height to reference plane in mm.
        er: Relative dielectric constant.

    Returns:
        (w_mm, s_mm) geometry tuple.
    """
    best_w = h_mm * 1.5
    best_s = h_mm * 1.0
    best_err = abs(edge_coupled_microstrip_z0(best_w, best_s, h_mm, er) - z0_target)

    for wi in range(5, 31):
        for si in range(3, 31):
            w = h_mm * wi / 10.0
            s = h_mm * si / 10.0
            z = edge_coupled_microstrip_z0(w, s, h_mm, er)
            err = abs(z - z0_target)
            if err < best_err:
                best_w, best_s = w, s
                best_err = err

    return (best_w, best_s)


# ---- Pre-computed constants for JLC04161H-7628 (USB 2.0) ----

_JLC_PREPREG_MM = 0.2      # F.Cu -> In1.Cu prepreg height (7628)
_JLC_ER = 4.2              # FR-4 7628 prepreg dielectric constant
_USB_DIFF_Z0_TARGET = 90.0  # USB 2.0 differential impedance target

# Pre-computed geometry that achieves 90R on this stackup.
USB_W_MM, USB_S_MM = edge_coupled_microstrip_geometry(
    _USB_DIFF_Z0_TARGET, _JLC_PREPREG_MM, _JLC_ER
)
USB_PREDICTED_ZDIFF = edge_coupled_microstrip_z0(
    USB_W_MM, USB_S_MM, _JLC_PREPREG_MM, _JLC_ER
)
