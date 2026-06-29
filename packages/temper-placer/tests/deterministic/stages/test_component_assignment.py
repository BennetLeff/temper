"""
Unit tests for ComponentAssignmentStage.

Tests greedy wirelength-based assignment of components to slots.
"""

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.stages.component_assignment import ComponentAssignmentStage
from temper_placer.deterministic.stages.slot_generation import SlotGenerationStage
from temper_placer.deterministic.stages.zone_assignment import ZoneAssignmentStage
from temper_placer.deterministic.stages.zone_geometry import ZoneGeometryStage
from temper_placer.deterministic.state import BoardState


def test_all_components_assigned():
    """Every component should get a slot."""
    # Setup
    c1 = Component(ref="R1", footprint="0603", bounds=(1.6, 0.8),
                   pins=[Pin("1", "1", (0, 0), net="N1")], initial_position=(50, 50))
    c2 = Component(ref="R2", footprint="0603", bounds=(1.6, 0.8),
                   pins=[Pin("1", "1", (0, 0), net="N1")], initial_position=(60, 60))
    nets = [Net("N1", [("R1", "1"), ("R2", "1")], net_class="Signal")]
    netlist = Netlist(components=[c1, c2], nets=nets)

    board = Board(width=100, height=100)
    initial_state = BoardState(board=board, netlist=netlist)

    # Pipeline: zones -> assignment -> slots -> component assignment
    state = ZoneGeometryStage().run(initial_state)
    state = ZoneAssignmentStage().run(state)
    state = SlotGenerationStage(slot_spacing_mm=5.0).run(state)
    state = ComponentAssignmentStage().run(state)

    # Verify
    placements = dict(state.placements)
    assert "R1" in placements
    assert "R2" in placements
    assert placements["R1"] is not None
    assert placements["R2"] is not None


def test_no_overlapping_assignments():
    """Each slot should be used at most once."""
    # Setup: 3 components
    c1 = Component(ref="R1", footprint="0603", bounds=(1.6, 0.8),
                   pins=[Pin("1", "1", (0, 0), net="N1")], initial_position=(50, 50))
    c2 = Component(ref="R2", footprint="0603", bounds=(1.6, 0.8),
                   pins=[Pin("1", "1", (0, 0), net="N1")], initial_position=(60, 60))
    c3 = Component(ref="R3", footprint="0603", bounds=(1.6, 0.8),
                   pins=[Pin("1", "1", (0, 0), net="N2")], initial_position=(70, 70))
    nets = [
        Net("N1", [("R1", "1"), ("R2", "1")], net_class="Signal"),
        Net("N2", [("R3", "1")], net_class="Signal")
    ]
    netlist = Netlist(components=[c1, c2, c3], nets=nets)

    board = Board(width=100, height=100)
    initial_state = BoardState(board=board, netlist=netlist)

    # Pipeline
    state = ZoneGeometryStage().run(initial_state)
    state = ZoneAssignmentStage().run(state)
    state = SlotGenerationStage(slot_spacing_mm=5.0).run(state)
    state = ComponentAssignmentStage().run(state)

    # Verify no duplicates
    placements = dict(state.placements)
    positions = list(placements.values())
    assert len(positions) == len(set(positions)), "Some slots were assigned to multiple components"


def test_assignment_is_deterministic():
    """Multiple runs should produce the same placement."""
    c1 = Component(ref="R1", footprint="0603", bounds=(1.6, 0.8),
                   pins=[Pin("1", "1", (0, 0), net="N1")], initial_position=(50, 50))
    c2 = Component(ref="R2", footprint="0603", bounds=(1.6, 0.8),
                   pins=[Pin("1", "1", (0, 0), net="N1")], initial_position=(60, 60))
    nets = [Net("N1", [("R1", "1"), ("R2", "1")], net_class="Signal")]
    netlist = Netlist(components=[c1, c2], nets=nets)

    board = Board(width=100, height=100)

    # Run twice
    def run_pipeline():
        state = BoardState(board=board, netlist=netlist)
        state = ZoneGeometryStage().run(state)
        state = ZoneAssignmentStage().run(state)
        state = SlotGenerationStage(slot_spacing_mm=5.0).run(state)
        state = ComponentAssignmentStage().run(state)
        return dict(state.placements)

    placements1 = run_pipeline()
    placements2 = run_pipeline()

    assert placements1 == placements2
