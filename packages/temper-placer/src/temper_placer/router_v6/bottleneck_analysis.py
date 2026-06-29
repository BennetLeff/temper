"""
Router V6 Stage 2.8: Identify Bottlenecks

Identifies routing bottlenecks by comparing capacity vs demand.
Part of temper-pox8 (Stage 2 - Channel Analysis)
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from temper_placer.deterministic.stages.base import Stage
from temper_placer.deterministic.state import BoardState
from temper_placer.router_v6.layer_capacity import LayerCapacity
from temper_placer.router_v6.routing_demand import RoutingDemand
from temper_placer.router_v6.stage_validators import (
    StageDRCFailure,
    register_validator,
)


class BottleneckSeverity(Enum):
    """Severity level of a routing bottleneck."""

    NONE = "none"  # No bottleneck
    LOW = "low"  # Mild congestion (capacity > demand * 2)
    MEDIUM = "medium"  # Moderate congestion (capacity > demand * 1.2)
    HIGH = "high"  # Severe congestion (capacity < demand)
    CRITICAL = "critical"  # Impossible to route (capacity << demand)


@dataclass
class Bottleneck:
    """Identified routing bottleneck."""

    layer_name: str
    severity: BottleneckSeverity
    capacity: int  # Estimated trace capacity
    demand: int  # Estimated trace demand
    utilization: float  # demand / capacity ratio

    @property
    def is_critical(self) -> bool:
        """Check if bottleneck is critical."""
        return self.severity == BottleneckSeverity.CRITICAL

    @property
    def margin(self) -> float:
        """Capacity margin (capacity - demand)."""
        return self.capacity - self.demand


@dataclass
class BottleneckAnalysis:
    """Overall bottleneck analysis for the design."""

    bottlenecks: list[Bottleneck]
    total_capacity: int  # Sum across all layers
    total_demand: int  # Total nets to route

    @property
    def has_critical_bottlenecks(self) -> bool:
        """Check if any critical bottlenecks exist."""
        return any(b.is_critical for b in self.bottlenecks)

    @property
    def worst_bottleneck(self) -> Bottleneck | None:
        """Return the most severe bottleneck."""
        if not self.bottlenecks:
            return None
        return max(self.bottlenecks, key=lambda b: b.utilization)


def identify_bottlenecks(
    layer_capacities: dict[str, LayerCapacity],
    demand: RoutingDemand,
) -> BottleneckAnalysis:
    """
    Identify routing bottlenecks by comparing capacity vs demand.

    Args:
        layer_capacities: Map of layer name -> LayerCapacity
        demand: Routing demand estimate

    Returns:
        BottleneckAnalysis with identified bottlenecks

    Example:
        >>> analysis = identify_bottlenecks(capacities, demand)
        >>> analysis.has_critical_bottlenecks
        False
    """
    bottlenecks = []
    total_capacity = 0

    # Distribute demand across layers (simplified - assume even distribution)
    num_layers = len(layer_capacities)
    demand_per_layer = demand.routable_nets // num_layers if num_layers > 0 else 0

    # Analyze each layer
    for layer_name, capacity in layer_capacities.items():
        total_capacity += capacity.estimated_traces

        # Calculate utilization
        if capacity.estimated_traces > 0:
            utilization = demand_per_layer / capacity.estimated_traces
        else:
            utilization = float('inf')

        # Determine severity
        severity = _classify_severity(capacity.estimated_traces, demand_per_layer)

        bottlenecks.append(Bottleneck(
            layer_name=layer_name,
            severity=severity,
            capacity=capacity.estimated_traces,
            demand=demand_per_layer,
            utilization=utilization,
        ))

    return BottleneckAnalysis(
        bottlenecks=bottlenecks,
        total_capacity=total_capacity,
        total_demand=demand.routable_nets,
    )


def _classify_severity(capacity: int, demand: int) -> BottleneckSeverity:
    """
    Classify bottleneck severity based on capacity/demand ratio.

    Args:
        capacity: Estimated trace capacity
        demand: Estimated trace demand

    Returns:
        BottleneckSeverity classification
    """
    if capacity == 0:
        if demand > 0:
            return BottleneckSeverity.CRITICAL
        return BottleneckSeverity.NONE

    ratio = capacity / demand if demand > 0 else float('inf')

    if ratio < 0.5:
        return BottleneckSeverity.CRITICAL
    elif ratio < 1.0:
        return BottleneckSeverity.HIGH
    elif ratio < 1.2:
        return BottleneckSeverity.MEDIUM
    elif ratio < 2.0:
        return BottleneckSeverity.LOW
    else:
        return BottleneckSeverity.NONE


class BottleneckAnalysisStage(Stage):
    '''Stage 2.8: Identify routing bottlenecks.'''

    @property
    def name(self) -> str:
        return "BottleneckAnalysis"

    def run(self, state: BoardState) -> BoardState:
        bottleneck_analysis = identify_bottlenecks(
            state.layer_capacities,
            state.routing_demand,
        )
        return replace(state, bottleneck_analysis=bottleneck_analysis)


@register_validator("BottleneckAnalysis")
def validate_bottleneck_analysis(state: BoardState) -> list[StageDRCFailure]:
    '''Validate bottleneck analysis invariants.'''
    failures: list[StageDRCFailure] = []
    if state.bottleneck_analysis is None:
        failures.append(StageDRCFailure(
            field="bottleneck_analysis", value=None,
            reason="Bottleneck analysis not computed", stage="BottleneckAnalysis",
        ))
        return failures

    ba = state.bottleneck_analysis
    num_layers = len(state.layer_capacities) if state.layer_capacities else 0
    if len(ba.bottlenecks) > num_layers:
        failures.append(StageDRCFailure(
            field="bottleneck_analysis",
            value="bottlenecks=" + repr(len(ba.bottlenecks)) + ", layers=" + repr(num_layers),
            reason="More bottlenecks than layers",
            stage="BottleneckAnalysis",
        ))

    for bn in ba.bottlenecks:
        if bn.severity == BottleneckSeverity.CRITICAL and bn.demand == 0:
            failures.append(StageDRCFailure(
                field="bottleneck_analysis",
                value=bn.layer_name,
                reason="CRITICAL severity with zero demand",
                stage="BottleneckAnalysis",
            ))

    return failures
