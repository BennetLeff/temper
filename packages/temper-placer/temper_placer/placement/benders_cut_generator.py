"""
Benders Cut Generator.

Converts blocking components (from min-cut analysis) and router failures
into routability cuts for the ILP Master Problem.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from temper_placer.placement.benders_mincut_mapper import BlockingComponent
    from temper_placer.placement.router_failure_types import BlockingPair
else:
    BlockingComponent = Any
    BlockingPair = Any

from temper_placer.placement.benders_mincut_mapper import CutDirection
from temper_placer.router_v6.stage0_data import DesignRules as RouterDesignRules


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
    3. Estimates required gap based on congestion and net class rules
    4. Returns RoutabilityCut objects
    """

    def __init__(
        self,
        design_rules: RouterDesignRules,
        min_gap_mm: float = 2.0,
        max_gap_mm: float = 25.0,  # Increased from 10.0mm to accommodate 3.0mm HV tracks
    ):
        """
        Initialize the cut generator.

        Args:
            design_rules: Design rules containing net class and default routing parameters
            min_gap_mm: Minimum gap to enforce
            max_gap_mm: Maximum gap to enforce
        """
        self.min_gap_mm = min_gap_mm
        self.max_gap_mm = max_gap_mm
        self._design_rules = design_rules
        self.base_trace_width_mm = design_rules.default_trace_width_mm
        self.base_clearance_mm = design_rules.default_clearance_mm
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
        vertical_blockers = [b for b in blocking_components if b.direction == CutDirection.VERTICAL]

        # Generate horizontal cuts (left-right separation)
        if len(horizontal_blockers) >= 2:
            h_cuts = self._generate_direction_cuts(horizontal_blockers, CutType.HORIZONTAL)
            cuts.extend(h_cuts)

        # Generate vertical cuts (up-down separation)
        if len(vertical_blockers) >= 2:
            v_cuts = self._generate_direction_cuts(vertical_blockers, CutType.VERTICAL)
            cuts.extend(v_cuts)

        return cuts

    def generate_cuts_from_router_failures(
        self,
        blocking_pairs: list[BlockingPair],
        iteration: int = 0,
        max_cuts_per_iteration: int = 3,
        min_confidence: float = 0.5,
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

    def _get_trace_params_for_blockers(
        self, blocker1: BlockingComponent, blocker2: BlockingComponent
    ) -> tuple[float, float]:
        """
        Get trace width and clearance based on HV nets in blocking components.

        Returns the maximum trace_width and clearance from:
        1. HV nets in blocker1
        2. HV nets in blocker2
        3. Design rules defaults

        Args:
            blocker1: First blocking component
            blocker2: Second blocking component

        Returns:
            Tuple of (trace_width, clearance) in mm
        """
        max_width = self.base_trace_width_mm
        max_clearance = self.base_clearance_mm

        for blocker in [blocker1, blocker2]:
            for net_name in blocker.hv_nets:
                rules = self._design_rules.get_rules_for_net(net_name)
                if rules:
                    max_width = max(max_width, rules.trace_width_mm)
                    max_clearance = max(max_clearance, rules.clearance_mm)

        return max_width, max_clearance

    def _estimate_gap(self, blocker1: BlockingComponent, blocker2: BlockingComponent) -> float:
        """
        Estimate the required gap between two blocking components.

        Uses net-class-aware trace width and clearance based on the HV nets
        connected to each blocking component.

        Args:
            blocker1: First blocking component
            blocker2: Second blocking component

        Returns:
            Required gap in mm
        """
        trace_width, clearance = self._get_trace_params_for_blockers(blocker1, blocker2)
        pitch = trace_width + clearance

        # Start with a base of 1 net if no specific HV nets are listed
        # This handles signal nets or generic blockages
        nets1 = len(blocker1.hv_nets) if blocker1.hv_nets else 1
        nets2 = len(blocker2.hv_nets) if blocker2.hv_nets else 1
        
        # Use the maximum net count of the pair as a proxy for channel demand
        # We assume the gap needs to support the larger bundle of nets
        num_nets_estimate = max(nets1, nets2)

        # Calculate gap: number of nets * pitch with a safety margin
        # We rely on net count rather than edges_involved (which counts grid units and determines huge gaps)
        required_gap = num_nets_estimate * pitch * 1.2 + self.min_gap_mm

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
