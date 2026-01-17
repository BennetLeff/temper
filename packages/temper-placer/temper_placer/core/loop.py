"""
Loop-centric data model for power electronics PCB design.

This module provides first-class representations of current loops, which are THE
critical abstraction for power electronics PCB layout. EMI and switching performance
are dominated by current loop areas:

- Commutation loop: DC+ -> high-side switch -> low-side switch -> DC- -> DC link cap
- Gate drive loops: Driver output -> gate -> emitter/source -> driver ground
- Bootstrap loop: Bootstrap diode -> bootstrap cap -> high-side supply

Minimizing these loop areas is the primary layout objective for power electronics.

Example usage:
    >>> from temper_placer.core.loop import Loop, LoopType, LoopEvent, LoopPriority
    >>>
    >>> # Define a gate drive loop
    >>> gate_loop = Loop(
    ...     name="gate_drive_high",
    ...     loop_type=LoopType.GATE_DRIVE_HIGH,
    ...     description="High-side IGBT gate drive loop",
    ...     components=["U_GATE_DRV", "Q1"],
    ...     max_area_mm2=50.0,
    ...     priority=LoopPriority.CRITICAL,
    ...     events=LoopEvent(di_dt=1e9, frequency_hz=50000),
    ... )
    >>>
    >>> gate_loop.involves_component("Q1")
    True
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


class LoopType(Enum):
    """Classification of current loop types in power electronics.

    Loop types help the optimizer understand the physical behavior and
    importance of each loop for prioritization and constraint generation.
    """

    # Power switching loops
    COMMUTATION = "commutation"  # Main power switching loop (highest di/dt)
    BUCK_SWITCH = "buck_switch"  # Buck converter switching loop
    BOOST_SWITCH = "boost_switch"  # Boost converter switching loop
    FLYBACK_PRIMARY = "flyback_primary"  # Flyback primary-side loop
    FLYBACK_SECONDARY = "flyback_secondary"  # Flyback secondary-side loop

    # Gate drive loops (critical for EMI)
    GATE_DRIVE_HIGH = "gate_drive_high"  # High-side gate drive
    GATE_DRIVE_LOW = "gate_drive_low"  # Low-side gate drive

    # Auxiliary power loops
    BOOTSTRAP = "bootstrap"  # Bootstrap charging loop
    AUXILIARY_SUPPLY = "auxiliary_supply"  # Aux supply switching

    # Signal/sensing loops
    SENSING = "sensing"  # Current/voltage sensing loop
    FEEDBACK = "feedback"  # Control feedback loop

    # General
    DECOUPLING = "decoupling"  # IC decoupling loop
    CUSTOM = "custom"  # User-defined loop type


class LoopPriority(Enum):
    """Priority levels for loop area optimization.

    Priority determines how aggressively the optimizer tries to minimize
    each loop area. CRITICAL loops may have hard area constraints while
    LOW priority loops are best-effort.
    """

    CRITICAL = "critical"  # Must be minimized - gate drive, commutation
    HIGH = "high"  # Should be minimized - bootstrap, sensing
    MEDIUM = "medium"  # Nice to minimize - auxiliary power
    LOW = "low"  # Best effort - decoupling, non-critical paths


@dataclass
class LoopEvent:
    """Physics metadata describing loop behavior during switching events.

    This data helps the optimizer understand the physical requirements of each
    loop. High di/dt loops need minimal inductance (small area), while high
    dv/dt loops need careful guard ring placement.

    Attributes:
        di_dt: Current slew rate in A/s. Higher values require smaller loop area.
        dv_dt: Voltage slew rate in V/s. Affects coupling to nearby traces.
        frequency_hz: Switching frequency in Hz. Higher frequency = more EMI.
        peak_current_a: Peak loop current in A. Affects trace width requirements.
        rms_current_a: RMS current in A. Affects thermal requirements.
        ringing_freq_hz: Parasitic ringing frequency in Hz. Indicates loop resonance.
    """

    di_dt: float | None = None  # A/s - current slew rate
    dv_dt: float | None = None  # V/s - voltage slew rate
    frequency_hz: float | None = None  # Hz - switching frequency
    peak_current_a: float | None = None  # A - peak loop current
    rms_current_a: float | None = None  # A - RMS current
    ringing_freq_hz: float | None = None  # Hz - parasitic ringing

    def estimated_inductance_nh(self, area_mm2: float, trace_height_mm: float = 0.2) -> float:
        """Estimate loop inductance from area using simplified model.

        Uses the approximation L ≈ μ₀ * A / h where h is the trace-to-plane
        height. This is valid for loops with a solid return plane underneath.

        Args:
            area_mm2: Loop area in square millimeters.
            trace_height_mm: Height from trace to return plane in mm (default 0.2mm).

        Returns:
            Estimated inductance in nanohenries (nH).

        Example:
            >>> event = LoopEvent(di_dt=1e9)
            >>> event.estimated_inductance_nh(100)  # 100 mm² loop
            62.83...
        """
        mu_0 = 4 * math.pi * 1e-7  # H/m, permeability of free space
        h_m = trace_height_mm * 1e-3  # Convert mm to m
        area_m2 = area_mm2 * 1e-6  # Convert mm² to m²
        inductance_h = mu_0 * area_m2 / h_m
        return inductance_h * 1e9  # Convert H to nH

    def max_area_for_inductance_nh(
        self, target_inductance_nh: float, trace_height_mm: float = 0.2
    ) -> float:
        """Calculate maximum loop area for a target inductance.

        Inverse of estimated_inductance_nh - useful for computing area constraints.

        Args:
            target_inductance_nh: Target loop inductance in nH.
            trace_height_mm: Height from trace to return plane in mm.

        Returns:
            Maximum loop area in mm² to achieve target inductance.

        Example:
            >>> event = LoopEvent()
            >>> event.max_area_for_inductance_nh(10)  # 10nH target
            15.91...
        """
        mu_0 = 4 * math.pi * 1e-7  # H/m
        h_m = trace_height_mm * 1e-3  # mm to m
        inductance_h = target_inductance_nh * 1e-9  # nH to H
        area_m2 = inductance_h * h_m / mu_0
        return area_m2 * 1e6  # m² to mm²

    def voltage_spike_v(self, inductance_nh: float) -> float | None:
        """Estimate voltage spike from V = L * di/dt.

        Args:
            inductance_nh: Loop inductance in nH.

        Returns:
            Voltage spike in volts, or None if di/dt is not specified.
        """
        if self.di_dt is None:
            return None
        inductance_h = inductance_nh * 1e-9
        return inductance_h * self.di_dt


@dataclass
class LoopPin:
    """A pin in the loop path.

    Represents a single point in the ordered path that forms the current loop.
    The loop is traced by following pins in order, with the last pin connecting
    back to the first.

    Attributes:
        component_ref: Component reference designator (e.g., 'Q1', 'U1').
        pin_name: Pin name on the component (e.g., 'GATE', 'VCC').
        net_name: Net this pin connects to (optional, can be inferred from netlist).
    """

    component_ref: str  # e.g., 'Q1', 'U_GATE_DRV'
    pin_name: str  # e.g., 'GATE', 'OUTL'
    net_name: str | None = None  # Net this pin connects to

    def __str__(self) -> str:
        """Human-readable representation."""
        if self.net_name:
            return f"{self.component_ref}.{self.pin_name} ({self.net_name})"
        return f"{self.component_ref}.{self.pin_name}"


@dataclass
class Loop:
    """A current loop in the power electronics design.

    This is the primary data structure for loop-centric PCB design. Each loop
    represents a path that current flows through during a switching event.

    Loops can be defined in two ways:
    1. Explicit pin path: Ordered list of LoopPin objects
    2. Component list: Just component refs, pins inferred from netlist

    Attributes:
        name: Unique identifier for this loop.
        loop_type: Classification of the loop (commutation, gate drive, etc.).
        description: Human-readable description of the loop's purpose.
        pins: Ordered list of pins forming the loop path (explicit definition).
        components: Alternative - just component refs (pins inferred).
        nets: Nets traversed by this loop.
        max_area_mm2: Maximum allowed loop area in mm².
        priority: Optimization priority for this loop.
        events: Physics metadata (di/dt, frequency, etc.).
        return_layer: PCB layer for return current (e.g., 'L2_GND').
        return_net: Net name for return path (e.g., 'PGND').

    Example:
        >>> loop = Loop(
        ...     name="commutation",
        ...     loop_type=LoopType.COMMUTATION,
        ...     description="Main half-bridge commutation loop",
        ...     components=["C_DC", "Q1", "Q2"],
        ...     max_area_mm2=200,
        ...     priority=LoopPriority.CRITICAL,
        ...     events=LoopEvent(di_dt=1e9, peak_current_a=50),
        ... )
    """

    name: str
    loop_type: LoopType
    description: str

    # Path definition - use either pins (explicit) or components (inferred)
    pins: list[LoopPin] = field(default_factory=list)
    components: list[str] = field(default_factory=list)

    # Nets traversed by this loop
    nets: list[str] = field(default_factory=list)

    # Constraints
    max_area_mm2: float = 100.0
    priority: LoopPriority = LoopPriority.MEDIUM

    # Physics metadata
    events: LoopEvent = field(default_factory=LoopEvent)

    # Return path information
    return_layer: str | None = None  # e.g., 'L2_GND'
    return_net: str | None = None  # e.g., 'PGND'

    # Source tracking (for debugging/auditing)
    source: str = "manual"  # 'manual', 'auto-extracted', 'template'

    # Computed/cached fields (not included in repr)
    _current_area_mm2: float | None = field(default=None, repr=False)

    def get_component_refs(self) -> list[str]:
        """Get all component references in this loop.

        If components list is provided, returns that. Otherwise extracts
        unique component refs from the pins list.

        Returns:
            List of component reference designators.
        """
        if self.components:
            return self.components
        # Extract unique refs from pins, preserving order
        seen = set()
        refs = []
        for pin in self.pins:
            if pin.component_ref not in seen:
                seen.add(pin.component_ref)
                refs.append(pin.component_ref)
        return refs

    def involves_component(self, ref: str) -> bool:
        """Check if a component is part of this loop.

        Args:
            ref: Component reference designator to check.

        Returns:
            True if the component is in this loop.
        """
        return ref in self.get_component_refs()

    def involves_net(self, net_name: str) -> bool:
        """Check if a net is part of this loop.

        Args:
            net_name: Net name to check.

        Returns:
            True if the net is traversed by this loop.
        """
        # Check explicit nets list
        if net_name in self.nets:
            return True
        # Check pins
        for pin in self.pins:
            if pin.net_name == net_name:
                return True
        return False

    def set_current_area(self, area_mm2: float) -> None:
        """Set the computed current loop area.

        Called by the optimizer after computing actual loop area from placement.

        Args:
            area_mm2: Computed loop area in mm².
        """
        self._current_area_mm2 = area_mm2

    def get_current_area(self) -> float | None:
        """Get the computed current loop area.

        Returns:
            Loop area in mm², or None if not yet computed.
        """
        return self._current_area_mm2

    def is_area_compliant(self) -> bool | None:
        """Check if current area meets the max_area constraint.

        Returns:
            True if compliant, False if over limit, None if area not computed.
        """
        if self._current_area_mm2 is None:
            return None
        return self._current_area_mm2 <= self.max_area_mm2

    def area_margin_pct(self) -> float | None:
        """Calculate margin as percentage of max area.

        Returns:
            Percentage margin (positive = under limit, negative = over).
            None if area not computed.
        """
        if self._current_area_mm2 is None:
            return None
        return (self.max_area_mm2 - self._current_area_mm2) / self.max_area_mm2 * 100

    def estimated_voltage_spike(self, trace_height_mm: float = 0.2) -> float | None:
        """Estimate voltage spike based on current area and di/dt.

        Uses V = L * di/dt where L is estimated from loop area.

        Args:
            trace_height_mm: Height from trace to return plane.

        Returns:
            Estimated voltage spike in volts, or None if data unavailable.
        """
        if self._current_area_mm2 is None or self.events.di_dt is None:
            return None
        inductance_nh = self.events.estimated_inductance_nh(self._current_area_mm2, trace_height_mm)
        return self.events.voltage_spike_v(inductance_nh)


@dataclass
class LoopCollection:
    """Collection of all loops in a design.

    Provides query methods to find loops by component, type, or priority.
    This is the main interface for the optimizer to access loop information.

    Attributes:
        loops: List of all Loop objects in the design.
        name: Optional name for this collection (e.g., 'temper_induction_cooker').
        description: Optional description of the design.

    Example:
        >>> collection = LoopCollection()
        >>> collection.add_loop(gate_loop)
        >>> collection.add_loop(commutation_loop)
        >>>
        >>> critical = collection.get_critical_loops()
        >>> q1_loops = collection.get_loops_for_component("Q1")
    """

    loops: list[Loop] = field(default_factory=list)
    name: str = ""
    description: str = ""

    def add_loop(self, loop: Loop) -> None:
        """Add a loop to the collection.

        Args:
            loop: Loop to add.

        Raises:
            ValueError: If a loop with the same name already exists.
        """
        if any(l.name == loop.name for l in self.loops):
            raise ValueError(f"Loop with name '{loop.name}' already exists")
        self.loops.append(loop)

    def get_loop(self, name: str) -> Loop | None:
        """Get a loop by name.

        Args:
            name: Loop name to find.

        Returns:
            The Loop object, or None if not found.
        """
        for loop in self.loops:
            if loop.name == name:
                return loop
        return None

    def get_loops_for_component(self, ref: str) -> list[Loop]:
        """Get all loops that involve a component.

        Args:
            ref: Component reference designator.

        Returns:
            List of loops containing this component.
        """
        return [loop for loop in self.loops if loop.involves_component(ref)]

    def get_loops_for_net(self, net_name: str) -> list[Loop]:
        """Get all loops that traverse a net.

        Args:
            net_name: Net name to search for.

        Returns:
            List of loops traversing this net.
        """
        return [loop for loop in self.loops if loop.involves_net(net_name)]

    def get_loops_by_type(self, loop_type: LoopType) -> list[Loop]:
        """Get all loops of a specific type.

        Args:
            loop_type: LoopType to filter by.

        Returns:
            List of loops with matching type.
        """
        return [loop for loop in self.loops if loop.loop_type == loop_type]

    def get_loops_by_priority(self, priority: LoopPriority) -> list[Loop]:
        """Get all loops with a specific priority.

        Args:
            priority: LoopPriority to filter by.

        Returns:
            List of loops with matching priority.
        """
        return [loop for loop in self.loops if loop.priority == priority]

    def get_critical_loops(self) -> list[Loop]:
        """Get loops with CRITICAL priority.

        Returns:
            List of critical priority loops.
        """
        return self.get_loops_by_priority(LoopPriority.CRITICAL)

    def get_high_priority_loops(self) -> list[Loop]:
        """Get loops with CRITICAL or HIGH priority.

        Returns:
            List of high-priority loops.
        """
        return [
            loop
            for loop in self.loops
            if loop.priority in (LoopPriority.CRITICAL, LoopPriority.HIGH)
        ]

    def get_all_component_refs(self) -> set[str]:
        """Get all unique component references across all loops.

        Returns:
            Set of all component reference designators.
        """
        refs = set()
        for loop in self.loops:
            refs.update(loop.get_component_refs())
        return refs

    def get_all_nets(self) -> set[str]:
        """Get all unique nets across all loops.

        Returns:
            Set of all net names.
        """
        nets = set()
        for loop in self.loops:
            nets.update(loop.nets)
            for pin in loop.pins:
                if pin.net_name:
                    nets.add(pin.net_name)
        return nets

    def get_non_compliant_loops(self) -> list[Loop]:
        """Get loops that exceed their max_area constraint.

        Returns:
            List of loops where current_area > max_area.
        """
        return [loop for loop in self.loops if loop.is_area_compliant() is False]

    def total_area_violation_mm2(self) -> float:
        """Calculate total area violation across all loops.

        Returns:
            Sum of (current_area - max_area) for all non-compliant loops.
        """
        total = 0.0
        for loop in self.loops:
            area = loop.get_current_area()
            if area is not None and area > loop.max_area_mm2:
                total += area - loop.max_area_mm2
        return total

    def summary(self) -> dict:
        """Generate summary statistics for the collection.

        Returns:
            Dictionary with counts and compliance info.
        """
        compliant = [l for l in self.loops if l.is_area_compliant() is True]
        non_compliant = [l for l in self.loops if l.is_area_compliant() is False]
        unknown = [l for l in self.loops if l.is_area_compliant() is None]

        return {
            "total_loops": len(self.loops),
            "critical_count": len(self.get_critical_loops()),
            "high_priority_count": len(self.get_high_priority_loops()),
            "compliant_count": len(compliant),
            "non_compliant_count": len(non_compliant),
            "unknown_count": len(unknown),
            "total_area_violation_mm2": self.total_area_violation_mm2(),
            "unique_components": len(self.get_all_component_refs()),
            "unique_nets": len(self.get_all_nets()),
        }

    def __len__(self) -> int:
        """Return number of loops in collection."""
        return len(self.loops)

    def __iter__(self):
        """Iterate over loops."""
        return iter(self.loops)

    def __getitem__(self, key):
        """Get loop by index or name."""
        if isinstance(key, int):
            return self.loops[key]
        elif isinstance(key, str):
            loop = self.get_loop(key)
            if loop is None:
                raise KeyError(f"No loop named '{key}'")
            return loop
        else:
            raise TypeError(f"Key must be int or str, not {type(key)}")
