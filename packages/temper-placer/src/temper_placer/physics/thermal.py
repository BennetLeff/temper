"""
Thermal junction temperature estimation for PCB components.

The scalar arithmetic runs in the ``temper-thermal`` Rust kernel
(``estimate_junction_temp_py``, Wave 4 Phase A #3); this module keeps
the public API, the default thermal-resistance parameters, and the
per-footprint thermal property lookup.

## Thermal-analysis correction (2026-08-15)

The safety audit found three defects in the pre-correction analysis:

1. **Flat thermal resistance.**  ``Rjc=0.6 / Rch=0.25 / Rha=1.0`` K/W was
   applied to *every* component.  Real components differ by an order of
   magnitude (TO-247 IGBT ``Rjc=0.31`` per the IKW40N120H3 datasheet; a
   SOT-23 buck has an ~80 K/W junction-to-ambient path through the PCB).
   The per-footprint table now lives in Rust
   (``temper_thermal.lookup_thermal_properties_py``, keyed by footprint,
   NOT refdes — handoff §6) and is wired through ``measure_thermal``.
   The flat values below remain only as the *fallback* for footprints
   with no table entry (labelled UNSOURCED).
2. **Margin temperature.**  The analysis used 150 °C as "typical
   shutdown"; 150 °C is the IKW40N120H3 *storage* temperature, not a
   junction limit (Tvj(max) = 175 °C per datasheet — see the thermal
   threshold decision, ``docs/evidence/2026-08-15-thermal-threshold-decision.md``).
   The decided firmware over-temperature trip is **80 °C**
   (decision doc verdict 2: ``OVER_TEMP_THRESHOLD`` moves 100 → 80 °C so
   the firmware layer is live ahead of the 85 °C hardware latch).
   Margins are now computed against that decided firmware trip (80 °C),
   the heatsink touch/trip temperature (85 °C,
   ``FUNCTIONAL_TEST_CRITERIA.md`` §2.3), and the component limit
   (120 °C, coil NTC trip per the same table) — see ``measure_thermal``
   in ``metrics/physics.py``.
3. **Ambient temperature.**  The default was 40 °C; the repo's own
   worst-case design ambient is 60 °C
   (``docs/guides/THERMAL_DESIGN_GUIDE.md`` §2.2, "Worst case design |
   60°C | Design limit").  ``ENVIRONMENTAL_SPEC.md`` §1.1 allows 40 °C at
   rated power with linear derating to 0 % at 60 °C, so 60 °C is the
   correct worst-case analysis ambient.

See ``docs/evidence/2026-08-15-thermal-analysis-corrections.md``.
"""

from __future__ import annotations

import temper_thermal as _tt

# Firmware over-temperature protection trip (heatsink NTC), °C.
# Decided 2026-08-15 (docs/evidence/2026-08-15-thermal-threshold-decision.md
# verdict 2): OVER_TEMP_THRESHOLD moves 100 -> 80 °C so the firmware layer
# is live (graceful shutdown / diagnostics) ahead of the 85 °C hardware
# THM-01 latch. The firmware edit itself is a separate pending task; the
# analysis margin targets the DECIDED value, not the pre-decision 100.0f
# still in firmware/components/safety/safety.c.
FIRMWARE_TRIP_C: float = 80.0
# Heatsink NTC trip / touch temperature, °C (FUNCTIONAL_TEST_CRITERIA.md §2.3).
TOUCH_TEMP_C: float = 85.0
# Component temperature limit, °C (FUNCTIONAL_TEST_CRITERIA.md §2.3, coil NTC).
COMPONENT_MAX_C: float = 120.0

# Legacy flat fallback stackup (K/W) for footprints with no entry in the
# Rust per-footprint table.  UNSOURCED: these were the pre-correction
# analysis defaults, kept only so an unknown footprint degrades to the
# old behavior rather than being silently assigned a value.
_DEFAULT_RJC: float = 0.6
_DEFAULT_RCH: float = 0.25
_DEFAULT_RHA: float = 1.0


def lookup_thermal_properties(footprint: str) -> tuple[float, float, float, str] | None:
    """Per-footprint ``(Rjc, Rch, Rha, source)`` from the Rust table.

    Keyed by footprint (not refdes — designators are unstable across
    branches).  Returns ``None`` for footprints with no table entry; the
    caller then falls back to the legacy flat stackup (UNSOURCED).
    """
    return _tt.lookup_thermal_properties_py(footprint)


def estimate_junction_temp(
    power_W: float,
    edge_distance_mm: float,
    copper_area_mm2: float = 0.0,
    ambient_C: float = 60.0,
    Rjc: float = _DEFAULT_RJC,
    Rch: float = _DEFAULT_RCH,
    Rha_base: float = _DEFAULT_RHA,
) -> float:
    """
    Estimate component junction temperature from placement and environment.

    Model: Tj = Tamb + P * (Rjc + Rch + Rha)
    Rha depends on distance to board edge (heatsink mount) and copper area.

    Args:
        power_W: Power dissipation in Watts.
        edge_distance_mm: Distance to board edge in mm.
        copper_area_mm2: Area of connected copper pour in mm².  The
            copper-spreading benefit (0.1 K/W per 1000 mm², capped at
            0.5 K/W) reduces the effective Rha — pass real copper areas
            to exercise it.
        ambient_C: Ambient temperature in °C.  Default 60 °C: the repo's
            worst-case design ambient (THERMAL_DESIGN_GUIDE.md §2.2), not
            the 40 °C the pre-correction analysis used.
        Rjc: Junction-to-case thermal resistance (K/W).  The flat 0.6
            fallback is UNSOURCED — use
            ``lookup_thermal_properties(footprint)`` for real per-part
            values (IKW40N120H3 TO-247: 0.31 per datasheet).
        Rch: Case-to-heatsink thermal resistance (K/W).  Flat 0.25
            fallback (grease); 0.20 is the design-guide value.
        Rha_base: Base heatsink-to-ambient resistance (K/W).  Flat 1.0
            fallback (UNSOURCED); 0.45 K/W with the forced-air HS1
            heatsink per THERMAL_DESIGN_GUIDE.md §3.1.

    The arithmetic runs in the ``temper-thermal`` Rust kernel
    (``estimate_junction_temp_py``, Wave 4 Phase A #3), which mirrors
    this function's exact f64 operation order bit-for-bit (pinned by the
    differential suite ``tests/physics/test_thermal_rust_differential.py``).

    Returns:
        Estimated junction temperature in °C.
    """
    return _tt.estimate_junction_temp_py(
        power_W,
        edge_distance_mm,
        copper_area_mm2,
        ambient_C,
        Rjc,
        Rch,
        Rha_base,
    )
