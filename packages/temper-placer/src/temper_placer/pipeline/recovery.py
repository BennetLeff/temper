import time
import jax
import jax.numpy as jnp
from jax import Array
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist
from temper_placer.router_v6 import _AdapterRoutePath as RoutePath

def all_routed(results: dict[str, RoutePath]) -> bool:
    """Check if all nets were successfully routed."""
    return all(r.success for r in results.values())

def auto_layout_pcb_with_recovery(netlist: Netlist, board: Board):
    """Pipeline with automatic recovery strategies."""
    from temper_placer.pipeline.auto_layout import auto_layout_pcb
    
    # Try standard pipeline
    print("Attempting standard pipeline...")
    positions, results = auto_layout_pcb(netlist, board)
    
    if all_routed(results):
        print("Standard pipeline succeeded!")
        return positions, results
        
    # Recovery 1: Increase grid resolution
    print('Trying finer grid (cell_size=0.25mm)...')
    positions, results = auto_layout_pcb(netlist, board, cell_size_mm=0.25)
    
    if all_routed(results):
        print("Recovery 1 (finer grid) succeeded!")
        return positions, results
        
    # Recovery 2: Allow more layers (if possible)
    print('Trying more layers (num_layers=4)...')
    positions, results = auto_layout_pcb(netlist, board, num_layers=4)
    
    if all_routed(results):
        print("Recovery 2 (more layers) succeeded!")
        return positions, results
        
    # Recovery 3: Random restart with different initial placement
    print('Trying different initial placement (randomized)...')
    key = jax.random.PRNGKey(int(time.time()))
    random_pos = jnp.array([(board.width/2, board.height/2) for _ in netlist.components])
    random_pos += jax.random.normal(key, random_pos.shape) * 10.0
    
    positions, results = auto_layout_pcb(netlist, board, initial_positions=random_pos)
    
    if all_routed(results):
        print("Recovery 3 (random restart) succeeded!")
        return positions, results
        
    print('Board may be too constrained')
    return positions, results  # Signal failure with partial results
