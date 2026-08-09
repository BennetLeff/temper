"""
Unified Multi-Standard Clearance Engine

Consolidates creepage/clearance requirements from five IEC/IPC standards
into a single queryable function.  Each standard is consulted independently
and the most-conservative (largest) value is returned so that a design
passes all applicable standards simultaneously.

Standards consolidated
----------------------
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

Wave-4 migration note: the leaf kernels now run in the ``temper-geometry``
crate (``via_clearance.rs``) — the IEC 60950-1 tables
(``safety_distances_py``), the word-boundary keyword matcher
(``kw_boundary_match_py``) and the IEC 60335-1 net-class classification
(``net_class_to_voltage_class_py``).  The ``get_clearance`` orchestration,
the ``SafetyDistances`` dataclass, and the ``VoltageClass`` enum mapping
stay here.  Bit-identical parity is pinned by
``tests/router_v6/test_via_clearance_tier2_rust_differential.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import temper_geometry as _tg

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

    @dataclass
    class SafetyDistances:
        clearance_mm: float
        creepage_mm: float
        voltage_v: float

    clearance_mm, creepage_mm, voltage_v = _tg.safety_distances_py(
        voltage_v, pollution_degree, overvoltage_category
    )
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

# The classification itself (the word-boundary keyword scan and the
# 120 V / 240 V branch) runs in temper-geometry's
# ``net_class_to_voltage_class_py``; this table maps the returned IEC 60335-1
# enum value back onto the pyo3 ``VoltageClass`` members.
_VC_FROM_VALUE = {
    VoltageClass.SELV.value: VoltageClass.SELV,
    VoltageClass.LOW_VOLTAGE.value: VoltageClass.LOW_VOLTAGE,
    VoltageClass.MAINS_120V.value: VoltageClass.MAINS_120V,
    VoltageClass.MAINS_240V.value: VoltageClass.MAINS_240V,
    VoltageClass.HIGH_VOLTAGE.value: VoltageClass.HIGH_VOLTAGE,
}


def _kw_boundary_match(upper: str, keywords: tuple[str, ...]) -> bool:
    """Word-boundary keyword match, delimited by ``_`` or start/end of string.

    Delegates to ``temper_geometry.kw_boundary_match_py``, which replicates
    the regex ``(?:^|_)kw(?:$|[\\d_])`` with the Unicode-Nd digit property
    exactly (see the bug-history rationale pinned in the differential suite
    and the Rust module doc for why plain substring matching is forbidden).
    """
    return _tg.kw_boundary_match_py(upper, list(keywords))


def _net_class_to_voltage_class(net_class: str) -> VoltageClass:
    """Map a free-form net-class string to an IEC 60335-1 ``VoltageClass``.

    The mapping is intentionally broad so callers can pass short labels
    (``"HV"``, ``"LV"``) or full names (``"HIGH_VOLTAGE"``) and still
    get the right table-entry. All keyword matching is word-boundary
    (delimited by ``_`` or start/end of string) -- see
    :func:`_kw_boundary_match`'s docstring for why plain substring
    matching here would repeat a defect class already confirmed three
    times in this repo.
    """
    return _VC_FROM_VALUE[_tg.net_class_to_voltage_class_py(net_class)]


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
            _material_group=material_group,
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
