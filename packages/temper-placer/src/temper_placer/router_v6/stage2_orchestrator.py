"""
Router V6 Stage 2 Orchestrator.

Chains the 8 channel-analysis micro-stages in dependency order and
assembles Stage2Output from the final BoardState.

Part of feat/decompose-stage2: U9 Stage2Orchestrator.
"""

from __future__ import annotations

from dataclasses import replace

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.bottleneck_analysis import BottleneckAnalysisStage
from temper_placer.router_v6.channel_skeleton import ChannelSkeletonStage
from temper_placer.router_v6.channel_widths import ChannelWidthsStage
from temper_placer.router_v6.escape_via_generator import EscapeVia
from temper_placer.router_v6.layer_capacity import LayerCapacityStage
from temper_placer.router_v6.obstacle_map import ObstacleMapStage
from temper_placer.router_v6.occupancy_grid import OccupancyGridStage
from temper_placer.router_v6.routing_demand import RoutingDemandStage
from temper_placer.router_v6.routing_space import RoutingSpaceStage
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.stage_validators import run_validators


class Stage2Orchestrator:
    """Chains the 8 channel-analysis micro-stages in dependency order."""

    _stages: list[Stage]

    def __init__(self, verbose: bool = False, profiler: object | None = None):
        self._stages = [
            ObstacleMapStage(),
            RoutingSpaceStage(),
            ChannelSkeletonStage(),
            ChannelWidthsStage(),
            OccupancyGridStage(),
            LayerCapacityStage(),
            RoutingDemandStage(),
            BottleneckAnalysisStage(),
        ]
        self.verbose = verbose
        self._profiler = profiler

    def run(
        self,
        pcb: ParsedPCB,
        escape_vias: list[EscapeVia],
        initial_state: BoardState | None = None,
    ) -> BoardState:
        """Run all 8 micro-stages in dependency order."""
        state = BoardState() if initial_state is None else initial_state

        state = replace(state, _parsed_pcb=pcb, _escape_vias=tuple(escape_vias))

        if self.verbose:
            print("Stage 2 (Orchestrated): Channel analysis...")

        for stage in self._stages:
            if self.verbose:
                idx = self._stages.index(stage) + 1
                print(f"  2.{idx}: {stage.name}...")

            if self._profiler is not None:
                with self._profiler.sub_step("stage2", stage.name):  # type: ignore[attr-defined]
                    state = stage.run(state)
            else:
                state = stage.run(state)

            drc_failures = run_validators(stage.name, state)
            if drc_failures and self.verbose:
                for f in drc_failures:
                    print(f"    DRC WARNING: {f}")

        return state

    @staticmethod
    def assemble_stage2_output(state: BoardState):
        """Assemble legacy Stage2Output from BoardState fields."""
        from temper_placer.router_v6.pipeline import Stage2Output

        return Stage2Output(
            obstacle_maps=state.obstacle_maps,
            routing_spaces=state.routing_spaces,
            skeletons=state.channel_skeletons,
            channel_widths=state.channel_widths,
            occupancy_grids=state.occupancy_grids,
            layer_capacities=state.layer_capacities,
            routing_demand=state.routing_demand,
            bottleneck_analysis=state.bottleneck_analysis,
        )
