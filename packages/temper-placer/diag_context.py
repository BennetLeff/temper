from temper_placer.losses.base import LossContext
from temper_placer.core.netlist import Netlist
from temper_placer.core.board import Board
import jax.numpy as jnp

netlist = Netlist([], [])
board = Board(100, 100)
context = LossContext.from_netlist_and_board(netlist, board)

print(f"Context type: {type(context)}")
print(f"Has domain_bounds: {hasattr(context, 'domain_bounds')}")
try:
    print(f"domain_bounds: {context.domain_bounds}")
except AttributeError as e:
    print(f"Error accessing domain_bounds: {e}")

from temper_placer.losses.types import LossContext as BaseLossContext
print(f"BaseLossContext has domain_bounds: {hasattr(BaseLossContext, 'domain_bounds')}")
