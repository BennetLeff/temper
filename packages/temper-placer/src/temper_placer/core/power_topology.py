"""
Power distribution topology modeling for PCB design.

This module provides immutable types and pure functions for modeling
power rail specifications and routing strategies. Follows functional
programming principles for testability and correctness.

Design Goals:
- Immutable data structures (frozen dataclasses)
- Pure functions (no side effects)
- Type-safe with Protocol interfaces
- IPC-2221 compliant trace width calculations
"""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class PowerDeliveryStrategy(Enum):
    """Routing strategy for power delivery."""

    PLANE = "plane"  # Inner layer copper pour
    WIDE_TRACE = "wide_trace"  # Fat traces on outer layer
    STANDARD_TRACE = "trace"  # Normal routing


@dataclass(frozen=True)
class PowerRailSpec:
    """Immutable specification for a power rail.

    Attributes:
        net_name: KiCad net name (e.g., "+5V", "+3V3")
        max_current_a: Maximum current draw in amperes
        voltage_v: Rail voltage in volts
        source_component: Component reference for power source (e.g., "U_5V")
        sink_components: Tuple of component refs consuming power
    """

    net_name: str
    max_current_a: float
    voltage_v: float
    source_component: str
    sink_components: tuple[str, ...]

    def required_trace_width(self) -> float:
        """Calculate minimum trace width for current capacity.

        Uses simplified IPC-2221 formula for 1oz copper, 10°C rise:
        width(mm) ≈ current(A) * 0.15 + 0.1mm safety margin

        Returns:
            Minimum trace width in millimeters
        """
        return self.max_current_a * 0.15 + 0.1

    def delivery_strategy(self) -> PowerDeliveryStrategy:
        """Determine routing strategy based on current requirements.

        Strategy selection:
        - >= 3.0A: Use plane (inner layer pour)
        - >= 1.0A: Use wide traces
        - <  1.0A: Use standard trace routing

        Returns:
            Recommended PowerDeliveryStrategy
        """
        if self.max_current_a >= 3.0:
            return PowerDeliveryStrategy.PLANE
        elif self.max_current_a >= 1.0:
            return PowerDeliveryStrategy.WIDE_TRACE
        else:
            return PowerDeliveryStrategy.STANDARD_TRACE


@dataclass(frozen=True)
class PowerDistributionTree:
    """Immutable tree structure representing power distribution hierarchy.

    Models power flow from source to loads as a tree. For example:
    +15V -> +5V -> +3V3
         -> VCC_BOOT

    Attributes:
        root: PowerRailSpec for this node
        children: Tuple of child PowerDistributionTree nodes
    """

    root: PowerRailSpec
    children: tuple["PowerDistributionTree", ...]

    def flatten(self) -> list[PowerRailSpec]:
        """DFS traversal of power tree.

        Returns:
            List of all PowerRailSpec nodes in depth-first order
        """
        result = [self.root]
        for child in self.children:
            result.extend(child.flatten())
        return result

    def find_rail(self, net_name: str) -> PowerRailSpec | None:
        """Search tree for specific rail by net name.

        Args:
            net_name: KiCad net name to search for

        Returns:
            PowerRailSpec if found, None otherwise
        """
        if self.root.net_name == net_name:
            return self.root
        for child in self.children:
            found = child.find_rail(net_name)
            if found:
                return found
        return None


class PowerRoutingRule(Protocol):
    """Functional interface for power routing decision logic.

    Implementations provide rules for determining routing strategy
    and trace width based on rail specifications.
    """

    def route_strategy(self, rail: PowerRailSpec) -> PowerDeliveryStrategy:
        """Determine routing strategy for a power rail."""
        ...

    def trace_width(self, rail: PowerRailSpec) -> float:
        """Calculate required trace width for a power rail."""
        ...


@dataclass(frozen=True)
class IPC2221Rule:
    """IPC-2221 compliant trace width calculator.

    Implements IPC-2221 internal trace width formula for current carrying
    capacity. Simplified for common case of 1oz copper with 10°C rise.

    Attributes:
        copper_weight_oz: Copper thickness in oz (default: 1.0)
        temp_rise_c: Allowed temperature rise in Celsius (default: 10.0)
    """

    copper_weight_oz: float = 1.0
    temp_rise_c: float = 10.0

    def trace_width(self, rail: PowerRailSpec) -> float:
        """Calculate IPC-2221 internal trace width.

        Full formula: W = (I / (k * ΔT^b))^(1/c) / (t^0.625)
        For 1oz copper, 10°C rise: W(mm) ≈ I(A) * 0.15 + 0.1
        For thicker copper: W scales with oz^-0.625

        Args:
            rail: PowerRailSpec to calculate width for

        Returns:
            Required trace width in millimeters
        """
        base_width = rail.max_current_a * 0.15 + 0.1

        if self.copper_weight_oz == 1.0:
            return base_width
        else:
            # Thicker copper = narrower trace for same current
            return base_width / (self.copper_weight_oz**0.625)

    def route_strategy(self, rail: PowerRailSpec) -> PowerDeliveryStrategy:
        """Determine routing strategy from current requirements.

        Delegates to PowerRailSpec.delivery_strategy() for consistency.

        Args:
            rail: PowerRailSpec to determine strategy for

        Returns:
            Recommended PowerDeliveryStrategy
        """
        return rail.delivery_strategy()


class TemperPowerTopology:
    """Factory for Temper induction cooker power distribution tree.

    Encodes the specific power architecture:
    - +15V (5A): Primary rail from AC/DC converter
    - +5V (2A): Derived from +15V via buck converter
    - +3V3 (0.5A): Derived from +5V for MCU/sensors
    - VCC_BOOT (0.1A): Bootstrap supply for gate driver
    """

    @staticmethod
    def create() -> PowerDistributionTree:
        """Build Temper power distribution tree.

        Tree structure:
        +15V (5A, PLANE)
        ├── +5V (2A, WIDE_TRACE)
        │   └── +3V3 (0.5A, STANDARD_TRACE)
        └── VCC_BOOT (0.1A, STANDARD_TRACE)

        Returns:
            PowerDistributionTree with all Temper power rails
        """
        v15_rail = PowerRailSpec(
            net_name="+15V",
            max_current_a=5.0,
            voltage_v=15.0,
            source_component="U_15V",
            sink_components=("U_GATE", "U_5V"),
        )

        v5_rail = PowerRailSpec(
            net_name="+5V",
            max_current_a=2.0,
            voltage_v=5.0,
            source_component="U_5V",
            sink_components=("U_3V3", "U_5V_ISO"),
        )

        v33_rail = PowerRailSpec(
            net_name="+3V3",
            max_current_a=0.5,
            voltage_v=3.3,
            source_component="U_3V3",
            sink_components=("U_MCU", "U_TEMP"),
        )

        vcc_boot_rail = PowerRailSpec(
            net_name="VCC_BOOT",
            max_current_a=0.1,
            voltage_v=15.0,
            source_component="U_GATE",
            sink_components=("U_GATE",),
        )

        # Tree structure: +15V -> (+5V -> +3V3, VCC_BOOT)
        v33_tree = PowerDistributionTree(root=v33_rail, children=())
        v5_tree = PowerDistributionTree(root=v5_rail, children=(v33_tree,))
        vcc_boot_tree = PowerDistributionTree(root=vcc_boot_rail, children=())
        v15_tree = PowerDistributionTree(root=v15_rail, children=(v5_tree, vcc_boot_tree))

        return v15_tree
