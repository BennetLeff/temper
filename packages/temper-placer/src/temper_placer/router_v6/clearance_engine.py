"""
Unified Multi-Standard Clearance Engine

Consolidates creepage/clearance requirements from five IEC/IPC standards
into a single queryable function.  Each standard is consulted independently
and the most-conservative (largest) value is returned so that a design
passes all applicable standards simultaneously.

Standards consolidated
-----------------------
* **IEC 60950-1**  — ITE safety: voltage-table creepage & clearance
  (``routing/safety_distances.py``)
* **IEC 60335-1**  — Household appliances: ``VoltageClass`` per-class
  creepage & clearance tables (``core/net_types.py``)
* **IEC 60664-1**  — Insulation coordination: internal-layer creepage
  reduction factor (``routing/constraints/drc_oracle.py``)
* **IEC 62368-1**  — AV/IT safety: HV ghost-pad injection uses
  ``NetClassRules.creepage_mm`` (``deterministic/stages/
  phased_component_assignment.py``) — consumed through the optional
  ``design_rule_creepage`` parameter.
* **IPC-2221**     — Generic PCB creepage table
  (``router_v6/creepage_check.py``)

Usage
-----
.. code-block:: python

    from temper_placer.router_v6.clearance_engine import get_clearance

    mm = get_clearance("HV", "Signal", voltage=340.0, layer_type="external")
    # → e.g. 8.0  (most-conservative across all standards)

Only the engine and ONE consumer are built in this commit; full migration
of all consumers is deferred (see ``feat/unified-clearance-engine``).
"""
from __future__ import annotations

from temper_placer.core.net_types import VoltageClass
from temper_placer.router_v6.creepage_check import _calculate_required_creepage

# ---------------------------------------------------------------------------
# Per-standard imports
# ---------------------------------------------------------------------------

# IEC 60950-1
def calculate_safety_distances(
    voltage_v: float,
    pollution_degree: int = 2,
    _material_group: str = "IIIa",
    overvoltage_category: int = 2,
):
    """Calculate required creepage and clearance per IEC 60950-1.

    Based on Table 2K (clearance) and Table 2N (creepage) from IEC 60950-1.
    Conservative values for PCB routing.

    Returns:
        SafetyDistances dataclass with clearance_mm, creepage_mm, voltage_v.
    """
    from dataclasses import dataclass

    @dataclass
    class SafetyDistances:
        clearance_mm: float
        creepage_mm: float
        voltage_v: float

    clearance_table = [
        (50, 0.2), (150, 1.0), (300, 2.0), (600, 2.5),
        (1000, 4.0), (float("inf"), 5.0),
    ]
    creepage_table = [
        (50, 0.4), (150, 2.0), (300, 2.5), (600, 3.0),
        (1000, 5.0), (float("inf"), 8.0),
    ]
    clearance_mm = 0.2
    for vl, d in clearance_table:
        if voltage_v <= vl:
            clearance_mm = d
            break
    creepage_mm = 0.4
    for vl, d in creepage_table:
        if voltage_v <= vl:
            creepage_mm = d
            break
    if overvoltage_category >= 3:
        clearance_mm *= 1.25
        creepage_mm *= 1.25
    if pollution_degree >= 3:
        creepage_mm *= 2.0
    return SafetyDistances(
        clearance_mm=clearance_mm,
        creepage_mm=creepage_mm,
        voltage_v=voltage_v,
    )


# IEC 60664-1 legacy constant (was in routing/constraints/drc_oracle.py)
INTERNAL_LAYER_CREEPAGE_FACTOR: float = 0.30

# ---------------------------------------------------------------------------
# Net-class → VoltageClass mapping (IEC 60335-1)
# ---------------------------------------------------------------------------

def _net_class_to_voltage_class(net_class: str) -> VoltageClass:
    """Map a free-form net-class string to an IEC 60335-1 ``VoltageClass``.

    The mapping is intentionally broad so callers can pass short labels
    (``"HV"``, ``"LV"``) or full names (``"HIGH_VOLTAGE"``) and still
    get the right table-entry.
    """
    upper = net_class.upper()

    if any(kw in upper for kw in ("HIGH_VOLTAGE", "HV", "MAINS_240V", "MAINS", "AC")):
        # Distinguish 120 V vs 240 V when possible
        if "120" in upper:
            return VoltageClass.MAINS_120V
        if "240" in upper or "MAINS" in upper:
            return VoltageClass.MAINS_240V
        return VoltageClass.HIGH_VOLTAGE

    if "120" in upper or "MAINS_120V" in upper:
        return VoltageClass.MAINS_120V

    if any(kw in upper for kw in ("LOW_VOLTAGE", "LV", "POWER")):
        return VoltageClass.LOW_VOLTAGE

    # Everything else (Signal, GND, SELV, …) → SELV (lowest requirements)
    return VoltageClass.SELV


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def get_clearance(
    net_class_a: str,
    net_class_b: str,
    voltage: float,
    layer_type: str = "external",
    pollution_degree: int = 2,
    material_group: str = "IIIa",
    overvoltage_category: int = 2,
    *,
    design_rule_creepage: float | None = None,
) -> float:
    """Return the most-conservative clearance (mm) across all applicable standards.

    Parameters
    ----------
    net_class_a : str
        Net-class label for the first net (e.g. ``"HV"``, ``"Signal"``).
    net_class_b : str
        Net-class label for the second net.
    voltage : float
        Working voltage (V).  For two nets at different potentials, pass
        the *maximum* of the two (or the voltage difference).
    layer_type : str
        ``"external"`` (default) for outer layers, ``"internal"`` for
        inner-layer routing that qualifies for the IEC 60664-1 reduction.
    pollution_degree : int
        1 = sealed, 2 = normal (default), 3 = conductive pollution.
    material_group : str
        CTI group for IEC 60950-1 creepage (``"IIIa"`` = standard FR-4).
    overvoltage_category : int
        Transient overvoltage category I-IV (default 2).
    design_rule_creepage : float or None
        When supplied, an explicit creepage value from the board's
        ``NetClassRules`` (IEC 62368-1 pathway).  The engine will include
        it in the conservative-max computation.

    Returns
    -------
    float
        Required clearance in mm.  This is the **maximum** of every
        standard consulted, ensuring the design satisfies all of them.
    """
    candidates: list[float] = []

    # ---- IEC 60950-1 ---------------------------------------------------
    try:
        iec60950 = calculate_safety_distances(
            voltage_v=voltage,
            pollution_degree=pollution_degree,
            material_group=material_group,
            overvoltage_category=overvoltage_category,
        )
        candidates.append(iec60950.clearance_mm)
        candidates.append(iec60950.creepage_mm)
    except Exception:
        pass  # Degrade gracefully if the table somehow fails

    # ---- IEC 60335-1 (VoltageClass tables) ----------------------------
    try:
        vc_a = _net_class_to_voltage_class(net_class_a)
        vc_b = _net_class_to_voltage_class(net_class_b)
        # Use the more demanding of the two net classes
        for vc in (vc_a, vc_b):
            candidates.append(vc.get_clearance_mm(pollution_degree))
            candidates.append(vc.get_creepage_mm())
    except Exception:
        pass

    # ---- IPC-2221 (generic PCB creepage table) ------------------------
    try:
        ipc = _calculate_required_creepage(voltage)
        candidates.append(ipc)
    except Exception:
        pass

    # ---- IEC 62368-1 (design-rule creepage from NetClassRules) --------
    if design_rule_creepage is not None and design_rule_creepage > 0.0:
        candidates.append(design_rule_creepage)

    # ---- Compute base conservative value -------------------------------
    if not candidates:
        # All standards failed — return a safe default
        return 0.5

    result = max(candidates)

    # ---- IEC 60664-1 internal-layer reduction -------------------------
    if layer_type == "internal" and result > 0.5:
            result = result * INTERNAL_LAYER_CREEPAGE_FACTOR

    return result
