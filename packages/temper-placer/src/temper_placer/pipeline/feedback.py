"""
Validation feedback and root cause analysis for PCB design.

This module analyzes validation failures and suggests actionable fixes
targeting placement, routing, or specification relaxation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Literal

import jax.numpy as jnp

if TYPE_CHECKING:
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Netlist
    from temper_placer.core.state import PlacementState
    from temper_placer.pipeline.orchestrator import PipelineState

from temper_placer.losses.base import LossContext, LossFunction, LossResult
from temper_placer.router_v6.congestion_heatmap import CongestionHeatmap


class AdjustmentType(Enum):
    PLACEMENT = "placement"
    ROUTING = "routing"
    SPECIFICATION = "specification"


class RoutingFeedbackLoss(LossFunction):
    """Loss function that penalizes placement in congested areas.

    Uses a pre-computed CongestionHeatmap to create a cost field
    that repels components from routing bottlenecks.
    """

    def __init__(self, heatmap: CongestionHeatmap, sigma: float = 2.0):
        self.heatmap = heatmap

        # Apply Gaussian blur to create a smooth cost field for gradients
        from scipy.ndimage import gaussian_filter
        blurred_grid = gaussian_filter(heatmap.grid, sigma=sigma)

        # Pre-process grid for JAX
        self.grid = jnp.array(blurred_grid)
        self.origin = jnp.array(heatmap.origin)
        self.cell_size = heatmap.cell_size

    @property
    def name(self) -> str:
        return "routing_feedback"

    @property
    def supports_virtual_nodes(self) -> bool:
        return False

    def __call__(
        self,
        positions: jnp.ndarray,
        _rotations: jnp.ndarray,
        _context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        _net_virtual_nodes: jnp.ndarray | None = None,
    ) -> LossResult:
        """Compute congestion loss for all components."""
        # Convert world positions to grid indices
        # grid_pos = (positions - origin) / cell_size
        # map_coordinates expects (y, x) order for (row, col) grid

        # Grid index coordinates
        gx = (positions[:, 0] - self.origin[0]) / self.cell_size
        gy = (positions[:, 1] - self.origin[1]) / self.cell_size

        # map_coordinates requires (ndim, n_samples)
        coords = (gx, gy)

        # Bi-linear interpolation for smooth gradients
        from jax.scipy.ndimage import map_coordinates
        congestion_values = map_coordinates(self.grid, coords, order=1, mode='nearest')

        # Total loss is sum of congestion at all component centers
        total_loss = jnp.sum(congestion_values)

        return LossResult(
            value=total_loss,
            breakdown={"routing_congestion": total_loss}
        )


class MomentumDampedRoutingFeedbackLoss:
    """Loss function with EWMA-damped congestion across feedback iterations.

    Separates blend (update) from compute (loss evaluation) so the loop
    orchestrator calls blend() once per iteration before the placer runs,
    and the JAX optimizer calls compute_loss() during gradient descent.
    """

    def __init__(self, initial_heatmap: CongestionHeatmap, sigma: float = 2.0):
        from scipy.ndimage import gaussian_filter

        self.origin = jnp.array(initial_heatmap.origin)
        self.cell_size = initial_heatmap.cell_size
        blurred = gaussian_filter(initial_heatmap.grid, sigma=sigma)
        self.blended_grid = jnp.array(blurred)
        self._iteration = 0

    def blend(
        self,
        new_heatmap: CongestionHeatmap,
        iteration: int,
        sigma: float = 2.0,
    ) -> None:
        """Blend a new routing heatmap into the EWMA state.

        Called by the loop orchestrator once per iteration, before the
        placer step. The separation from compute_loss ensures the blend
        happens exactly once per iteration.
        """
        from scipy.ndimage import gaussian_filter

        alpha = max(0.1, 1.0 / (iteration + 1))
        new_grid = jnp.array(gaussian_filter(new_heatmap.grid, sigma=sigma))
        self.blended_grid = alpha * new_grid + (1.0 - alpha) * self.blended_grid
        self._iteration = iteration

    def compute_loss(
        self,
        positions: jnp.ndarray,
        _rotations: jnp.ndarray,
        _context: LossContext,
        _epoch: int = 0,
        _total_epochs: int = 1,
        _net_virtual_nodes: jnp.ndarray | None = None,
    ) -> LossResult:
        """Compute congestion loss from the EWMA-blended grid."""
        from jax.scipy.ndimage import map_coordinates

        from temper_placer.losses.base import LossResult

        gx = (positions[:, 0] - self.origin[0]) / self.cell_size
        gy = (positions[:, 1] - self.origin[1]) / self.cell_size
        coords = (gx, gy)
        congestion_values = map_coordinates(self.blended_grid, coords, order=1, mode="nearest")
        total_loss = jnp.sum(congestion_values)
        return LossResult(
            value=total_loss,
            breakdown={"routing_congestion": total_loss},
        )

    @property
    def iteration(self) -> int:
        return self._iteration

@dataclass
class FeedbackAdjustment:
    """A suggested adjustment to the design."""
    adjustment_type: AdjustmentType
    description: str
    target_ref: str | None = None
    value: Any = None


class FeedbackGenerator:
    """Generates adjustments from validation failures."""
    def __init__(self, state: PlacementState, netlist: Netlist, board: Board):
        self.state = state
        self.netlist = netlist
        self.board = board

    def generate(self, failures: list[ValidationFailure]) -> list[FeedbackAdjustment]:
        adjustments = []
        for failure in failures:
            analysis = analyze_root_cause(failure, self.state, self.netlist, self.board)
            # Pick the best fix
            if analysis.fixes:
                best_fix = analysis.fixes[0]
                adjustments.append(FeedbackAdjustment(
                    adjustment_type=AdjustmentType(best_fix.target),
                    description=best_fix.action,
                    value=best_fix.expected_improvement
                ))
        return adjustments


class AdjustmentApplier:
    """Applies adjustments to design state."""
    def apply(self, state: PipelineState, adjustments: list[FeedbackAdjustment]) -> PipelineState:
        """Apply adjustments to pipeline state."""
        for adj in adjustments:
            if adj.adjustment_type == AdjustmentType.PLACEMENT:
                print(f"Applying placement adjustment: {adj.description}")
                # TODO: Implement actual coordinate shifts
            elif adj.adjustment_type == AdjustmentType.SPECIFICATION:
                print(f"Applying specification adjustment: {adj.description}")
                # TODO: Update state.constraints
        return state


@dataclass
class FeedbackLoopConfig:
    max_iterations: int = 3


@dataclass
class FeedbackLoopResult:
    success: bool
    iterations: int


def run_feedback_loop(state: PipelineState, config: FeedbackLoopConfig) -> FeedbackLoopResult:
    """Run the validation-adjustment feedback loop."""
    iteration = 0
    success = False

    while iteration < config.max_iterations:
        print(f"Feedback Loop Iteration {iteration + 1}/{config.max_iterations}")

        # 1. Validation (Simulated for now)
        # In a real run, this would be populated by ROUTING/POST-ROUTING phases
        failures = []
        if state.physics_report and state.physics_report.emi.power_loop_area_mm2 > 80.0:
                failures.append(ValidationFailure(
                    spec_name="loop_area_power",
                    actual_value=state.physics_report.emi.power_loop_area_mm2,
                    limit_value=80.0,
                    margin=80.0 - state.physics_report.emi.power_loop_area_mm2
                ))

        if not failures:
            success = True
            break

        # 2. Generate Adjustments
        generator = FeedbackGenerator(state.placement_state, state.netlist, state.board)
        adjustments = generator.generate(failures)

        # 3. Apply Adjustments
        applier = AdjustmentApplier()
        state = applier.apply(state, adjustments)

        iteration += 1

    return FeedbackLoopResult(success=success, iterations=iteration)


@dataclass
class SuggestedFix:
    """Actionable fix for a validation failure."""
    target: Literal['placement', 'routing', 'specification']
    action: str
    expected_improvement: float
    feasibility: Literal['easy', 'moderate', 'difficult', 'impossible'] = 'moderate'
    side_effects: list[str] = field(default_factory=list)


@dataclass
class ValidationFailure:
    """A specific failure identified during validation."""
    spec_name: str
    actual_value: float
    limit_value: float
    margin: float  # Negative = violation

    # Root cause breakdown
    placement_contribution: float = 0.0  # % due to component positions
    routing_contribution: float = 0.0    # % due to trace path

    # Actionable fixes
    fixes: list[SuggestedFix] = field(default_factory=list)


@dataclass
class RootCauseAnalysis:
    """Analysis of why a failure occurred and how to fix it."""
    failure: ValidationFailure
    placement_contribution: float
    routing_contribution: float
    fixes: list[SuggestedFix] = field(default_factory=list)


def analyze_root_cause(
    failure: ValidationFailure,
    state: PlacementState,
    netlist: Netlist,
    board: Board,
    # TODO: Add routing data when available
) -> RootCauseAnalysis:
    """
    Analyze a validation failure and suggest fixes.
    """
    if failure.spec_name.startswith('loop_area'):
        return analyze_loop_failure(failure, state, netlist, board)
    elif failure.spec_name.startswith('thermal'):
        return analyze_thermal_failure(failure, state, netlist, board)
    else:
        # Generic fallback
        return RootCauseAnalysis(
            failure=failure,
            placement_contribution=50.0,
            routing_contribution=50.0,
            fixes=[SuggestedFix(
                target='specification',
                action=f"Relax {failure.spec_name} limit",
                expected_improvement=abs(failure.margin),
                feasibility='moderate'
            )]
        )


def compute_min_loop_area(
    state: PlacementState,
    netlist: Netlist,
    loop_refs: list[str],
) -> float:
    """Compute minimum possible loop area from placement (pin-to-pin direct)."""
    import numpy as np

    positions = []
    for ref in loop_refs:
        try:
            idx = netlist.get_component_index(ref)
            positions.append(state.positions[idx])
        except KeyError:
            continue

    if len(positions) < 3:
        return 0.0

    v = np.array(positions)
    # Shoelace formula for polygon area
    area = 0.5 * np.abs(np.dot(v[:, 0], np.roll(v[:, 1], 1)) - np.dot(v[:, 1], np.roll(v[:, 0], 1)))
    return float(area)


def analyze_loop_failure(
    failure: ValidationFailure,
    state: PlacementState,
    netlist: Netlist,
    _board: Board,
) -> RootCauseAnalysis:
    """Analyze EMI/Loop Area failure with attribution."""
    # Try to identify loop components from name
    # Format: "loop_area_<name>" or similar
    loop_name = failure.spec_name.replace("loop_area_", "")

    # Mock loop lookup for now
    # TODO: Get actual loop components from state/netlist
    loop_refs = ["Q1", "Q2", "C_BUS1"] if "power" in loop_name else ["U_MCU", "C_MCU_1"]

    min_placement_area = compute_min_loop_area(state, netlist, loop_refs)
    actual_area = failure.actual_value

    # Attribution
    # placement_contribution: what % of actual area is accounted for by the ideal placement?
    # High % means components are just too far apart.
    # Low % means routing detours are the main problem.
    placement_contrib = min(100.0, (min_placement_area / actual_area * 100.0)) if actual_area > 0 else 0.0
    routing_contrib = 100.0 - placement_contrib

    fixes = []

    # If placement is major contributor (>= 50%)
    if placement_contrib >= 50:
        fixes.append(SuggestedFix(
            target='placement',
            action="Decrease component spacing in critical loop",
            expected_improvement=(min_placement_area - failure.limit_value) * 0.8,
            feasibility='moderate',
            side_effects=["May increase thermal coupling"]
        ))

    # If routing is major contributor (> 30%)
    if routing_contrib > 30:
        fixes.append(SuggestedFix(
            target='routing',
            action="Reroute to reduce detour",
            expected_improvement=(actual_area - min_placement_area) * 0.7,
            feasibility='moderate',
            side_effects=["May require more vias"]
        ))

    # Specification relaxation if best achievable is still above limit
    best_achievable = min_placement_area * 1.1 # 10% routing overhead
    if best_achievable > failure.limit_value:
        fixes.append(SuggestedFix(
            target='specification',
            action=f"Relax {failure.spec_name} limit to {best_achievable:.1f}mm²",
            expected_improvement=failure.actual_value - failure.limit_value,
            feasibility='difficult',
            side_effects=["Verify against regulatory limits"]
        ))

    return RootCauseAnalysis(
        failure=failure,
        placement_contribution=placement_contrib,
        routing_contribution=routing_contrib,
        fixes=sorted(fixes, key=lambda f: f.expected_improvement, reverse=True)
    )


def analyze_thermal_failure(
    failure: ValidationFailure,
    _state: PlacementState,
    _netlist: Netlist,
    _board: Board,
) -> RootCauseAnalysis:
    """Analyze thermal violation."""
    placement_contrib = 90.0
    routing_contrib = 10.0

    fixes = []

    fixes.append(SuggestedFix(
        target='placement',
        action="Move high-power components closer to board edge",
        expected_improvement=abs(failure.margin) * 0.7,
        feasibility='easy',
        side_effects=["May increase wirelength"]
    ))

    fixes.append(SuggestedFix(
        target='routing',
        action="Increase trace width for high-current paths",
        expected_improvement=5.0, # Celsius estimate
        feasibility='moderate',
        side_effects=["Reduces routing channel capacity"]
    ))

    return RootCauseAnalysis(
        failure=failure,
        placement_contribution=placement_contrib,
        routing_contribution=routing_contrib,
        fixes=fixes
    )
