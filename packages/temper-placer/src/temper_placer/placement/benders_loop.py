"""
Benders Loop Orchestration.

Coordinates the Master Problem (ILP), Subproblem (Max-Flow), and cut generation
to find a provably routable PCB placement.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.placement.benders_cut_generator import RoutabilityCut


class BendersStatus(Enum):
    """Status of Benders optimization."""

    OPTIMAL = "optimal"  # Found provably routable placement
    FEASIBLE = "feasible"  # Found feasible placement (routability not verified)
    INFEASIBLE = "infeasible"  # No feasible placement exists
    MAX_ITERATIONS = "max_iterations"  # Reached iteration limit
    ERROR = "error"  # Error during optimization


@dataclass
class BendersResult:
    """
    Result from Benders optimization.

    Attributes:
        status: Optimization status
        iterations: Number of Benders iterations
        final_positions: Final component positions {ref: (x, y)}
        total_movement: Total component movement in mm
        cuts_added: List of routability cuts added
        solve_time_sec: Total optimization time
        master_problem_time: Time spent in ILP solver
        routability_check_time: Time spent in Max-Flow analysis
    """

    status: BendersStatus
    iterations: int
    final_positions: dict[str, tuple[float, float]]
    total_movement: float
    cuts_added: list[RoutabilityCut]
    solve_time_sec: float
    master_problem_time: float = 0.0
    routability_check_time: float = 0.0


class BendersOptimizer:
    """
    Benders decomposition optimizer for PCB placement.

    Iteratively solves:
    1. Master Problem (ILP): Find valid placement
    2. Subproblem (Max-Flow): Check if placement is routable
    3. Cut Generation: Add constraints to open routing channels
    """

    def __init__(
        self,
        component_data_json: str | Path,
        max_iterations: int = 20,
        time_limit_per_ilp_sec: float = 60.0,
        check_routability: bool = True,
        verbose: bool = True,
    ):
        """
        Initialize the Benders optimizer.

        Args:
            component_data_json: Path to benders_input.json
            max_iterations: Maximum Benders iterations
            time_limit_per_ilp_sec: Time limit for each ILP solve
            check_routability: Whether to check routability (set False for testing)
            verbose: Print progress information
        """
        self.component_data_json = Path(component_data_json)
        self.max_iterations = max_iterations
        self.time_limit_per_ilp_sec = time_limit_per_ilp_sec
        self.check_routability = check_routability
        self.verbose = verbose

        # State
        self.current_iteration = 0
        self.cuts_history: list[RoutabilityCut] = []

        # Components (lazy-loaded)
        self._master_problem = None
        self._mapper = None
        self._cut_generator = None

        # Timing
        self._master_time_total = 0.0
        self._routability_time_total = 0.0

    def optimize(self) -> BendersResult:
        """
        Run Benders optimization loop.

        Returns:
            BendersResult with final placement and statistics
        """
        start_time = time.time()

        try:
            # Initialize components
            self._initialize()

            # Benders loop
            for iteration in range(self.max_iterations):
                self.current_iteration = iteration

                if self.verbose:
                    print(f"\n=== Benders Iteration {iteration + 1}/{self.max_iterations} ===")

                # Step 1: Solve Master Problem
                master_result = self._solve_master_problem()

                if master_result.status == "INFEASIBLE":
                    if self.verbose:
                        print("Master Problem is infeasible!")
                    return self._build_result(
                        BendersStatus.INFEASIBLE,
                        {},
                        0.0,
                        time.time() - start_time,
                    )

                if self.verbose:
                    print(
                        f"Master: {master_result.status}, "
                        f"movement={master_result.objective_value:.2f}mm, "
                        f"time={master_result.solve_time_sec:.2f}s"
                    )

                self._master_time_total += master_result.solve_time_sec

                # If not checking routability, return after first iteration
                if not self.check_routability:
                    return self._build_result(
                        BendersStatus.FEASIBLE if master_result.status == "OPTIMAL" else BendersStatus.ERROR,
                        master_result.positions,
                        master_result.objective_value,
                        time.time() - start_time,
                    )

                # Step 2: Check routability with Max-Flow
                is_routable, min_cut_edges = self._check_routability(master_result.positions)

                if is_routable:
                    if self.verbose:
                        print("✓ Placement is routable!")
                    return self._build_result(
                        BendersStatus.OPTIMAL,
                        master_result.positions,
                        master_result.objective_value,
                        time.time() - start_time,
                    )

                # Step 3: Generate cuts from min-cut
                if self.verbose:
                    print(f"✗ Placement not routable. Min-cut has {len(min_cut_edges)} edges")

                cuts = self._generate_cuts_from_mincut(min_cut_edges)

                if not cuts:
                    if self.verbose:
                        print("Warning: No cuts generated from min-cut")
                    # Continue anyway, might converge on next iteration
                    continue

                if self.verbose:
                    print(f"Generated {len(cuts)} routability cuts")

                # Step 4: Add cuts to Master Problem
                for cut in cuts:
                    self._add_cut(cut)

            # Reached max iterations
            if self.verbose:
                print(f"\nReached maximum iterations ({self.max_iterations})")

            # Return best placement found so far
            final_master = self._solve_master_problem()
            return self._build_result(
                BendersStatus.MAX_ITERATIONS,
                final_master.positions,
                final_master.objective_value,
                time.time() - start_time,
            )

        except Exception as e:
            if self.verbose:
                print(f"Error during optimization: {e}")
                import traceback

                traceback.print_exc()

            return self._build_result(
                BendersStatus.ERROR,
                {},
                float("inf"),
                time.time() - start_time,
            )

    def _initialize(self) -> None:
        """Initialize Master Problem, mapper, and cut generator."""
        from temper_placer.placement.benders_master import BendersMasterProblem
        from temper_placer.placement.benders_mincut_mapper import MinCutMapper
        from temper_placer.placement.benders_cut_generator import BendersCutGenerator
        import json

        # Load component data
        with open(self.component_data_json) as f:
            data = json.load(f)

        # Create Master Problem
        self._master_problem = BendersMasterProblem.from_json(self.component_data_json)
        self._master_problem.build()

        # Create mapper
        from temper_placer.placement.benders_master import ComponentData

        components = []
        for c in data["components"]:
            components.append(
                ComponentData(
                    ref=c["ref"],
                    width_mm=c["width_mm"],
                    height_mm=c["height_mm"],
                    x_mm=c.get("center_x_mm", c.get("x_mm", 0)),
                    y_mm=c.get("center_y_mm", c.get("y_mm", 0)),
                    classification=c.get("classification", "FREE"),
                    hv_nets=c.get("hv_nets", []),
                )
            )

        self._mapper = MinCutMapper(components, tolerance_mm=2.0)

        # Create cut generator
        self._cut_generator = BendersCutGenerator()

        if self.verbose:
            print(f"Initialized with {len(components)} components")

    def _solve_master_problem(self):
        """Solve the ILP Master Problem."""
        return self._master_problem.solve(
            time_limit_sec=self.time_limit_per_ilp_sec,
            iteration=self.current_iteration,
        )

    def _check_routability(self, positions: dict[str, tuple[float, float]]) -> tuple[bool, list]:
        """
        Check if placement is routable using Max-Flow.

        Args:
            positions: Component positions from Master Problem

        Returns:
            Tuple of (is_routable, min_cut_edges)
        """
        # TODO: Integrate with MaxFlowAnalyzer
        # For now, return mock result
        # This requires:
        # 1. Convert placement to PCB file or update existing PCB
        # 2. Run router_v6 pipeline to get channel skeletons
        # 3. Run MaxFlowAnalyzer.compute_feasibility()

        # Mock implementation for testing
        if not hasattr(self, "_mock_routability"):
            self._mock_routability = True

        if self._mock_routability:
            return True, []
        else:
            # Mock min-cut
            return False, [
                (("F.Cu", (30.0, 45.0)), ("F.Cu", (30.0, 55.0)), 0),
            ]

    def _generate_cuts_from_mincut(self, min_cut_edges: list) -> list[RoutabilityCut]:
        """
        Generate routability cuts from min-cut edges.

        Args:
            min_cut_edges: Min-cut edges from Max-Flow analysis

        Returns:
            List of RoutabilityCut objects
        """
        # Map min-cut to blocking components
        blocking = self._mapper.map_mincut_to_components(min_cut_edges)

        # Generate cuts
        cuts = self._cut_generator.generate_cuts(blocking, iteration=self.current_iteration)

        return cuts

    def _add_cut(self, cut: RoutabilityCut) -> None:
        """
        Add a routability cut to the Master Problem.

        Args:
            cut: RoutabilityCut to add
        """
        # Convert cut to Master Problem format
        cut_type, components, gap = cut.to_master_problem_args()

        # Add to Master Problem
        self._master_problem.add_routability_cut(cut_type, components, gap)

        # Track in history
        self.cuts_history.append(cut)

    def _build_result(
        self,
        status: BendersStatus,
        positions: dict[str, tuple[float, float]],
        total_movement: float,
        total_time: float,
    ) -> BendersResult:
        """Build a BendersResult object."""
        return BendersResult(
            status=status,
            iterations=self.current_iteration + 1,
            final_positions=positions,
            total_movement=total_movement,
            cuts_added=self.cuts_history,
            solve_time_sec=total_time,
            master_problem_time=self._master_time_total,
            routability_check_time=self._routability_time_total,
        )


def run_benders_optimization(
    component_data_json: str | Path,
    max_iterations: int = 20,
    verbose: bool = True,
) -> BendersResult:
    """
    Convenience function to run Benders optimization.

    Args:
        component_data_json: Path to benders_input.json
        max_iterations: Maximum Benders iterations
        verbose: Print progress

    Returns:
        BendersResult
    """
    optimizer = BendersOptimizer(
        component_data_json=component_data_json,
        max_iterations=max_iterations,
        verbose=verbose,
    )

    return optimizer.optimize()
