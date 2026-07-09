"""
Deterministic JLCPCB JLC04161H-7628 4-layer stackup definition.

Single source of truth for the physical stackup: layer order, copper weights,
dielectric heights, and dielectric constant. Provides a closed-form IPC-2141
microstrip impedance calculator for the USB differential pair (U5).

Requirement: R1 (stackup definition) from
docs/plans/2026-07-08-004-feat-4-layer-functional-stackup-plan.md
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class LayerConfig:
    """Physical layer configuration for a single copper layer.

    Attributes:
        name: KiCad layer name (e.g. "F.Cu", "In1.Cu", "In2.Cu", "B.Cu").
        kicad_index: KiCad internal layer index (0=F.Cu, 1=In1.Cu, 2=In2.Cu, 31=B.Cu).
        type: Functional layer type ("signal", "plane", "mixed").
        copper_weight_oz: Copper weight in ounces (1.0 outer, 0.5 inner).
        thickness_mm: Copper foil thickness in mm (35 um for 1 oz, 17 um for 0.5 oz).
    """

    name: str
    kicad_index: int
    type: str
    copper_weight_oz: float
    thickness_mm: float


@dataclass(frozen=True)
class Stackup:
    """PCB stackup with dielectric and layer geometry.

    Attributes:
        name: Human-readable stackup name.
        layers: Ordered list of copper layers (top to bottom).
        total_thickness_mm: Total board thickness in mm (1.6 mm nominal for 4-layer).
        prepreg_outer_mm: Prepreg thickness between F.Cu-In1.Cu and In2.Cu-B.Cu.
        core_inner_mm: Core thickness between In1.Cu and In2.Cu.
        dielectric_constant: Relative permittivity (epsilon_r) of the FR-4 dielectric.
    """

    name: str
    layers: list[LayerConfig]
    total_thickness_mm: float
    prepreg_outer_mm: float
    core_inner_mm: float
    dielectric_constant: float


def jlc04161h_7628() -> Stackup:
    """Factory for the JLCPCB JLC04161H-7628 4-layer stackup.

    Physical parameters (from the JLCPCB offering):
        - Total thickness: 1.6 mm
        - F.Cu: 1 oz (35 um), signal layer
        - In1.Cu: 0.5 oz (17 um), plane layer (solid GND reference)
        - In2.Cu: 0.5 oz (17 um), plane layer (power-domain pours)
        - B.Cu: 1 oz (35 um), signal layer
        - Prepreg (F.Cu-In1.Cu, In2.Cu-B.Cu): 0.2 mm, 7628 glass, epsilon_r ~4.5
        - Core (In1.Cu-In2.Cu): 1.1 mm, FR-4, epsilon_r ~4.5

    KiCad indices: 0=F.Cu, 1=In1.Cu, 2=In2.Cu, 31=B.Cu.
    """
    return Stackup(
        name="JLCPCB JLC04161H-7628",
        layers=[
            LayerConfig("F.Cu", 0, "signal", 1.0, 0.035),
            LayerConfig("In1.Cu", 1, "plane", 0.5, 0.017),
            LayerConfig("In2.Cu", 2, "plane", 0.5, 0.017),
            LayerConfig("B.Cu", 31, "signal", 1.0, 0.035),
        ],
        total_thickness_mm=1.6,
        prepreg_outer_mm=0.2,
        core_inner_mm=1.1,
        dielectric_constant=4.5,
    )


def characteristic_impedance_microstrip(width_mm: float, stackup: Stackup) -> float:
    """Compute characteristic impedance Z0 for a microstrip on F.Cu over In1.Cu.

    Uses the IPC-2141 closed-form formula for a microstrip transmission line:

        Z0 = (87 / sqrt(epsilon_r + 1.41)) * ln(5.98 * H / (0.8 * W + T))

    where H is the prepreg height (F.Cu to In1.Cu), W is the trace width,
    T is the copper thickness, and epsilon_r is the dielectric constant.

    This drives the 90-ohm USB differential pair impedance verification (U5):
    a single-ended Z0 of ~50-55 ohm on F.Cu with 0.2mm prepreg gives a
    differential impedance near 90 ohm with appropriate pair spacing.

    Args:
        width_mm: Trace width in mm.
        stackup: The PCB stackup (prepreg_outer_mm, dielectric_constant, and
                 F.Cu copper thickness are used).

    Returns:
        Characteristic impedance Z0 in ohms.
    """
    er = stackup.dielectric_constant
    h = stackup.prepreg_outer_mm
    t = stackup.layers[0].thickness_mm  # F.Cu copper thickness (35 um)
    w = width_mm

    return (87.0 / math.sqrt(er + 1.41)) * math.log(5.98 * h / (0.8 * w + t))
