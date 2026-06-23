"""
Adaptive congestion detection for A* routing iteration budgeting.

This module provides congestion detection to adaptively scale A* iteration
limits based on local routing difficulty. Unlike the grid-based congestion
analysis in congestion.py (which estimates demand vs supply), this module
detects actual routing difficulty at specific points on the board.

Detection strategies:
1. GridBasedCongestionDetector: Samples ClearanceGrid occupancy in a radius
2. ComponentBasedCongestionDetector: Detects proximity to fine-pitch components

Design principles:
- Protocol-based interface (functional)
- Immutable detectors (frozen dataclasses)
- Pure detection methods (no side effects)
- Composable (can combine multiple detectors)
- Type-safe units (Millimeters to prevent unit confusion bugs)

Example usage:
    >>> from temper_placer.routing.adaptive_congestion import (
    ...     GridBasedCongestionDetector,
    ...     CongestionLevel
    ... )
    >>> from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
    >>> from temper_placer.core.units import Millimeters
    >>>
    >>> grid = ClearanceGrid(width_mm=100, height_mm=100, cell_size_mm=0.1)
    >>> detector = GridBasedCongestionDetector(grid=grid)
    >>> level = detector.detect_congestion(
    ...     point=(Millimeters(50.0), Millimeters(50.0)),
    ...     radius=Millimeters(5.0)
    ... )
    >>> print(level)  # CongestionLevel.LOW, MEDIUM, HIGH, or EXTREME
"""

from dataclasses import dataclass
from typing import Protocol, Tuple, Optional
import math

from temper_placer.routing.iteration_budget import CongestionLevel
from temper_placer.core.units import Millimeters, CellIndex, mm_to_cell, LayerIndex, NetId


class CongestionDetector(Protocol):
    """Protocol for congestion detection strategies.

    Implementers must provide a detect_congestion method that samples
    the board at a point and returns a congestion level.
    """

    def detect_congestion(
        self, point: Tuple[Millimeters, Millimeters], radius: Millimeters = Millimeters(5.0)
    ) -> CongestionLevel:
        """Detect congestion level at a point.

        Args:
            point: (x, y) coordinates in millimeters
            radius: Detection radius in millimeters

        Returns:
            CongestionLevel (LOW/MEDIUM/HIGH/EXTREME)
        """
        ...


@dataclass(frozen=True)
class GridBasedCongestionDetector:
    """Detect congestion from ClearanceGrid occupancy.

    Samples grid cells within a radius and calculates occupancy percentage
    to determine congestion level:
    - <30% occupied → LOW
    - 30-60% → MEDIUM
    - 60-80% → HIGH
    - >80% → EXTREME

    Attributes:
        grid: ClearanceGrid with routing occupancy data
        low_threshold: Occupancy threshold for LOW→MEDIUM (default: 0.3)
        medium_threshold: Occupancy threshold for MEDIUM→HIGH (default: 0.6)
        high_threshold: Occupancy threshold for HIGH→EXTREME (default: 0.8)
    """

    grid: "ClearanceGrid"  # Type hint as string to avoid circular import
    low_threshold: float = 0.3
    medium_threshold: float = 0.6
    high_threshold: float = 0.8

    def detect_congestion(
        self, point: Tuple[Millimeters, Millimeters], radius: Millimeters = Millimeters(5.0)
    ) -> CongestionLevel:
        """Sample grid occupancy in radius around point.

        Args:
            point: (x, y) center point in millimeters
            radius: Detection radius in millimeters

        Returns:
            CongestionLevel based on occupancy percentage
        """
        x, y = point
        cell_size_mm = Millimeters(self.grid.cell_size_mm)

        # Calculate grid bounds for sampling
        x_min = int((x - radius) / cell_size_mm)
        x_max = int((x + radius) / cell_size_mm)
        y_min = int((y - radius) / cell_size_mm)
        y_max = int((y + radius) / cell_size_mm)

        # Clamp to grid bounds (cols=width, rows=height)
        x_min = max(0, x_min)
        x_max = min(self.grid.cols - 1, x_max)
        y_min = max(0, y_min)
        y_max = min(self.grid.rows - 1, y_max)

        # Sample cells in rectangular region
        total_cells = 0
        blocked_cells = 0

        for yi in range(y_min, y_max + 1):
            for xi in range(x_min, x_max + 1):
                # Check if cell is within circular radius
                cell_x = xi * cell_size_mm
                cell_y = yi * cell_size_mm
                dist = math.sqrt((cell_x - x) ** 2 + (cell_y - y) ** 2)

                if dist <= radius:
                    total_cells += 1
                    # Check if cell is blocked (pass mm coordinates)
                    if self._is_cell_blocked(cell_x, cell_y):
                        blocked_cells += 1

        # Calculate occupancy
        if total_cells == 0:
            return CongestionLevel.LOW

        occupancy = blocked_cells / total_cells

        # Map occupancy to congestion level
        if occupancy < self.low_threshold:
            return CongestionLevel.LOW
        elif occupancy < self.medium_threshold:
            return CongestionLevel.MEDIUM
        elif occupancy < self.high_threshold:
            return CongestionLevel.HIGH
        else:
            return CongestionLevel.EXTREME

    def _is_cell_blocked(self, x_mm: float, y_mm: float) -> bool:
        """Check if a grid cell is blocked.

        Args:
            x_mm: Cell x position in millimeters
            y_mm: Cell y position in millimeters

        Returns:
            True if cell is blocked/occupied (NOT available for routing)
        """
        # Use ClearanceGrid API: is_available takes mm coordinates
        # Returns True if available, False if blocked
        # We return the inverse: True if blocked
        try:
            available = self.grid.is_available(x_mm, y_mm, layer=0, net_id=0)
            return not available  # blocked = not available
        except Exception:
            # If error, assume available (not blocked) to be conservative
            return False
        except (IndexError, AttributeError):
            return False


@dataclass(frozen=True)
class ComponentBasedCongestionDetector:
    """Detect congestion from component proximity.

    Fine-pitch components (QFN-56, 0.4mm pitch) create extreme routing
    difficulty in their vicinity due to dense pad arrays and escape routing.

    Detection rules:
    - Within 5mm of fine-pitch IC → EXTREME
    - Within 10mm → HIGH
    - Otherwise → LOW

    Attributes:
        netlist: Netlist with component positions
        fine_pitch_components: Set of component references to check
            (e.g., {"U_MCU", "U_TEMP"})
        extreme_radius_mm: Radius for EXTREME level (default: 5.0mm)
        high_radius_mm: Radius for HIGH level (default: 10.0mm)
    """

    netlist: "Netlist"  # Type hint as string to avoid import
    fine_pitch_components: frozenset = frozenset({"U_MCU", "U_TEMP"})
    extreme_radius_mm: Millimeters = Millimeters(5.0)
    high_radius_mm: Millimeters = Millimeters(10.0)

    def detect_congestion(
        self, point: Tuple[Millimeters, Millimeters], radius: Millimeters = Millimeters(5.0)
    ) -> CongestionLevel:
        """Detect congestion based on component proximity.

        Args:
            point: (x, y) coordinates in millimeters
            radius: Detection radius (not used, kept for protocol compatibility)

        Returns:
            CongestionLevel based on distance to fine-pitch components
        """
        x, y = point

        # Find minimum distance to any fine-pitch component
        min_distance = Millimeters(float("inf"))

        for component_ref in self.fine_pitch_components:
            # Get component position from netlist
            comp_pos = self._get_component_position(component_ref)
            if comp_pos is None:
                continue

            comp_x, comp_y = comp_pos
            distance = Millimeters(math.sqrt((x - comp_x) ** 2 + (y - comp_y) ** 2))
            min_distance = Millimeters(min(min_distance, distance))

        # Map distance to congestion level
        if min_distance <= self.extreme_radius_mm:
            return CongestionLevel.EXTREME
        elif min_distance <= self.high_radius_mm:
            return CongestionLevel.HIGH
        else:
            return CongestionLevel.LOW

    def _get_component_position(self, ref: str) -> Optional[Tuple[Millimeters, Millimeters]]:
        """Get position of a component by reference.

        Args:
            ref: Component reference (e.g., "U_MCU")

        Returns:
            (x, y) position in millimeters, or None if not found
        """
        # Try different netlist API patterns
        if hasattr(self.netlist, "get_component_position"):
            pos = self.netlist.get_component_position(ref)
            if pos:
                return (Millimeters(pos[0]), Millimeters(pos[1]))
        elif hasattr(self.netlist, "components"):
            # netlist.components is a list/tuple, not a dict
            for comp in self.netlist.components:
                if hasattr(comp, "ref") and comp.ref == ref:
                    if hasattr(comp, "initial_position") and comp.initial_position:
                        return (
                            Millimeters(comp.initial_position[0]),
                            Millimeters(comp.initial_position[1]),
                        )
                    elif hasattr(comp, "position") and comp.position:
                        return (Millimeters(comp.position[0]), Millimeters(comp.position[1]))
                    elif hasattr(comp, "x") and hasattr(comp, "y"):
                        return (Millimeters(comp.x), Millimeters(comp.y))

        return None


@dataclass(frozen=True)
class CompositeDetector:
    """Combine multiple congestion detectors (take worst case).

    Useful for combining grid-based and component-based detection:
    - Sample grid occupancy for general congestion
    - Check component proximity for fine-pitch areas
    - Return the highest (worst) congestion level

    Attributes:
        detectors: Tuple of detectors to combine
    """

    detectors: Tuple[CongestionDetector, ...]

    def detect_congestion(
        self, point: Tuple[Millimeters, Millimeters], radius: Millimeters = Millimeters(5.0)
    ) -> CongestionLevel:
        """Detect congestion using all detectors, return worst case.

        Args:
            point: (x, y) coordinates in millimeters
            radius: Detection radius in millimeters

        Returns:
            Maximum congestion level from all detectors
        """
        if not self.detectors:
            return CongestionLevel.LOW

        levels = [detector.detect_congestion(point, radius) for detector in self.detectors]

        # Return the highest (worst) congestion level
        # EXTREME > HIGH > MEDIUM > LOW
        level_order = {
            CongestionLevel.LOW: 0,
            CongestionLevel.MEDIUM: 1,
            CongestionLevel.HIGH: 2,
            CongestionLevel.EXTREME: 3,
        }

        worst_level = max(levels, key=lambda l: level_order[l])
        return worst_level


# ============================================================================
# Helper Functions
# ============================================================================


def create_default_detector(
    grid: Optional["ClearanceGrid"] = None,
    netlist: Optional["Netlist"] = None,
) -> CongestionDetector:
    """Create a default congestion detector with sensible defaults.

    Args:
        grid: Optional ClearanceGrid for occupancy-based detection
        netlist: Optional Netlist for component-based detection

    Returns:
        CongestionDetector (composite if both grid and netlist provided)
    """
    detectors = []

    if grid is not None:
        detectors.append(GridBasedCongestionDetector(grid=grid))

    if netlist is not None:
        detectors.append(ComponentBasedCongestionDetector(netlist=netlist))

    if len(detectors) == 0:
        # No inputs - return a dummy detector that always returns LOW
        @dataclass(frozen=True)
        class DummyDetector:
            def detect_congestion(
                self, point: Tuple[Millimeters, Millimeters], radius: Millimeters = Millimeters(5.0)
            ) -> CongestionLevel:
                return CongestionLevel.LOW

        return DummyDetector()  # type: ignore
    elif len(detectors) == 1:
        return detectors[0]
    else:
        return CompositeDetector(detectors=tuple(detectors))
