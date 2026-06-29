import jax
import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.losses.base import LossContext
from temper_placer.losses.channel_capacity import ChannelCapacityLoss


def test_channel_capacity_basic():
    """Verify that ChannelCapacityLoss penalizes components that are too close."""
    # Create 4 components in a row
    # U1-U2 have a high-demand net (4 traces)
    # U3-U4 have a low-demand net (1 trace)

    components = [
        Component("U1", "R", (10.0, 10.0)),
        Component("U2", "R", (10.0, 10.0)),
        Component("U3", "R", (10.0, 10.0)),
        Component("U4", "R", (10.0, 10.0)),
    ]

    # Net with 4 pins on U1 and U2 to simulate high demand
    # Actually demand is measured by nets that have pins on BOTH components.
    # So 4 nets between U1 and U2 = 4 traces demand.
    nets = [
        Net("N1", [("U1", "1"), ("U2", "1")]),
        Net("N2", [("U1", "2"), ("U2", "2")]),
        Net("N3", [("U1", "3"), ("U2", "3")]),
        Net("N4", [("U1", "4"), ("U2", "4")]),
        Net("N5", [("U3", "1"), ("U4", "1")]),
    ]

    netlist = Netlist(components, nets)
    board = Board(width=100, height=100)
    ctx = LossContext.from_netlist_and_board(netlist, board)

    # trace_pitch = 0.4mm. margin = 0.5mm.
    # For demand=4, we need 4 * 0.4 = 1.6mm usable gap.
    # Total gap needed = 1.6 + 2 * 0.5 = 2.6mm.
    loss_fn = ChannelCapacityLoss(trace_width=0.2, trace_spacing=0.2, min_margin=0.5)

    # Case 1: U1/U2 are 10mm apart (plenty of space), U3/U4 are 10mm apart
    pos_far = jnp.array([
        [0.0, 0.0], [20.0, 0.0],  # Gap = 20 - 10 = 10mm
        [40.0, 0.0], [60.0, 0.0],  # Gap = 60 - 40 - 10 = 10mm
    ])
    loss_far = loss_fn(pos_far, jnp.zeros((4, 4)), ctx).value
    assert loss_far == 0.0

    # Case 2: U1/U2 are 11mm apart (centers) -> Gap = 11 - 10 = 1mm
    # Required gap for 4 traces = 2.6mm. 1mm < 2.6mm -> Penalty!
    pos_near = jnp.array([
        [0.0, 0.0], [11.0, 0.0],  # Gap = 1mm
        [40.0, 0.0], [60.0, 0.0],
    ])
    result_near = loss_fn(pos_near, jnp.zeros((4, 4)), ctx)
    loss_near = result_near.value
    assert loss_near > 0.0
    assert result_near.breakdown["max_shortage"] > 0

    # Case 3: U3/U4 are 11mm apart (centers) -> Gap = 1mm
    # Required gap for 1 trace = (1 * 0.4) + 1.0 = 1.4mm.
    # 1mm < 1.4mm -> Penalty, but smaller than U1/U2 penalty
    pos_near_low = jnp.array([
        [0.0, 0.0], [20.0, 0.0],
        [40.0, 0.0], [51.0, 0.0], # Gap = 1mm
    ])
    loss_near_low = loss_fn(pos_near_low, jnp.zeros((4, 4)), ctx).value
    assert loss_near_low > 0.0
    assert loss_near > loss_near_low

    print(f"Far: {loss_far:.4f}, Near (4 nets): {loss_near:.4f}, Near (1 net): {loss_near_low:.4f}")


def test_channel_capacity_gradients():
    """Verify that gradients push components apart."""
    c1 = Component("U1", "R", (10.0, 10.0))
    c2 = Component("U2", "R", (10.0, 10.0))
    nets = [Net(f"N{i}", [("U1", str(i)), ("U2", str(i))]) for i in range(5)]

    netlist = Netlist([c1, c2], nets)
    board = Board(width=100, height=100)
    ctx = LossContext.from_netlist_and_board(netlist, board)

    loss_fn = ChannelCapacityLoss()

    # Components are too close: (0,0) and (11, 0) -> Gap = 1mm
    pos = jnp.array([[0.0, 0.0], [11.0, 0.0]])

    def loss_val(p):
        return loss_fn(p, jnp.zeros((2, 4)), ctx).value

    grad = jax.grad(loss_val)(pos)

    # grad[0, 0] should be positive (increasing pos[0,0] decreases gap, increases loss)
    # grad[1, 0] should be negative (increasing pos[1,0] increases gap, decreases loss)
    assert grad[0, 0] > 0
    assert grad[1, 0] < 0
    assert jnp.abs(grad[0, 1]) < 1e-5  # No vertical force needed

if __name__ == "__main__":
    pytest.main([__file__])
