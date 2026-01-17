"""
Base classes for placement heuristics.

Defines the interface that all heuristics must implement, along with
common data structures for passing information between heuristics.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum

from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.io.config_loader import PlacementConstraints


class HeuristicPriority(IntEnum):
    """
    Priority levels for heuristics.

    Lower numbers = higher priority (applied first).
    Heuristics at the same priority level are applied in registration order.
    """

    INITIALIZATION = -1  # Global layout algorithms (spectral, force-directed)
    HARD = 0  # Must satisfy: keep-outs, boundaries
    STRUCTURAL = 1  # Connectors, thermal components at edges
    ORGANIZATIONAL = 2  # Module clustering, decoupling caps
    STYLE = 3  # Signal flow, domain separation
    FILL = 4  # Random placement for remaining components


@dataclass
class ComponentPlacement:
    """
    Placement information for a single component.

    Attributes:
        ref: Component reference designator
        position: (x, y) center position in mm
        rotation: Rotation index (0=0°, 1=90°, 2=180°, 3=270°)
        confidence: How confident the heuristic is (0-1)
        placed_by: Name of the heuristic that placed this component
    """

    ref: str
    position: tuple[float, float]
    rotation: int = 0
    confidence: float = 1.0
    placed_by: str = ""


@dataclass
class HeuristicResult:
    """
    Result of applying a heuristic.

    Attributes:
        placements: Dict of component ref -> ComponentPlacement
        conflicts: List of conflict descriptions (for logging)
        success: Whether the heuristic completed successfully
        message: Optional message describing the result
    """

    placements: dict[str, ComponentPlacement] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    success: bool = True
    message: str = ""

    def merge(self, other: HeuristicResult) -> HeuristicResult:
        """
        Merge another result into this one.

        Later placements override earlier ones for the same component.
        """
        merged_placements = {**self.placements, **other.placements}
        merged_conflicts = self.conflicts + other.conflicts
        return HeuristicResult(
            placements=merged_placements,
            conflicts=merged_conflicts,
            success=self.success and other.success,
            message=f"{self.message}; {other.message}"
            if self.message and other.message
            else self.message or other.message,
        )


@dataclass
class PlacementContext:
    """
    Context passed to all heuristics containing board, netlist, and constraints.

    This is the main input to heuristics and contains all information needed
    for smart initialization decisions.

    Attributes:
        board: Board geometry and zones
        netlist: Components and nets
        constraints: Placement constraints from YAML config
        current_placements: Already-placed components (from higher-priority heuristics)
        keep_out_mask: Optional (H, W) boolean mask of valid placement regions
        rng_key: JAX random key for any stochastic decisions
    """

    board: Board
    netlist: Netlist
    constraints: PlacementConstraints
    current_placements: dict[str, ComponentPlacement] = field(default_factory=dict)
    keep_out_mask: Array | None = None
    rng_key: Array | None = None

    def get_unplaced_components(self) -> list[Component]:
        """Get components that haven't been placed yet."""
        placed_refs = set(self.current_placements.keys())
        return [c for c in self.netlist.components if c.ref not in placed_refs and not c.fixed]

    def get_placed_refs(self) -> set[str]:
        """Get set of already-placed component references."""
        return set(self.current_placements.keys())

    def is_position_valid(self, x: float, y: float, width: float, height: float) -> bool:
        """
        Check if a position is valid (within bounds and not in keep-out).

        Args:
            x, y: Center position in mm
            width, height: Component dimensions in mm

        Returns:
            True if position is valid
        """
        # Check board bounds
        margin = self.constraints.board_margin_mm
        ox, oy = self.board.origin

        half_w, half_h = width / 2, height / 2
        if x - half_w < ox + margin or x + half_w > ox + self.board.width - margin:
            return False
        if y - half_h < oy + margin or y + half_h > oy + self.board.height - margin:
            return False

        # Check keep-out mask if available
        if self.keep_out_mask is not None:
            # Convert to mask coordinates (assuming 1mm resolution)
            mask_x = int(x - ox)
            mask_y = int(y - oy)
            if (
                0 <= mask_x < self.keep_out_mask.shape[1]
                and 0 <= mask_y < self.keep_out_mask.shape[0]
            ):
                if not self.keep_out_mask[mask_y, mask_x]:
                    return False

        return True

    def check_overlap(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
        exclude_refs: set[str] | None = None,
    ) -> bool:
        """
        Check if a position would overlap with already-placed components.

        Args:
            x, y: Center position in mm
            width, height: Component dimensions in mm
            exclude_refs: Component refs to exclude from overlap check

        Returns:
            True if there is an overlap
        """
        exclude_refs = exclude_refs or set()
        half_w, half_h = width / 2, height / 2

        for ref, placement in self.current_placements.items():
            if ref in exclude_refs:
                continue

            comp = self.netlist.get_component(ref)
            other_w, other_h = comp.bounds
            other_half_w, other_half_h = other_w / 2, other_h / 2
            ox, oy = placement.position

            # AABB overlap check
            if abs(x - ox) < half_w + other_half_w and abs(y - oy) < half_h + other_half_h:
                return True

        return False


class Heuristic(ABC):
    """
    Abstract base class for placement heuristics.

    Subclasses implement specific placement strategies by overriding
    the apply() method. Each heuristic has a priority that determines
    when it runs relative to others.

    Example:
        class ThermalEdgeHeuristic(Heuristic):
            @property
            def name(self) -> str:
                return "thermal_edge"

            @property
            def priority(self) -> HeuristicPriority:
                return HeuristicPriority.STRUCTURAL

            def apply(self, context: PlacementContext) -> HeuristicResult:
                # Place thermal components near edges
                ...
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name for this heuristic."""
        pass

    @property
    @abstractmethod
    def priority(self) -> HeuristicPriority:
        """Priority level for this heuristic."""
        pass

    @property
    def description(self) -> str:
        """Human-readable description of what this heuristic does."""
        return ""

    @abstractmethod
    def apply(self, context: PlacementContext) -> HeuristicResult:
        """
        Apply this heuristic to generate placements.

        Args:
            context: PlacementContext with board, netlist, constraints,
                and any placements from higher-priority heuristics.

        Returns:
            HeuristicResult with generated placements.
        """
        pass

    def identify_target_components(self, context: PlacementContext) -> list[Component]:
        """
        Identify which components this heuristic should place.

        Default implementation returns all unplaced components.
        Override to filter for specific component types.

        Args:
            context: PlacementContext

        Returns:
            List of components this heuristic should consider placing.
        """
        return context.get_unplaced_components()
