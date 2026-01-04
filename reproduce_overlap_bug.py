
import jax
import jax.numpy as jnp
from dataclasses import dataclass, field
from typing import Any, List

from temper_placer.losses.overlap import OverlapLoss
from temper_placer.losses.base import LossContext, LossResult, LossFunction, WeightedLoss, CompositeLoss
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component

def main():
    print("--- Setting up GradNorm Reproduction ---")
    
    # 1. Setup Data
    board = Board(width=100.0, height=100.0)
    # Create enough components to potentially trigger chunking if we wanted, 
    # but let's start with a small number to mimic the failure case cleanly first.
    # The error usually happens regardless of N if it's a tracer issue.
    n_components = 5
    components = [Component(ref=f"C{i}", footprint="R_0603", bounds=(1.6, 0.8)) for i in range(n_components)]
    netlist = Netlist(components=components, nets=[])
    
    context = LossContext.from_netlist_and_board(netlist=netlist, board=board)
    
    positions = jnp.zeros((n_components, 2))
    rotations = jnp.zeros((n_components, 4)).at[:, 0].set(1.0)

    # 2. Setup Composite Loss
    # We need at least 2 losses to make switch/GradNorm meaningful
    overlap_loss = OverlapLoss(margin=0.1)
    
    # Create a dummy second loss
    class DummyLoss(LossFunction):
        def __call__(self, positions, rotations, context, epoch=0, total_epochs=1, **kwargs):
            return LossResult(value=jnp.sum(positions**2), breakdown={})
        @property
        def name(self): return "dummy"

    dummy_loss = DummyLoss()
    
    composite = CompositeLoss([
        WeightedLoss(overlap_loss, weight=1.0),
        WeightedLoss(dummy_loss, weight=1.0)
    ])
    
    print(f"Composite loss created with {len(composite.losses)} losses.")

    # 3. Define GradNorm Logic (Mirroring gradnorm.py)
    # This is the critical part: vmap over losses with switch
    
    n_losses = len(composite.losses)

    def get_individual_loss(i, pos, rot):
        """Get loss value for i-th term using jax.lax.switch for tracing."""
        # Using the exact pattern from gradnorm.py
        def make_loss_thunk(wloss_idx):
            def thunk(p_r):
                pos_in, rot_in = p_r
                # Direct access to the loss function from the closure
                wloss = composite.losses[wloss_idx]
                # In gradnorm.py: res = wloss.loss_fn(pos_in, rot_in, loss_context, epoch, total_epochs)
                # We hardcode epoch/total_epochs for reproduction
                res = wloss.loss_fn(pos_in, rot_in, context, 0, 100)
                # In gradnorm.py: return res.value / wloss.get_normalizer(loss_context)
                return res.value 
            return thunk

        thunks = [make_loss_thunk(idx) for idx in range(n_losses)]
        # This switch is where dynamic shaping issues often explode
        return jax.lax.switch(i, thunks, (pos, rot))

    def get_grad_norm(i):
        """Compute gradient norm for i-th loss term."""
        # jax.grad w.r.t positions (arg 1)
        grad_fn = jax.grad(get_individual_loss, argnums=1)
        g = grad_fn(i, positions, rotations)
        return jnp.linalg.norm(g)

    # 4. JIT Compilation
    print("Compiling GradNorm step...")
    @jax.jit
    def gradnorm_step():
        # vmap over the loss indices
        return jax.vmap(get_grad_norm)(jnp.arange(n_losses))

    # 5. Execute
    try:
        print("Executing...")
        norms = gradnorm_step()
        print(f"Success! Norms: {norms}")
    except Exception as e:
        print("\n!!! REPRODUCTION SUCCESS (FAILURE CAUGHT) !!!")
        print(f"Error type: {type(e)}")
        print(f"Error message: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
