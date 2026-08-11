"""
Coverage-paydown wave 2 tests for heuristics modules.

Covers still-zero-coverage allowlisted functions:
- Heuristic .apply() methods that need real context
- Stale property tests that were on the allowlist without coverage
"""

import numpy as np
import pytest

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.heuristics.base import (
    ComponentPlacement,
    HeuristicPriority,
    HeuristicResult,
    PlacementContext,
)
from temper_placer.io.config_loader import PlacementConstraints


# ============================================================================
# Fixtures
# ============================================================================


def _make_basic_context(board=None, netlist=None, constraints=None, rng_key=None):
    """Build a PlacementContext for testing heuristic apply()."""
    board = board or Board(width=100.0, height=100.0)
    constraints = constraints or PlacementConstraints(
        board_width_mm=100.0, board_height_mm=100.0, board_margin_mm=5.0,
    )
    rng_key = rng_key or np.random.default_rng(42)
    return PlacementContext(
        board=board, netlist=netlist, constraints=constraints, rng_key=rng_key,
    )


def _make_small_netlist():
    """Build a minimal netlist with a couple of components."""
    comps = [
        Component(ref="U1", footprint="SOIC8", bounds=(5, 5),
                  pins=[Pin("1", "1", (0, 0), net="VCC")]),
        Component(ref="C1", footprint="0805", bounds=(2, 1.25),
                  pins=[Pin("1", "1", (0, 0), net="VCC")]),
    ]
    nets = [Net("VCC", [("U1", "1"), ("C1", "1")], net_class="Power")]
    return Netlist(components=comps, nets=nets)


def _make_medium_netlist():
    """Build a netlist with several components suitable for heuristics."""
    comps = [
        Component(ref="U1", footprint="SOIC8", bounds=(5, 5),
                  pins=[Pin("VCC", "8", (2, 1.5), net="VCC"),
                        Pin("GND", "4", (-2, -1.5), net="GND")]),
        Component(ref="Q1", footprint="TO-247", bounds=(10, 10),
                  pins=[Pin("1", "1", (0, 0), net="DC_BUS+")]),
        Component(ref="C1", footprint="0805", bounds=(2, 1.25),
                  pins=[Pin("1", "1", (0, 0), net="VCC")]),
        Component(ref="C2", footprint="0805", bounds=(2, 1.25),
                  pins=[Pin("1", "1", (0, 0), net="VCC")]),
        Component(ref="R1", footprint="0603", bounds=(1.6, 0.8),
                  pins=[Pin("1", "1", (0, 0), net="SPI_CLK")]),
        Component(ref="J1", footprint="CONN", bounds=(10, 6),
                  pins=[Pin("1", "1", (0, 0), net="+3V3")]),
    ]
    nets = [
        Net("VCC", [("U1", "VCC"), ("C1", "1"), ("C2", "1")], net_class="Power"),
        Net("GND", [("U1", "GND")], net_class="Power"),
        Net("DC_BUS+", [("Q1", "1")], net_class="HighVoltage"),
        Net("SPI_CLK", [("R1", "1")], net_class="Signal"),
        Net("+3V3", [("J1", "1")], net_class="Power"),
    ]
    return Netlist(components=comps, nets=nets)


# ============================================================================
# base.py — stale entry coverage (already covered but on allowlist)
# ============================================================================


class TestBasePlacementContext:
    """Cover get_unplaced_components (stale on allowlist)."""

    def test_get_unplaced_components_all_unplaced(self):
        netlist = _make_small_netlist()
        ctx = _make_basic_context(netlist=netlist)
        unplaced = ctx.get_unplaced_components()
        assert len(unplaced) == 2

    def test_get_unplaced_components_partial(self):
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        ctx.current_placements["U1"] = ComponentPlacement(
            ref="U1", position=(50.0, 50.0),
        )
        unplaced = ctx.get_unplaced_components()
        refs = set(c.ref for c in unplaced)
        assert "U1" not in refs
        assert len(unplaced) == 5  # Q1, C1, C2, R1, J1


# ============================================================================
# conflict.py — stale entry coverage
# ============================================================================


class TestConflictResolver:
    """Cover get_all_conflicts (stale on allowlist)."""

    def test_get_all_conflicts_empty(self):
        from temper_placer.heuristics.conflict import ConflictResolver
        cr = ConflictResolver()
        conflicts = cr.get_all_conflicts()
        assert isinstance(conflicts, list)
        assert len(conflicts) == 0

    def test_get_all_conflicts_with_placements(self):
        from temper_placer.heuristics.conflict import ConflictResolver
        from temper_placer.heuristics.base import ComponentPlacement
        cr = ConflictResolver()
        cr.add_placement(
            ComponentPlacement(ref="U1", position=(10.0, 20.0)),
        )
        conflicts = cr.get_all_conflicts()
        assert isinstance(conflicts, list)


# ============================================================================
# organizational.py — heuristic apply() methods
# ============================================================================


class TestOrganizationalApply:
    """Tests for .apply() methods on organizational heuristics."""

    def test_decoupling_cap_heuristic_apply(self):
        from temper_placer.heuristics.organizational import DecouplingCapHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = DecouplingCapHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    def test_domain_separation_heuristic_apply(self):
        from temper_placer.heuristics.organizational import DomainSeparationHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = DomainSeparationHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    def test_functional_module_clustering_heuristic_apply(self):
        from temper_placer.heuristics.organizational import FunctionalModuleClusteringHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = FunctionalModuleClusteringHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    def test_power_flow_topology_heuristic_apply(self):
        from temper_placer.heuristics.organizational import PowerFlowTopologyHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = PowerFlowTopologyHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    # Property tests (stale entries that need coverage)
    def test_decoupling_cap_heuristic_name(self):
        from temper_placer.heuristics.organizational import DecouplingCapHeuristic
        h = DecouplingCapHeuristic()
        assert isinstance(h.name, str)
        assert len(h.name) > 0

    def test_decoupling_cap_heuristic_priority(self):
        from temper_placer.heuristics.organizational import DecouplingCapHeuristic
        h = DecouplingCapHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_decoupling_cap_heuristic_description(self):
        from temper_placer.heuristics.organizational import DecouplingCapHeuristic
        h = DecouplingCapHeuristic()
        assert isinstance(h.description, str)

    def test_domain_separation_heuristic_name(self):
        from temper_placer.heuristics.organizational import DomainSeparationHeuristic
        h = DomainSeparationHeuristic()
        assert isinstance(h.name, str)

    def test_domain_separation_heuristic_priority(self):
        from temper_placer.heuristics.organizational import DomainSeparationHeuristic
        h = DomainSeparationHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_domain_separation_heuristic_description(self):
        from temper_placer.heuristics.organizational import DomainSeparationHeuristic
        h = DomainSeparationHeuristic()
        assert isinstance(h.description, str)

    def test_functional_module_clustering_name(self):
        from temper_placer.heuristics.organizational import FunctionalModuleClusteringHeuristic
        h = FunctionalModuleClusteringHeuristic()
        assert isinstance(h.name, str)

    def test_functional_module_clustering_priority(self):
        from temper_placer.heuristics.organizational import FunctionalModuleClusteringHeuristic
        h = FunctionalModuleClusteringHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_functional_module_clustering_description(self):
        from temper_placer.heuristics.organizational import FunctionalModuleClusteringHeuristic
        h = FunctionalModuleClusteringHeuristic()
        assert isinstance(h.description, str)

    def test_power_flow_topology_name(self):
        from temper_placer.heuristics.organizational import PowerFlowTopologyHeuristic
        h = PowerFlowTopologyHeuristic()
        assert isinstance(h.name, str)

    def test_power_flow_topology_priority(self):
        from temper_placer.heuristics.organizational import PowerFlowTopologyHeuristic
        h = PowerFlowTopologyHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_power_flow_topology_description(self):
        from temper_placer.heuristics.organizational import PowerFlowTopologyHeuristic
        h = PowerFlowTopologyHeuristic()
        assert isinstance(h.description, str)


# ============================================================================
# structural.py — heuristic apply() methods
# ============================================================================


class TestStructuralApply:
    """Tests for .apply() methods on structural heuristics."""

    def test_connector_edge_snapping_apply(self):
        from temper_placer.heuristics.structural import ConnectorEdgeSnappingHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = ConnectorEdgeSnappingHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    def test_critical_loop_apply(self):
        from temper_placer.heuristics.structural import CriticalLoopHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = CriticalLoopHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    def test_keepout_awareness_apply(self):
        from temper_placer.heuristics.structural import KeepoutAwarenessHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = KeepoutAwarenessHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    def test_thermal_edge_placement_apply(self):
        from temper_placer.heuristics.structural import ThermalEdgePlacementHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = ThermalEdgePlacementHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    # Property tests (stale entries)
    def test_connector_edge_snapping_name(self):
        from temper_placer.heuristics.structural import ConnectorEdgeSnappingHeuristic
        h = ConnectorEdgeSnappingHeuristic()
        assert isinstance(h.name, str)

    def test_connector_edge_snapping_priority(self):
        from temper_placer.heuristics.structural import ConnectorEdgeSnappingHeuristic
        h = ConnectorEdgeSnappingHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_connector_edge_snapping_description(self):
        from temper_placer.heuristics.structural import ConnectorEdgeSnappingHeuristic
        h = ConnectorEdgeSnappingHeuristic()
        assert isinstance(h.description, str)

    def test_critical_loop_name(self):
        from temper_placer.heuristics.structural import CriticalLoopHeuristic
        h = CriticalLoopHeuristic()
        assert isinstance(h.name, str)

    def test_critical_loop_priority(self):
        from temper_placer.heuristics.structural import CriticalLoopHeuristic
        h = CriticalLoopHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_critical_loop_description(self):
        from temper_placer.heuristics.structural import CriticalLoopHeuristic
        h = CriticalLoopHeuristic()
        assert isinstance(h.description, str)

    def test_keepout_awareness_name(self):
        from temper_placer.heuristics.structural import KeepoutAwarenessHeuristic
        h = KeepoutAwarenessHeuristic()
        assert isinstance(h.name, str)

    def test_keepout_awareness_priority(self):
        from temper_placer.heuristics.structural import KeepoutAwarenessHeuristic
        h = KeepoutAwarenessHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_keepout_awareness_description(self):
        from temper_placer.heuristics.structural import KeepoutAwarenessHeuristic
        h = KeepoutAwarenessHeuristic()
        assert isinstance(h.description, str)

    def test_thermal_edge_placement_name(self):
        from temper_placer.heuristics.structural import ThermalEdgePlacementHeuristic
        h = ThermalEdgePlacementHeuristic()
        assert isinstance(h.name, str)

    def test_thermal_edge_placement_priority(self):
        from temper_placer.heuristics.structural import ThermalEdgePlacementHeuristic
        h = ThermalEdgePlacementHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_thermal_edge_placement_description(self):
        from temper_placer.heuristics.structural import ThermalEdgePlacementHeuristic
        h = ThermalEdgePlacementHeuristic()
        assert isinstance(h.description, str)


# ============================================================================
# style.py — heuristic apply() methods
# ============================================================================


class TestStyleApply:
    """Tests for .apply() methods on style heuristics."""

    def test_signal_flow_preservation_apply(self):
        from temper_placer.heuristics.style import SignalFlowPreservationHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = SignalFlowPreservationHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    def test_star_ground_topology_apply(self):
        from temper_placer.heuristics.style import StarGroundTopologyHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = StarGroundTopologyHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    # Property tests (stale entries)
    def test_signal_flow_preservation_name(self):
        from temper_placer.heuristics.style import SignalFlowPreservationHeuristic
        h = SignalFlowPreservationHeuristic()
        assert isinstance(h.name, str)

    def test_signal_flow_preservation_priority(self):
        from temper_placer.heuristics.style import SignalFlowPreservationHeuristic
        h = SignalFlowPreservationHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_signal_flow_preservation_description(self):
        from temper_placer.heuristics.style import SignalFlowPreservationHeuristic
        h = SignalFlowPreservationHeuristic()
        assert isinstance(h.description, str)

    def test_star_ground_topology_name(self):
        from temper_placer.heuristics.style import StarGroundTopologyHeuristic
        h = StarGroundTopologyHeuristic()
        assert isinstance(h.name, str)

    def test_star_ground_topology_priority(self):
        from temper_placer.heuristics.style import StarGroundTopologyHeuristic
        h = StarGroundTopologyHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_star_ground_topology_description(self):
        from temper_placer.heuristics.style import StarGroundTopologyHeuristic
        h = StarGroundTopologyHeuristic()
        assert isinstance(h.description, str)


# ============================================================================
# power_stage.py — heuristic apply() methods
# ============================================================================


class TestPowerStageApply:
    """Tests for .apply() methods on power_stage heuristics."""

    def test_driver_proximity_apply(self):
        from temper_placer.heuristics.power_stage import DriverProximityHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = DriverProximityHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    def test_power_stage_template_apply(self):
        from temper_placer.heuristics.power_stage import PowerStageTemplateHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = PowerStageTemplateHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    # Property tests (stale entries)
    def test_driver_proximity_name(self):
        from temper_placer.heuristics.power_stage import DriverProximityHeuristic
        h = DriverProximityHeuristic()
        assert isinstance(h.name, str)

    def test_driver_proximity_priority(self):
        from temper_placer.heuristics.power_stage import DriverProximityHeuristic
        h = DriverProximityHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_power_stage_template_name(self):
        from temper_placer.heuristics.power_stage import PowerStageTemplateHeuristic
        h = PowerStageTemplateHeuristic()
        assert isinstance(h.name, str)

    def test_power_stage_template_priority(self):
        from temper_placer.heuristics.power_stage import PowerStageTemplateHeuristic
        h = PowerStageTemplateHeuristic()
        assert isinstance(h.priority, HeuristicPriority)


# ============================================================================
# topological_init.py — heuristic apply() and properties
# ============================================================================


class TestTopologicalInitApply:
    """Tests for TopologicalInitializationHeuristic."""

    def test_topological_init_apply(self):
        from temper_placer.heuristics.topological_init import TopologicalInitializationHeuristic
        netlist = _make_medium_netlist()
        ctx = _make_basic_context(netlist=netlist)
        h = TopologicalInitializationHeuristic()
        result = h.apply(ctx)
        assert isinstance(result, HeuristicResult)

    def test_topological_init_name(self):
        from temper_placer.heuristics.topological_init import TopologicalInitializationHeuristic
        h = TopologicalInitializationHeuristic()
        assert isinstance(h.name, str)

    def test_topological_init_priority(self):
        from temper_placer.heuristics.topological_init import TopologicalInitializationHeuristic
        h = TopologicalInitializationHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_topological_init_description(self):
        from temper_placer.heuristics.topological_init import TopologicalInitializationHeuristic
        h = TopologicalInitializationHeuristic()
        assert isinstance(h.description, str)


# ============================================================================
# mcu_subsystem.py — heuristic apply() method
# ============================================================================


class TestMCUSubsystemApply:
    """Tests for MCUSubsystemHeuristic.apply."""

    def test_mcu_subsystem_apply_needs_mcu_zone(self):
        """MCUSubsystemHeuristic.apply takes netlist, board, zone_name."""
        from temper_placer.heuristics.mcu_subsystem import MCUSubsystemHeuristic
        # Create a board with an MCU zone
        board = Board(
            width=100.0, height=100.0,
            zones=[Zone("MCU", (20, 20, 60, 60))],
        )
        netlist = _make_small_netlist()
        h = MCUSubsystemHeuristic()
        # apply(netlist, board, zone_name) - different from Heuristic base class
        result = h.apply(netlist, board, zone_name="MCU")
        # Result is a PlacementResult from deterministic placer
        assert result is not None


# ============================================================================
# pipeline.py — get_registered_heuristics stale entry
# ============================================================================


class TestPipelineGetRegisteredHeuristics:
    """Cover get_registered_heuristics (stale on allowlist)."""

    def test_get_registered_empty(self):
        from temper_placer.heuristics.pipeline import HeuristicPipeline
        pipeline = HeuristicPipeline()
        registered = pipeline.get_registered_heuristics()
        assert isinstance(registered, list)
        assert registered == []

    def test_get_registered_with_heuristics(self):
        from temper_placer.heuristics import create_default_pipeline
        from temper_placer.heuristics.pipeline import HeuristicPipeline
        pipeline = create_default_pipeline()
        registered = pipeline.get_registered_heuristics()
        assert len(registered) > 0
        # Each entry is (name, priority)
        for entry in registered:
            assert isinstance(entry[0], str)
            assert isinstance(entry[1], HeuristicPriority)


class TestPipelineClear:
    """Cover clear (stale on allowlist)."""

    def test_pipeline_clear(self):
        from temper_placer.heuristics import create_default_pipeline
        from temper_placer.heuristics.pipeline import HeuristicPipeline
        pipeline = create_default_pipeline()
        assert len(pipeline.heuristics) > 0
        pipeline.clear()
        assert len(pipeline.heuristics) == 0
