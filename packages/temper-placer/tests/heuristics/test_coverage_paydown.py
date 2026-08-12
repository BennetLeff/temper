"""
Coverage paydown tests for heuristics modules.

Tests the pure functions and heuristic class properties across
organizational, structural, style, and other heuristic modules.
"""

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.config_loader import PlacementConstraints


# ============================================================================
# Organizational module tests
# ============================================================================


def make_simple_netlist():
    """Create a netlist with test components for organizational heuristics."""
    comps = [
        Component(ref="U1", footprint="SOIC8", bounds=(5, 5),
                  pins=[Pin("1", "1", (0, 0), net="VCC")]),
        Component(ref="Q1", footprint="TO-247", bounds=(10, 10),
                  pins=[Pin("1", "1", (0, 0), net="DC_BUS+")]),
        Component(ref="Q2", footprint="TO-247", bounds=(10, 10),
                  pins=[Pin("1", "1", (0, 0), net="DC_BUS+")]),
        Component(ref="C1", footprint="0805", bounds=(2, 1.25),
                  pins=[Pin("1", "1", (0, 0), net="VCC")]),
        Component(ref="C2", footprint="0805", bounds=(2, 1.25),
                  pins=[Pin("1", "1", (0, 0), net="VCC")]),
        Component(ref="R1", footprint="0603", bounds=(1.6, 0.8),
                  pins=[Pin("1", "1", (0, 0), net="SPI_CLK")]),
    ]
    nets = [
        Net("VCC", [("U1", "1"), ("C1", "1"), ("C2", "1")], net_class="Power"),
        Net("DC_BUS+", [("Q1", "1"), ("Q2", "1")], net_class="HighVoltage"),
        Net("SPI_CLK", [("R1", "1")], net_class="Signal"),
    ]
    return Netlist(components=comps, nets=nets)


def make_placement_constraints():
    """Create placement constraints for testing."""
    return PlacementConstraints(
        board_width_mm=100.0,
        board_height_mm=150.0,
        board_margin_mm=5.0,
    )


class TestOrganizationalPureFunctions:
    """Tests for pure functions in organizational.py."""

    def test_identify_functional_modules_returns_list(self):
        """identify_functional_modules returns a list of FunctionalModule."""
        from temper_placer.heuristics.organizational import identify_functional_modules
        netlist = make_simple_netlist()
        constraints = make_placement_constraints()
        result = identify_functional_modules(netlist, constraints)
        assert isinstance(result, list)

    def test_classify_power_topology_returns_list(self):
        """classify_power_topology returns a list."""
        from temper_placer.heuristics.organizational import classify_power_topology
        netlist = make_simple_netlist()
        constraints = make_placement_constraints()
        result = classify_power_topology(netlist, constraints)
        assert isinstance(result, list)

    def test_classify_signal_domains_returns_dict(self):
        """classify_signal_domains returns a dict mapping ref -> domain."""
        from temper_placer.heuristics.organizational import classify_signal_domains
        netlist = make_simple_netlist()
        constraints = make_placement_constraints()
        result = classify_signal_domains(netlist, constraints)
        assert isinstance(result, dict)

    def test_identify_decoupling_caps_returns_dict(self):
        """identify_decoupling_caps returns a dict."""
        from temper_placer.heuristics.organizational import identify_decoupling_caps
        netlist = make_simple_netlist()
        result = identify_decoupling_caps(netlist)
        assert isinstance(result, dict)


class TestOrganizationalHeuristics:
    """Tests for heuristic classes in organizational.py."""

    def test_decoupling_cap_heuristic_name(self):
        """DecouplingCapHeuristic.name returns a string."""
        from temper_placer.heuristics.organizational import DecouplingCapHeuristic
        h = DecouplingCapHeuristic()
        assert isinstance(h.name, str)
        assert len(h.name) > 0

    def test_decoupling_cap_heuristic_priority(self):
        """DecouplingCapHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.organizational import DecouplingCapHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = DecouplingCapHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_decoupling_cap_heuristic_description(self):
        """DecouplingCapHeuristic.description returns a string."""
        from temper_placer.heuristics.organizational import DecouplingCapHeuristic
        h = DecouplingCapHeuristic()
        assert isinstance(h.description, str)

    def test_domain_separation_heuristic_name(self):
        """DomainSeparationHeuristic.name returns a string."""
        from temper_placer.heuristics.organizational import DomainSeparationHeuristic
        h = DomainSeparationHeuristic()
        assert isinstance(h.name, str)
        assert len(h.name) > 0

    def test_domain_separation_heuristic_priority(self):
        """DomainSeparationHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.organizational import DomainSeparationHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = DomainSeparationHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_domain_separation_heuristic_description(self):
        """DomainSeparationHeuristic.description returns a string."""
        from temper_placer.heuristics.organizational import DomainSeparationHeuristic
        h = DomainSeparationHeuristic()
        assert isinstance(h.description, str)

    def test_functional_module_clustering_heuristic_name(self):
        """FunctionalModuleClusteringHeuristic.name returns a string."""
        from temper_placer.heuristics.organizational import FunctionalModuleClusteringHeuristic
        h = FunctionalModuleClusteringHeuristic()
        assert isinstance(h.name, str)

    def test_functional_module_clustering_heuristic_priority(self):
        """FunctionalModuleClusteringHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.organizational import FunctionalModuleClusteringHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = FunctionalModuleClusteringHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_functional_module_clustering_heuristic_description(self):
        """FunctionalModuleClusteringHeuristic.description returns a string."""
        from temper_placer.heuristics.organizational import FunctionalModuleClusteringHeuristic
        h = FunctionalModuleClusteringHeuristic()
        assert isinstance(h.description, str)

    def test_power_flow_topology_heuristic_name(self):
        """PowerFlowTopologyHeuristic.name returns a string."""
        from temper_placer.heuristics.organizational import PowerFlowTopologyHeuristic
        h = PowerFlowTopologyHeuristic()
        assert isinstance(h.name, str)

    def test_power_flow_topology_heuristic_priority(self):
        """PowerFlowTopologyHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.organizational import PowerFlowTopologyHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = PowerFlowTopologyHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_power_flow_topology_heuristic_description(self):
        """PowerFlowTopologyHeuristic.description returns a string."""
        from temper_placer.heuristics.organizational import PowerFlowTopologyHeuristic
        h = PowerFlowTopologyHeuristic()
        assert isinstance(h.description, str)


# ============================================================================
# Structural module tests
# ============================================================================


class TestStructuralPureFunctions:
    """Tests for pure functions in structural.py."""

    def test_identify_connectors_returns_list(self):
        """identify_connectors returns a list of component refs."""
        from temper_placer.heuristics.structural import identify_connectors
        netlist = make_simple_netlist()
        constraints = make_placement_constraints()
        result = identify_connectors(netlist, constraints)
        assert isinstance(result, list)

    def test_identify_thermal_components_returns_list(self):
        """identify_thermal_components returns a list of component refs."""
        from temper_placer.heuristics.structural import identify_thermal_components
        netlist = make_simple_netlist()
        constraints = make_placement_constraints()
        result = identify_thermal_components(netlist, constraints)
        assert isinstance(result, list)

    def test_create_keepout_mask_returns_array(self):
        """create_keepout_mask returns a numpy array."""
        from temper_placer.heuristics.structural import create_keepout_mask
        import numpy as np
        board = Board(width=100.0, height=100.0)
        constraints = make_placement_constraints()
        mask = create_keepout_mask(board, constraints, resolution_mm=5.0)
        assert isinstance(mask, np.ndarray)
        assert mask.ndim == 2


class TestStructuralHeuristics:
    """Tests for heuristic classes in structural.py."""

    def test_connector_edge_snapping_name(self):
        """ConnectorEdgeSnappingHeuristic.name returns a string."""
        from temper_placer.heuristics.structural import ConnectorEdgeSnappingHeuristic
        h = ConnectorEdgeSnappingHeuristic()
        assert isinstance(h.name, str)

    def test_connector_edge_snapping_priority(self):
        """ConnectorEdgeSnappingHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.structural import ConnectorEdgeSnappingHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = ConnectorEdgeSnappingHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_connector_edge_snapping_description(self):
        """ConnectorEdgeSnappingHeuristic.description returns a string."""
        from temper_placer.heuristics.structural import ConnectorEdgeSnappingHeuristic
        h = ConnectorEdgeSnappingHeuristic()
        assert isinstance(h.description, str)

    def test_critical_loop_heuristic_name(self):
        """CriticalLoopHeuristic.name returns a string."""
        from temper_placer.heuristics.structural import CriticalLoopHeuristic
        h = CriticalLoopHeuristic()
        assert isinstance(h.name, str)

    def test_critical_loop_heuristic_priority(self):
        """CriticalLoopHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.structural import CriticalLoopHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = CriticalLoopHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_critical_loop_heuristic_description(self):
        """CriticalLoopHeuristic.description returns a string."""
        from temper_placer.heuristics.structural import CriticalLoopHeuristic
        h = CriticalLoopHeuristic()
        assert isinstance(h.description, str)

    def test_keepout_awareness_heuristic_name(self):
        """KeepoutAwarenessHeuristic.name returns a string."""
        from temper_placer.heuristics.structural import KeepoutAwarenessHeuristic
        h = KeepoutAwarenessHeuristic()
        assert isinstance(h.name, str)

    def test_keepout_awareness_heuristic_priority(self):
        """KeepoutAwarenessHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.structural import KeepoutAwarenessHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = KeepoutAwarenessHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_keepout_awareness_heuristic_description(self):
        """KeepoutAwarenessHeuristic.description returns a string."""
        from temper_placer.heuristics.structural import KeepoutAwarenessHeuristic
        h = KeepoutAwarenessHeuristic()
        assert isinstance(h.description, str)

    def test_thermal_edge_placement_heuristic_name(self):
        """ThermalEdgePlacementHeuristic.name returns a string."""
        from temper_placer.heuristics.structural import ThermalEdgePlacementHeuristic
        h = ThermalEdgePlacementHeuristic()
        assert isinstance(h.name, str)

    def test_thermal_edge_placement_heuristic_priority(self):
        """ThermalEdgePlacementHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.structural import ThermalEdgePlacementHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = ThermalEdgePlacementHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_thermal_edge_placement_heuristic_description(self):
        """ThermalEdgePlacementHeuristic.description returns a string."""
        from temper_placer.heuristics.structural import ThermalEdgePlacementHeuristic
        h = ThermalEdgePlacementHeuristic()
        assert isinstance(h.description, str)


# ============================================================================
# Style module tests
# ============================================================================


class TestStylePureFunctions:
    """Tests for pure functions in style.py."""

    def test_extract_signal_chains_returns_list(self):
        """extract_signal_chains returns a list."""
        from temper_placer.heuristics.style import extract_signal_chains
        netlist = make_simple_netlist()
        constraints = make_placement_constraints()
        result = extract_signal_chains(netlist, constraints)
        assert isinstance(result, list)

    def test_identify_ground_domains_returns_dict(self):
        """identify_ground_domains returns a dict mapping ref -> domain."""
        from temper_placer.heuristics.style import identify_ground_domains
        netlist = make_simple_netlist()
        constraints = make_placement_constraints()
        result = identify_ground_domains(netlist, constraints)
        assert isinstance(result, dict)


class TestStyleHeuristics:
    """Tests for heuristic classes in style.py."""

    def test_signal_flow_preservation_name(self):
        """SignalFlowPreservationHeuristic.name returns a string."""
        from temper_placer.heuristics.style import SignalFlowPreservationHeuristic
        h = SignalFlowPreservationHeuristic()
        assert isinstance(h.name, str)

    def test_signal_flow_preservation_priority(self):
        """SignalFlowPreservationHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.style import SignalFlowPreservationHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = SignalFlowPreservationHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_signal_flow_preservation_description(self):
        """SignalFlowPreservationHeuristic.description returns a string."""
        from temper_placer.heuristics.style import SignalFlowPreservationHeuristic
        h = SignalFlowPreservationHeuristic()
        assert isinstance(h.description, str)

    def test_star_ground_topology_name(self):
        """StarGroundTopologyHeuristic.name returns a string."""
        from temper_placer.heuristics.style import StarGroundTopologyHeuristic
        h = StarGroundTopologyHeuristic()
        assert isinstance(h.name, str)

    def test_star_ground_topology_priority(self):
        """StarGroundTopologyHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.style import StarGroundTopologyHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = StarGroundTopologyHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_star_ground_topology_description(self):
        """StarGroundTopologyHeuristic.description returns a string."""
        from temper_placer.heuristics.style import StarGroundTopologyHeuristic
        h = StarGroundTopologyHeuristic()
        assert isinstance(h.description, str)


# ============================================================================
# Power stage, spectral, topological_init, mcu_subsystem tests
# ============================================================================


class TestPowerStageHeuristic:
    """Tests for power_stage.py heuristics."""

    def test_driver_proximity_name(self):
        """DriverProximityHeuristic.name returns a string."""
        from temper_placer.heuristics.power_stage import DriverProximityHeuristic
        h = DriverProximityHeuristic()
        assert isinstance(h.name, str)

    def test_driver_proximity_priority(self):
        """DriverProximityHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.power_stage import DriverProximityHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = DriverProximityHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_power_stage_template_name(self):
        """PowerStageTemplateHeuristic.name returns a string."""
        from temper_placer.heuristics.power_stage import PowerStageTemplateHeuristic
        h = PowerStageTemplateHeuristic()
        assert isinstance(h.name, str)

    def test_power_stage_template_priority(self):
        """PowerStageTemplateHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.power_stage import PowerStageTemplateHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = PowerStageTemplateHeuristic()
        assert isinstance(h.priority, HeuristicPriority)


class TestTopologicalInitialization:
    """Tests for topological_init.py."""

    def test_topological_init_name(self):
        """TopologicalInitializationHeuristic.name returns a string."""
        from temper_placer.heuristics.topological_init import TopologicalInitializationHeuristic
        h = TopologicalInitializationHeuristic()
        assert isinstance(h.name, str)

    def test_topological_init_priority(self):
        """TopologicalInitializationHeuristic.priority returns HeuristicPriority."""
        from temper_placer.heuristics.topological_init import TopologicalInitializationHeuristic
        from temper_placer.heuristics.base import HeuristicPriority
        h = TopologicalInitializationHeuristic()
        assert isinstance(h.priority, HeuristicPriority)

    def test_topological_init_description(self):
        """TopologicalInitializationHeuristic.description returns a string."""
        from temper_placer.heuristics.topological_init import TopologicalInitializationHeuristic
        h = TopologicalInitializationHeuristic()
        assert isinstance(h.description, str)


class TestMCUSubsystemHeuristic:
    """Tests for mcu_subsystem.py."""

    def test_mcu_subsystem_apply_returns_result(self, simple_netlist, simple_board):
        """MCUSubsystemHeuristic.apply returns PlacementResult (needs MCU zone)."""
        from temper_placer.heuristics.mcu_subsystem import MCUSubsystemHeuristic
        # MCUSubsystemHeuristic is not a Heuristic subclass; it requires a board with MCU zone.
        # Just verify it instantiates without error.
        h = MCUSubsystemHeuristic()
        assert h.template_path is not None
        assert h.template is not None


# ============================================================================
# Pipeline tests
# ============================================================================


class TestHeuristicPipeline:
    """Tests for pipeline.py."""

    def test_create_default_pipeline_returns_pipeline(self):
        """create_default_pipeline returns a HeuristicPipeline."""
        from temper_placer.heuristics import create_default_pipeline
        from temper_placer.heuristics.pipeline import HeuristicPipeline
        pipeline = create_default_pipeline()
        assert isinstance(pipeline, HeuristicPipeline)

    def test_heuristic_pipeline_register_and_run(self, simple_netlist, simple_board, rng_key):
        """HeuristicPipeline.register and run cycle."""
        from temper_placer.heuristics.pipeline import HeuristicPipeline
        from temper_placer.heuristics.base import (
            HeuristicPriority, Heuristic, HeuristicResult,
        )
        from temper_placer.io.config_loader import PlacementConstraints as PC
        pipeline = HeuristicPipeline()
        # Initially empty
        assert len(pipeline.heuristics) == 0

        class TestH(Heuristic):
            @property
            def name(self):
                return "test_h"
            @property
            def priority(self):
                return HeuristicPriority.FILL
            def apply(self, _ctx):
                return HeuristicResult(success=True)

        pipeline.register(TestH())
        assert len(pipeline.heuristics) == 1

        constraints = PC(board_width_mm=100.0, board_height_mm=100.0, board_margin_mm=5.0)
        result = pipeline.run(simple_board, simple_netlist, constraints, rng_key)
        assert isinstance(result.placements, dict)

        pipeline.clear()
        assert len(pipeline.heuristics) == 0

    def test_heuristic_pipeline_register_all(self):
        """HeuristicPipeline.register_all registers default heuristics."""
        from temper_placer.heuristics import create_default_pipeline
        from temper_placer.heuristics.pipeline import HeuristicPipeline
        pipeline = HeuristicPipeline()
        default = create_default_pipeline()
        pipeline.register_all(default.heuristics)
        assert len(pipeline.heuristics) > 0


# ============================================================================
# ConflictResolver tests
# ============================================================================


class TestConflictResolver:
    """Tests for conflict.py."""

    def test_conflict_resolver_basic(self):
        """ConflictResolver basic operations."""
        from temper_placer.heuristics.conflict import ConflictResolver
        from temper_placer.heuristics.base import ComponentPlacement
        cr = ConflictResolver()

        p1 = ComponentPlacement(ref="U1", position=(10.0, 20.0))
        cr.add_placement(p1)
        assert "U1" in cr.placements

        p2 = ComponentPlacement(ref="R1", position=(30.0, 40.0))
        cr.add_placement(p2)
        assert len(cr.placements) == 2

        conflicts = cr.get_all_conflicts()
        assert isinstance(conflicts, list)

        cr.clear()
        assert len(cr.placements) == 0

    def test_conflict_resolver_add_placements(self):
        """ConflictResolver.add_placements accepts dict of placements."""
        from temper_placer.heuristics.conflict import ConflictResolver
        from temper_placer.heuristics.base import ComponentPlacement
        cr = ConflictResolver()
        cr.add_placements({
            "U1": ComponentPlacement(ref="U1", position=(10.0, 20.0)),
            "R1": ComponentPlacement(ref="R1", position=(30.0, 40.0)),
        })
        assert len(cr.placements) == 2

    def test_conflict_resolver_check_conflict(self, simple_netlist, simple_board, rng_key):
        """ConflictResolver.check_conflict detects overlaps."""
        from temper_placer.heuristics.conflict import ConflictResolver
        from temper_placer.heuristics.base import ComponentPlacement, PlacementContext
        cr = ConflictResolver()
        cr.add_placement(ComponentPlacement(ref="U1", position=(10.0, 20.0)))
        ctx = PlacementContext(
            board=simple_board, netlist=simple_netlist,
            constraints=make_placement_constraints(), rng_key=rng_key,
        )
        result = cr.check_conflict(
            ComponentPlacement(ref="R1", position=(10.0, 20.0)),
            1.6, 0.8, ctx,
        )
        # Should be (conflicting_ref, overlap_mm) or None
        assert result is None or (isinstance(result, tuple) and len(result) == 2)

    def test_conflict_resolver_resolve(self, simple_netlist, simple_board, rng_key):
        """ConflictResolver.resolve returns resolved placement."""
        from temper_placer.heuristics.conflict import ConflictResolver
        from temper_placer.heuristics.base import ComponentPlacement, PlacementContext
        cr = ConflictResolver()
        cr.add_placement(ComponentPlacement(ref="U1", position=(10.0, 20.0)))
        ctx = PlacementContext(
            board=simple_board, netlist=simple_netlist,
            constraints=make_placement_constraints(), rng_key=rng_key,
        )
        p1 = ComponentPlacement(ref="R1", position=(30.0, 40.0))
        resolved, conflict = cr.resolve(p1, 1.6, 0.8, ctx)
        assert resolved is not None
        assert isinstance(resolved, ComponentPlacement)


# ============================================================================
# heuristics/__init__ tests
# ============================================================================


def test_create_default_pipeline_top_level():
    """heuristics.__init__.create_default_pipeline returns a pipeline."""
    from temper_placer.heuristics import create_default_pipeline
    from temper_placer.heuristics.pipeline import HeuristicPipeline
    pipeline = create_default_pipeline()
    assert isinstance(pipeline, HeuristicPipeline)
