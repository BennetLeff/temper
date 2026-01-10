import jax
import jax.numpy as jnp

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist
from temper_placer.losses.base import LossContext
from temper_placer.losses.overlap import OverlapLoss


def test_overlap_gradients():
    # 2 components, 10x10mm
    c1 = Component(ref="C1", footprint="", bounds=(10.0, 10.0), pins=[])
    c2 = Component(ref="C2", footprint="", bounds=(10.0, 10.0), pins=[])
    netlist = Netlist(components=[c1, c2], nets=[])
    board = Board(width=100, height=100)

    context = LossContext.from_netlist_and_board(netlist, board)
    loss_fn = OverlapLoss()

    # Perfectly overlapping at (50, 50)
    pos = jnp.array([[50.0, 50.0], [50.0, 50.0]])
    rot = jnp.zeros((2, 4))

    def loss(p):
        res = loss_fn(p, rot, context)
        return res.value

    grad = jax.grad(loss)(pos)
    print(f"Perfect Overlap Grad:\n{grad}")

    # Cluster of 5 components
    c = [Component(ref=f"C{i}", footprint="", bounds=(10.0, 10.0), pins=[]) for i in range(5)]
    netlist_c = Netlist(components=c, nets=[])
    context_c = LossContext.from_netlist_and_board(netlist_c, board)

    pos_c = jnp.zeros((5, 2)) + 50.0 # All at center

    def loss_c(p):
        res = loss_fn(p, jnp.zeros((5, 4)), context_c)
        return res.value

    grad_c = jax.grad(loss_c)(pos_c)
    print(f"Cluster (5) Overlap Grad:\n{grad_c}")

if __name__ == "__main__":
    test_overlap_gradients()
