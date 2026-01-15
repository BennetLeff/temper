"""
Benders Cut Generator.

Converts blocking components (from min-cut analysis) and router failures
into routability cuts for the ILP Master Problem.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.placement.benders_mincut_mapper import BlockingComponent
    from temper_placer.placement.router_failure_types import BlockingPair

from temper_placer.placement.benders_mincut_mapper import CutDirection


class CutType(Enum):
    """Type of routability cut."""

    HORIZONTAL = "horizontal"  # Require horizontal separation
    VERTICAL = "vertical"  # Require vertical separation


@dataclass
class RoutabilityCut:
    """
    A routability cut to add to the ILP Master Problem.

    Attributes:
        cut_type: Direction of required separation
        component_pair: Tuple of (component1_ref, component2_ref)
        gap_required: Minimum channel width in mm
        iteration: Benders iteration when this cut was generated
    """

    cut_type: CutType
    component_pair: tuple[str, str]
    gap_required: float
    iteration: int = 0

    def to_master_problem_args(self) -> tuple[str, list[str], float]:
        """
        Convert to arguments for BendersMasterProblem.add_routability_cut().

        Returns:
            Tuple of (cut_type_str, components_list, gap_required)
        """
        return (self.cut_type.value, list(self.component_pair), self.gap_required)


class BendersCutGenerator:
    """
    Generates routability cuts from blocking components.

    The generator:
    1. Groups blocking components by direction
    2. Identifies pairs that need separation
    3. Estimates required gap based on congestion
    4. Returns RoutabilityCut objects
    """

    def __init__(
        self,
        min_gap_mm: float = 2.0,
        max_gap_mm: float = 10.0,
        base_trace_width_mm: float = 0.2,
        base_clearance_mm: float = 0.2,
    ):
        """
        Initialize the cut generator.

        Args:
            min_gap_mm: Minimum gap to enforce
            max_gap_mm: Maximum gap to enforce
            base_trace_width_mm: Default trace width for gap estimation
            base_clearance_mm: Default clearance for gap estimation
        """
        self.min_gap_mm = min_gap_mm
        self.max_gap_mm = max_gap_mm
        self.base_trace_width_mm = base_trace_width_mm
        self.base_clearance_mm = base_clearance_mm
        self._iteration = 0

    def generate_cuts(
        self, blocking_components: list[BlockingComponent], iteration: int = 0
    ) -> list[RoutabilityCut]:
        """
        Generate routability cuts from blocking components.

        Args:
            blocking_components: List of components blocking routing channels
            iteration: Current Benders iteration number

        Returns:
            List of RoutabilityCut objects
        """
        self._iteration = iteration

        if not blocking_components:
            return []

        cuts = []

        # Group by direction
        horizontal_blockers = [
            b for b in blocking_components if b.direction == CutDirection.HORIZONTAL
        ]
        vertical_blockers = [
            b for b in blocking_components if b.direction == CutDirection.VERTICAL
        ]

        # Generate horizontal cuts (left-right separation)
        if len(horizontal_blockers) >= 2:
            h_cuts = self._generate_direction_cuts(
                horizontal_blockers, CutType.HORIZONTAL
            )
            cuts.extend(h_cuts)

        # Generate vertical cuts (up-down separation)
        if len(vertical_blockers) >= 2:
            v_cuts = self._generate_direction_cuts(vertical_blockers, CutType.VERTICAL)
            cuts.extend(v_cuts)

        return cuts

    def generate_cuts_from_router_failures(
        self, blocking_pairs: list[BlockingPair], iteration: int = 0,
        max_cuts_per_iteration: int = 3, min_confidence: float = 0.5
    ) -> list[RoutabilityCut]:
        """
        Generate routability cuts from router failure analysis.
        
        IMPROVED STRATEGY (Phase 5):
        - Only high-confidence pairs (>0.5 default)
        - Limit cuts per iteration (3 default)
        - Use exact spacing when available (from enhanced diagnostics)
        
        Args:
            blocking_pairs: List of component pairs identified as blocking routing
            iteration: Current Benders iteration number
            max_cuts_per_iteration: Maximum cuts to generate (prevent infeasibility)
            min_confidence: Minimum confidence threshold (0.0-1.0)
            
        Returns:
            List of RoutabilityCut objects
        """
        self._iteration = iteration
        
        if not blocking_pairs:
            return []
        
        # Filter to high-confidence pairs only
        high_confidence = [p for p in blocking_pairs if p.confidence >= min_confidence]
        
        if not high_confidence:
            # Fall back to lower threshold if no high-confidence pairs
            high_confidence = [p for p in blocking_pairs if p.confidence >= 0.3]
        
        # Sort by confidence (highest first)
        high_confidence.sort(key=lambda p: p.confidence, reverse=True)
        
        # Limit number of cuts
        selected = high_confidence[:max_cuts_per_iteration]
        
        cuts = []
        
        for pair in selected:
            # Use the required spacing from the BlockingPair
            # For high-confidence pairs from enhanced diagnostics, this is precise
            # For heuristic pairs, add safety margin
            if pair.confidence >= 0.8:
                # High confidence - use exact spacing
                gap = pair.required_spacing
            else:
                # Lower confidence - add safety margin
                gap = pair.required_spacing * 1.2
            
            # Clamp to reasonable range
            gap = min(max(gap, self.min_gap_mm), self.max_gap_mm)
            
            # Add horizontal cut
            cuts.append(
                RoutabilityCut(
                    cut_type=CutType.HORIZONTAL,
                    component_pair=(pair.component_a, pair.component_b),
                    gap_required=gap,
                    iteration=self._iteration,
                )
            )
            
            # Add vertical cut
            cuts.append(
                RoutabilityCut(
                    cut_type=CutType.VERTICAL,
                    component_pair=(pair.component_a, pair.component_b),
                    gap_required=gap,
                    iteration=self._iteration,
                )
            )
        
        return cuts

    def _generate_direction_cuts(
        self, blockers: list[BlockingComponent], cut_type: CutType
    ) -> list[RoutabilityCut]:
        """
        Generate cuts for a specific direction.

        Args:
            blockers: Blocking components in this direction
            cut_type: Type of cut to generate

        Returns:
            List of RoutabilityCut objects
        """
        cuts = []

        # Sort blockers by position
        if cut_type == CutType.HORIZONTAL:
            # Sort by X position (left to right)
            sorted_blockers = sorted(blockers, key=lambda b: b.position[0])
        else:
            # Sort by Y position (bottom to top)
            sorted_blockers = sorted(blockers, key=lambda b: b.position[1])

        # Generate cuts for adjacent pairs
        for i in range(len(sorted_blockers) - 1):
            b1 = sorted_blockers[i]
            b2 = sorted_blockers[i + 1]

            # Estimate required gap based on congestion
            gap = self._estimate_gap(b1, b2)

            cut = RoutabilityCut(
                cut_type=cut_type,
                component_pair=(b1.component_ref, b2.component_ref),
                gap_required=gap,
                iteration=self._iteration,
            )
            cuts.append(cut)

        return cuts

    def _estimate_gap(
        self, blocker1: BlockingComponent, blocker2: BlockingComponent
    ) -> float:
        """
        Estimate the required gap between two blocking components.

        Args:
            blocker1: First blocking component
            blocker2: Second blocking component

        Returns:
            Required gap in mm
        """
        # Base pitch (trace + clearance)
        pitch = self.base_trace_width_mm + self.base_clearance_mm

        # Use the maximum edge count as a measure of congestion
        max_edges = max(blocker1.edges_involved, blocker2.edges_involved)

        # Conservative estimate: allow space for max_edges traces
        # Add 50% margin for via space and tolerances
        required_gap = max_edges * pitch * 1.5 + self.min_gap_mm

        # Clamp to reasonable range
        return min(max(required_gap, self.min_gap_mm), self.max_gap_mm)


def direction_to_cut_type(direction: CutDirection) -> CutType:
    """
    Convert CutDirection to CutType.

    Args:
        direction: CutDirection enum value

    Returns:
        Corresponding CutType enum value
    """
    if direction == CutDirection.HORIZONTAL:
        return CutType.HORIZONTAL
    else:
        return CutType.VERTICAL
