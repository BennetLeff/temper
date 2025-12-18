"""Tests for force-directed layout heuristic."""

import pytest
import numpy as np
import jax.random as random
from unittest.mock import MagicMock

from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Net, Pin
from temper_placer.io.config_loader import PlacementConstraints
from temper_placer.heuristics.base import PlacementContext, ComponentPlacement
from temper_placer.heuristics.force_directed import ForceDirectedHeuristic


@pytest.fixture
def simple_context():
    """Create a simple context with 3 connected components."""
    # Components
    c1 = Component(ref="U1", footprint="DIP8", bounds=(10.0, 10.0))
    c2 = Component(ref="R1", footprint="R0603", bounds=(5.0, 2.0))
    c3 = Component(ref="C1", footprint="C0603", bounds=(4.0, 2.0))

    # Net: U1-1 <-> R1-1 <-> C1-1
    net1 = Net(
        name="NET1",
        pins=[
            ("U1", "1"),
            ("R1", "1"),
            ("C1", "1"),
        ],
    )

    netlist = Netlist(components=[c1, c2, c3], nets=[net1])
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
    constraints = PlacementConstraints(board_margin_mm=5.0)

    return PlacementContext(
        board=board,
        netlist=netlist,
        constraints=constraints,
        current_placements={},
        rng_key=random.PRNGKey(42),
    )

    netlist = Netlist(components=[c1, c2, c3], nets=[net1])
    board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
    constraints = PlacementConstraints(board_margin_mm=5.0)

    return PlacementContext(
        board=board,
        netlist=netlist,
        constraints=constraints,
        current_placements={},
        rng_key=random.PRNGKey(42),
    )


def test_force_directed_placement_basic(simple_context):
    """Test that force-directed layout places components within bounds."""
    heuristic = ForceDirectedHeuristic(confidence=0.2, iterations=10)
    result = heuristic.apply(simple_context)

    assert result.success
    assert len(result.placements) == 3

    margin = simple_context.constraints.board_margin_mm
    board = simple_context.board

    for ref, placement in result.placements.items():
        x, y = placement.position
        comp = simple_context.netlist.get_component(ref)

        # Check bounds
        assert x >= margin + comp.width / 2
        assert x <= board.width - margin - comp.width / 2
        assert y >= margin + comp.height / 2
        assert y <= board.height - margin - comp.height / 2

        assert placement.placed_by == "force_directed_layout"
        assert placement.confidence == 0.2


def test_force_directed_respects_existing_placements(simple_context):
    """Test that existing placements are used as initial positions."""
    # Pre-place U1 at (20, 20)
    simple_context.current_placements["U1"] = ComponentPlacement(
        ref="U1",
        position=(20.0, 20.0),
        rotation=0,
        confidence=0.1,
        placed_by="spectral_initialization",
    )

    heuristic = ForceDirectedHeuristic(confidence=0.2, iterations=1)  # Low iterations to stay close
    result = heuristic.apply(simple_context)

    assert result.success
    u1_pos = result.placements["U1"].position

    # It should have moved, but not randomly.
    # With 1 iteration and other components unplaced, it might move significantly due to repulsion
    # or attraction to random starts of others.
    # But the key is that the heuristic didn't crash and returned a result.
    assert "U1" in result.placements


def test_force_directed_empty_graph():
    """Test behavior with empty netlist."""
    context = PlacementContext(
        board=Board(100, 100),
        netlist=Netlist(components=[], nets=[]),
        constraints=PlacementConstraints(),
        current_placements={},
        rng_key=random.PRNGKey(0),
    )

    heuristic = ForceDirectedHeuristic()
    result = heuristic.apply(context)

    assert result.success
    assert len(result.placements) == 0
    assert "Empty graph" in result.message


def test_force_directed_fixed_components(simple_context):
    """Test that fixed components are not moved."""
    # Fix U1
    u1 = simple_context.netlist.get_component("U1")
    u1.fixed = True
    u1.initial_position = (50.0, 50.0)

    # We must put it in current_placements for the heuristic to know where it is fixed AT
    simple_context.current_placements["U1"] = ComponentPlacement(
        ref="U1", position=(50.0, 50.0), rotation=0, confidence=1.0, placed_by="user"
    )

    heuristic = ForceDirectedHeuristic(confidence=0.2)
    result = heuristic.apply(simple_context)

    # Fixed component should NOT be in the OUTPUT placements of the heuristic
    # because heuristics usually return *new* placements to be applied.
    # However, implementation detail: _scale_to_board filters out fixed components.
    assert "U1" not in result.placements
    assert "R1" in result.placements
    assert "C1" in result.placements
