"""
Isolation barrier validation functions.

These functions check if PCB layout meets safety isolation requirements
per REQ-SAFE-02 for maintaining proper clearance and isolation between
high-voltage and low-voltage circuits.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class IsolationViolation:
    """An isolation barrier violation."""

    barrier_type: str  # "MAIN_HV_LV", "UCC21550", "ADUM1250"
    component_refs: list[str]
    code: str
    message: str
    location: tuple[float, float] | None = None
    clearance_mm: float | None = None
    slot_width_mm: float | None = None
    severity: str = "error"  # error, warning


@dataclass
class IsolationResult:
    """Result of isolation barrier validation."""

    passed: bool
    violations: list[IsolationViolation]

    @property
    def error_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "error")

    @property
    def warning_count(self) -> int:
        return sum(1 for v in self.violations if v.severity == "warning")


def check_isolation_slot(
    barrier: dict[str, Any],
    min_width_mm: float = 2.0,
) -> IsolationResult:
    """
    Check that isolation barriers have proper routed slot width.

    Isolation barriers require routed slots to maintain creepage distance
    and prevent contamination bridging between HV and LV sides.

    Args:
        barrier: Dict with barrier information including:
            - type: "MAIN_HV_LV", "UCC21550", "ADUM1250"
            - position: (x, y) center position
            - slot_width: actual slot width in mm
            - slot_length: actual slot length in mm
            - board_width: total board width for main barrier
        min_width_mm: Minimum required slot width

    Returns:
        IsolationResult with violations for insufficient slot width
    """
    # TODO: Implement slot width validation
    raise NotImplementedError("Isolation slot width checking not yet implemented")


def check_no_traces_across_barrier(
    traces: list[dict[str, Any]],
    barrier: dict[str, Any],
) -> IsolationResult:
    """
    Check that no traces cross the isolation barrier.

    Only isolation components (transformers, optocouplers) should provide
    electrical connection across HV-LV barriers.

    Args:
        traces: List of trace dictionaries with:
            - start: (x, y) start position
            - end: (x, y) end position
            - net: net name
            - layer: layer name
        barrier: Dict with barrier information including:
            - type: barrier type
            - position: (x, y) center
            - orientation: "horizontal" or "vertical"
            - clearance_mm: required clearance

    Returns:
        IsolationResult with violations for traces crossing barrier
    """
    # TODO: Implement trace crossing detection
    raise NotImplementedError("Trace crossing barrier checking not yet implemented")


def check_ucc21550_barrier(
    driver_position: tuple[float, float],
) -> IsolationResult:
    """
    Check UCC21550 gate driver isolation requirements.

    UCC21550 requires:
    - No traces under transformer area (pins 5-12)
    - Ground plane cutout under package center
    - Separate power domains: VCCI, VDDA, VDDB

    Args:
        driver_position: UCC21550 center position (x, y)

    Returns:
        IsolationResult with violations for UCC21550 isolation violations
    """
    # TODO: Implement UCC21550 specific isolation checking
    raise NotImplementedError("UCC21550 barrier checking not yet implemented")


def check_adum1250_barrier(
    isolator_position: tuple[float, float],
) -> IsolationResult:
    """
    Check ADUM1250 I2C isolator isolation requirements.

    ADUM1250 requires:
    - 10mm clearance between isolated sides
    - Ground plane split under ADUM1250
    - Separate power supplies each side

    Args:
        isolator_position: ADUM1250 center position (x, y)

    Returns:
        IsolationResult with violations for ADUM1250 isolation violations
    """
    # TODO: Implement ADUM1250 specific isolation checking
    raise NotImplementedError("ADUM1250 barrier checking not yet implemented")


def check_ground_plane_split(
    ground_planes: dict[str, list[tuple[float, float, float, float]]],
    barriers: list[dict[str, Any]],
) -> IsolationResult:
    """
    Check that ground planes are properly split at isolation barriers.

    Ground planes must be split to prevent unwanted coupling between
    HV and LV domains while maintaining star-ground topology.

    Args:
        ground_planes: Dict of {layer_name: [(x, y, width, height)]} for ground planes
        barriers: List of barrier dictionaries with position and type

    Returns:
        IsolationResult with violations for improper ground plane splits
    """
    # TODO: Implement ground plane split validation
    raise NotImplementedError("Ground plane split checking not yet implemented")


def check_clearance_distances(
    components: dict[str, dict[str, Any]],
    barriers: list[dict[str, Any]],
    min_clearance_mm: float = 10.0,
) -> IsolationResult:
    """
    Check minimum clearance distances between HV and LV components.

    Safety standards require minimum creepage and clearance distances
    based on working voltage and pollution degree.

    Args:
        components: Dict of {ref: {position, voltage, type}} for all components
        barriers: List of barrier information
        min_clearance_mm: Minimum required clearance distance

    Returns:
        IsolationResult with violations for insufficient clearance
    """
    # TODO: Implement clearance distance checking
    raise NotImplementedError("Clearance distance checking not yet implemented")


def check_power_domain_separation(
    power_supplies: dict[str, dict[str, Any]],
    isolation_components: list[str],
) -> IsolationResult:
    """
    Check that power domains are properly separated by isolation.

    Each isolated side should have its own power supply with no
    direct electrical connection except through isolation components.

    Args:
        power_supplies: Dict of {supply_ref: {voltage, position, domain}} for power supplies
        isolation_components: List of isolation component refs (UCC21550, ADUM1250, etc.)

    Returns:
        IsolationResult with violations for power domain coupling
    """
    # TODO: Implement power domain separation checking
    raise NotImplementedError("Power domain separation checking not yet implemented")
