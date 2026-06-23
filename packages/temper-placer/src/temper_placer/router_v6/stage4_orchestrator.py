"""
Router V6 Stage 4 Orchestrator.

Chains the 4 A* pathfinding micro-stages in dependency order and
assembles PathfindingResult from the final BoardState.

Part of feat/stage4-astar-strangler: U6 Stage4Orchestrator.
"""

from __future__ import annotations

from dataclasses import replace

from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.stages.base import Stage
from temper_placer.router_v6.astar_pathfinding import PathfindingResult
from temper_placer.router_v6.grid_prep_stage import GridPrepStage
from temper_placer.router_v6.net_prep_stage import NetPrepStage
from temper_placer.router_v6.route_stage import RouteStage
from temper_placer.router_v6.result_aggregate_stage import ResultAggregateStage
from temper_placer.router_v6.stage_validators import run_validators


class Stage4Orchestrator:
    """Chains the 4 A* pathfinding micro-stages in dependency order."""

    _stages: list[Stage]

    def __init__(self, verbose: bool = False):
        self._stages = [
            GridPrepStage(),
            NetPrepStage(),
            RouteStage(),
            ResultAggregateStage(),
        ]
        self.verbose = verbose

    def run(
        self,
        initial_state: BoardState | None = None,
    ) -> BoardState:
        """Run all 4 micro-stages in dependency order."""
        if initial_state is None:
            state = BoardState()
        else:
            state = initial_state

        if self.verbose:
            print("Stage 4 (Orchestrated): A* Pathfinding...")

        for stage in self._stages:
            if self.verbose:
                idx = self._stages.index(stage)
                print(f"  4.{idx}: {stage.name}...")
            state = stage.run(state)

            drc_failures = run_validators(stage.name, state)
            if drc_failures and self.verbose:
                for f in drc_failures:
                    print(f"    DRC WARNING: {f}")

        return state

    @staticmethod
    def assemble_pathfinding_result(state: BoardState) -> PathfindingResult | None:
        """Assemble PathfindingResult from BoardState fields."""
        return getattr(state, "pathfinding_result", None)
