import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board, Layer, LayerStackup
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.base import LossContext
from temper_placer.losses.routability import RoutabilityLoss
from temper_placer.losses.wirelength import WirelengthLoss


def setup_simple_board(layers=2):
    if layers == 2:
        stackup = LayerStackup(layers=[
            Layer("F.Cu", "signal", is_routable=True),
            Layer("B.Cu", "signal", is_routable=True),
        ])
    elif layers == 4:
        stackup = LayerStackup(layers=[
            Layer("F.Cu", "signal", is_routable=True),
            Layer("In1.Cu", "plane", is_routable=False),
            Layer("In2.Cu", "plane", is_routable=False),
            Layer("B.Cu", "signal", is_routable=True),
        ])
    else:
        # Default 4-layer with 2 signal layers
        stackup = LayerStackup.default_4layer()

    board = Board(width=100, height=100)
    board.layer_stackup = stackup

    p1 = Pin("1", "1", (0, 0), "N1")
    p2 = Pin("1", "1", (0, 0), "N1")

    c1 = Component("Q1", "footprint", (10, 10), [p1])
    c2 = Component("Q2", "footprint", (10, 10), [p2])

    net = Net("N1", [("Q1", "1"), ("Q2", "1")])
    netlist = Netlist([c1, c2], [net])

    return board, netlist

def test_rhwl_scaling():
    """Verify RHWL scales correctly with routable layer count."""
    # 2 signal layers
    board2, netlist = setup_simple_board(layers=2)
    ctx2 = LossContext.from_netlist_and_board(netlist, board2)

    # 1 signal layer board
    stackup1 = LayerStackup(layers=[
        Layer("F.Cu", "signal", is_routable=True),
        Layer("GND", "plane", is_routable=False),
    ])
    board1 = Board(width=100, height=100)
    board1.layer_stackup = stackup1
    ctx1 = LossContext.from_netlist_and_board(netlist, board1)

    positions = jnp.array([[10, 10], [20, 10]], dtype=jnp.float32)
    rotations = jnp.zeros((2, 4))

    loss = WirelengthLoss(alpha=100.0) # Sharp HPWL

    res1 = loss(positions, rotations, ctx1)
    res2 = loss(positions, rotations, ctx2)

    # HPWL should be ~10mm.
    # res1 should be ~10 / 1 = 10
    # res2 should be ~10 / 2 = 5

    assert res1.value > 0
    assert res2.value > 0
    assert jnp.allclose(res1.value, res2.value * 2, rtol=1e-2)

def test_routability_capacity():
    """Verify RoutabilityLoss uses LayerStackup capacity."""
    board2, netlist = setup_simple_board(layers=2)
    ctx2 = LossContext.from_netlist_and_board(netlist, board2)

    # Increase density by adding more nets or reducing board size
    # For simplicity, we just check if it runs and uses capacity

    positions = jnp.array([[10, 10], [15, 10]], dtype=jnp.float32)
    rotations = jnp.zeros((2, 4))

    loss = RoutabilityLoss(grid_shape=(2, 2))
    res = loss(positions, rotations, ctx2)

    assert "cell_capacity" in res.breakdown
    assert res.breakdown["cell_capacity"] > 0
    # Tracks per cell for 2 layers should be double 1 layer

    stackup1 = LayerStackup(layers=[Layer("F.Cu", "signal", is_routable=True)])
    board1 = Board(width=100, height=100, layer_stackup=stackup1)
    ctx1 = LossContext.from_netlist_and_board(netlist, board1)

    res1 = loss(positions, rotations, ctx1)
    assert jnp.allclose(res.breakdown["cell_capacity"], res1.breakdown["cell_capacity"] * 2)

if __name__ == "__main__":
    pytest.main([__file__])
