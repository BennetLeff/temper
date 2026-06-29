"""
Router V6 Stage 2.6: Calculate Per-Layer Capacity

Calculates routing capacity for each layer based on channel widths and grid.
Part of temper-cmzd (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.channel_widths import ChannelWidths
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.stage0_data import ParsedPCB
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


@dataclass
class LayerCapacity:
    """Routing capacity for a single layer."""

    layer_name: str
    total_cells: int  # Total grid cells
    free_cells: int  # Available routing cells
    blocked_cells: int  # Occupied by obstacles

    # Capacity metrics
    min_channel_width: float  # Minimum channel width (mm)
    avg_channel_width: float  # Average channel width (mm)
    estimated_traces: int  # Estimated number of traces that can fit

    @property
    def utilization_ratio(self) -> float:
        """Ratio of blocked to total cells."""
        return self.blocked_cells / self.total_cells if self.total_cells > 0 else 0.0

    @property
    def available_ratio(self) -> float:
        """Ratio of free to total cells."""
        return self.free_cells / self.total_cells if self.total_cells > 0 else 0.0


def calculate_layer_capacity(
    grid: OccupancyGrid,
    widths: ChannelWidths,
    min_trace_width: float = 0.127,  # 5mil
    min_clearance: float = 0.127,  # 5mil
) -> LayerCapacity:
    """
    Calculate routing capacity for a layer.

    Args:
        grid: Occupancy grid from Stage 2.5
        widths: Channel widths from Stage 2.4
        min_trace_width: Minimum trace width in mm
        min_clearance: Minimum clearance in mm

    Returns:
        LayerCapacity with capacity metrics

    Example:
        >>> capacity = calculate_layer_capacity(grid, widths)
        >>> capacity.estimated_traces > 0
        True
    """
    # Get basic grid statistics
    total_cells = grid.width_cells * grid.height_cells
    free_cells = grid.free_cell_count
    blocked_cells = grid.blocked_cell_count

    # Get channel width statistics
    min_channel_width = widths.min_width
    avg_channel_width = widths.avg_width

    # Estimate trace capacity
    # Each trace needs: trace_width + 2*clearance for isolation
    trace_pitch = min_trace_width + 2 * min_clearance

    # Estimate number of traces that can fit in average channel
    if avg_channel_width > 0 and trace_pitch > 0:
        traces_per_channel = int(avg_channel_width / trace_pitch)

        # Estimate total trace capacity (conservative)
        # Use free cells as a proxy for routing area
        estimated_traces = max(1, int(free_cells * 0.01 * traces_per_channel))
    else:
        estimated_traces = 0

    return LayerCapacity(
        layer_name=grid.layer_name,
        total_cells=total_cells,
        free_cells=free_cells,
        blocked_cells=blocked_cells,
        min_channel_width=min_channel_width,
        avg_channel_width=avg_channel_width,
        estimated_traces=estimated_traces,
    )


class LayerCapacityStage(Stage):
    '''Stage 2.6: Calculate per-layer routing capacity.'''

    @property
    def name(self) -> str:
        return "LayerCapacity"

    def run(self, state: BoardState) -> BoardState:
        assert state._parsed_pcb is not None
        pcb: ParsedPCB = state._parsed_pcb
        layer_capacities: dict[str, LayerCapacity] = {}
        for layer_name in state.occupancy_grids:  # type: ignore[union-attr]
            widths = state.channel_widths.get(layer_name)  # type: ignore[union-attr]
            if widths is None:
                continue
            capacity = calculate_layer_capacity(
                state.occupancy_grids[layer_name],  # type: ignore[index]
                widths,
                pcb.design_rules.default_trace_width_mm * 1.5,
                pcb.design_rules.default_clearance_mm,
            )
            layer_capacities[layer_name] = capacity
        return replace(state, layer_capacities=layer_capacities)


@register_validator("LayerCapacity")
def validate_layer_capacity(state: BoardState) -> list[StageDRCFailure]:
    '''Validate layer capacity invariants.'''
    failures: list[StageDRCFailure] = []
    if state.layer_capacities is None:
        failures.append(StageDRCFailure(
            field="layer_capacities", value=None,
            reason="Layer capacities not computed", stage="LayerCapacity",
        ))
        return failures

    for layer_name, lc in state.layer_capacities.items():
        if lc.estimated_traces < 0:
            failures.append(StageDRCFailure(
                field="layer_capacities", value=layer_name,
                reason="Negative estimated traces: " + repr(lc.estimated_traces),
                stage="LayerCapacity",
            ))
        if lc.free_cells > lc.total_cells:
            failures.append(StageDRCFailure(
                field="layer_capacities", value=layer_name,
                reason="Free cells (" + repr(lc.free_cells) + ") > total cells (" + repr(lc.total_cells) + ")",
                stage="LayerCapacity",
            ))

    return failures
