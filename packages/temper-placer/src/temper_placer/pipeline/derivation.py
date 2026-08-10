"""
Physics-based constraint derivation for PCB placement.

This module derives geometric placement constraints from high-level
physical performance specifications (EMI, Thermal, Signal Integrity).

The derivation compute (EMI `sqrt(area) * 0.8`, thermal `power * 2.0`,
signal-integrity `max_len / 1.5`, the mains-voltage classification
boundaries and the `_min_clearance` key extraction) delegates to the
``temper-orchestration`` crate (``temper_orchestration.derive_emi_max_dist``
/ ``derive_thermal_clearance`` / ``derive_si_max_placement_dist`` /
``mains_voltage_to_class_code`` / ``extract_min_clearance``), pinned
bit-identically by ``tests/pipeline/test_pipeline_feasibility_rust_differential.py``
(oracle: ``tests/pipeline/_pipeline_feasibility_py_oracle.py``).
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING, Any

import temper_orchestration as _rs

if TYPE_CHECKING:
    from temper_placer.core.netlist import Netlist
    from temper_placer.core.specification import PcbSpecification

from temper_placer.core.net_types import VoltageClass

# IEC 60335-1 voltage classes, indexed by `mains_voltage_to_class_code`
# (0=LOW_VOLTAGE, 1=MAINS_120V, 2=MAINS_240V, 3=HIGH_VOLTAGE).
_VOLTAGE_CLASS_BY_CODE = {
    0: VoltageClass.LOW_VOLTAGE,
    1: VoltageClass.MAINS_120V,
    2: VoltageClass.MAINS_240V,
    3: VoltageClass.HIGH_VOLTAGE,
}


def _mains_voltage_to_class(voltage_v: float) -> VoltageClass:
    """Map a mains voltage in volts to the nearest IEC 60335-1 voltage class.

    The boundary comparisons (`<= 50` / `<= 130` / `<= 264`, NaN falling
    through to HIGH_VOLTAGE) are the Rust kernel `mains_voltage_to_class_code`;
    the code-to-pyclass mapping stays here.
    """
    return _VOLTAGE_CLASS_BY_CODE[_rs.mains_voltage_to_class_code(voltage_v)]


def derive_constraints_from_spec(
    spec: PcbSpecification,
    netlist: Netlist,  # noqa: ARG001
) -> dict[str, Any]:
    """
    Derive geometric constraints from physical specifications.

    Returns a dictionary of derived parameters (e.g. max distances).
    """
    derived = {}

    # 1. EMI -> Max Distance and Max Area
    for loop_name, max_area in spec.emi.max_loop_area_mm2.items():
        # L = sqrt(Area). Max side length of a square loop. Conservative
        # estimate for max component spacing (center-to-center), assuming
        # 20% routing overhead. The `sqrt(area) * 0.8` expression is the
        # Rust kernel `derive_emi_max_dist` (IEEE sqrt = CPython math.sqrt,
        # then the same `* 0.8`).
        derived[f"{loop_name}_max_dist"] = _rs.derive_emi_max_dist(float(max_area))
        # Store the max area directly for quality metric scoring
        derived[f"{loop_name}_max_area_mm2"] = max_area

    # 2. Thermal -> Min Spacing
    # Simple model: heat sources should be spaced to avoid thermal overlap
    # Required spacing proportional to power dissipation
    power_map = spec.thermal.power_dissipation
    for ref, power in power_map.items():
        # Heuristic: 2mm per Watt spacing
        # The `power * 2.0` product is the Rust kernel
        # `derive_thermal_clearance`.
        derived[f"{ref}_min_clearance"] = _rs.derive_thermal_clearance(float(power))

    # 3. Signal Integrity -> Max Length
    for net_name, max_len in spec.signal_integrity.max_length_mm.items():
        # Max placement distance should be less than max length
        # Assuming 1.5x routing overhead (Manhattan + detours)
        # The `max_len / 1.5` quotient is the Rust kernel
        # `derive_si_max_placement_dist`.
        derived[f"{net_name}_max_placement_dist"] = _rs.derive_si_max_placement_dist(
            float(max_len)
        )

    # 4. Safety -> Isolation (Creepage/Clearance)
    if spec.safety is not None:
        vc = _mains_voltage_to_class(spec.safety.mains_voltage_v)
        derived["hv_lv_isolation_mm"] = vc.get_clearance_mm(
            pollution_degree=spec.safety.pollution_degree
        )
    else:
        # Default to 6.5mm for reinforced isolation (340V)
        warnings.warn(
            "No safety spec provided — falling back to hardcoded 6.5mm isolation.",
            stacklevel=2,
        )
        derived["hv_lv_isolation_mm"] = 6.5

    return derived


def apply_derived_constraints(
    netlist: Netlist,
    derived: dict[str, Any],
    pcl_constraints: Any = None,
) -> Any:
    """
    Apply derived constraints back to PCL constraint collection.

    When pcl_constraints is provided, synthesized constraints from
    derivation are added to it. Returns the modified collection or
    netlist fallback.

    This resolves the TODO at derivation.py:65 — back-propagation
    of derived parameters to the PCL constraint IR.
    """
    if pcl_constraints is None:
        return netlist

    from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

    for key, value in derived.items():
        # The `_min_clearance` suffix test and the ref extraction
        # (Python `str.replace` all-occurrence semantics) are the Rust
        # kernel `extract_min_clearance`; the PCL object construction is
        # Python IR marshalling.
        extracted = _rs.extract_min_clearance(key, float(value))
        if extracted is not None:
            ref, min_distance = extracted
            pcl_constraints.add(
                SeparatedConstraint(
                    a=ref,
                    b="*",
                    min_distance_mm=float(min_distance),
                    tier=ConstraintTier.STRONG,
                    because=f"Derived from thermal spec: {ref} min clearance {value}mm",
                )
            )

    return pcl_constraints
