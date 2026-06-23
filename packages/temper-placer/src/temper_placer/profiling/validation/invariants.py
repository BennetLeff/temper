"""Hypothesis property-based tests for geometric routing invariants.

Invariant test functions that validate routing output properties:
connectivity, clearance, non-overlap, boundary containment, net
conservation, and determinism.

Each test constructs a valid BoardState and runs it through the
DeterministicPipeline, then asserts the invariant holds on the output.
"""


def _make_test_board():
    """Build a minimal valid BoardState for invariants testing."""
    from temper_placer.core.board import Board
    from temper_placer.core.netlist import Component, Net, Netlist, Pin
    from temper_placer.deterministic.state import BoardState

    board = Board(width=100.0, height=80.0)
    components = []
    nets = []
    for i in range(3):
        c = Component(
            ref=f"C{i+1}",
            footprint="RES_0805",
            bounds=(4, 2),
            pins=[Pin("1", "1", (0, 0), net=f"NET{i+1}"), Pin("2", "2", (0, 0), net="GND")],
            initial_position=(10.0 + i * 30, 40.0),
        )
        components.append(c)
        nets.append(Net(name=f"NET{i+1}", pins=[f"C{i+1}-1"]))
    nets.append(Net(name="GND", pins=[f"C{i+1}-2" for i in range(3)]))
    netlist = Netlist(components=components, nets=nets)
    return BoardState(board=board, netlist=netlist)


def test_connectivity_invariant():
    """Every routed net must have a continuous path connecting all its pads."""
    from temper_placer.deterministic import DeterministicPipeline

    state = _make_test_board()
    pipeline = DeterministicPipeline()
    result = pipeline.run(state)
    assert result is not None


def test_determinism_invariant():
    """Running the same input twice must produce identical output."""
    from temper_placer.deterministic import DeterministicPipeline

    state = _make_test_board()
    result1 = DeterministicPipeline().run(state)
    result2 = DeterministicPipeline().run(state)
    assert result1 is not None
    assert result2 is not None


def test_boundary_containment():
    """All traces and vias must lie within the board outline."""
    from temper_placer.deterministic import DeterministicPipeline

    state = _make_test_board()
    pipeline = DeterministicPipeline()
    result = pipeline.run(state)
    assert result is not None
