
import jax.numpy as jnp
import numpy as np
from temper_placer.optimizer.initialization import SpectralInitializer
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.board import Board
from temper_placer.core.state import PlacementState

def create_chain_netlist(n=100):
    components = []
    for i in range(n):
        components.append(Component(
            ref=f"R{i}",
            footprint="0805",
            bounds=(2, 1),
            pins=[
                Pin("1", "1", (0, 0), net=f"N{i}"),
                Pin("2", "2", (0, 0), net=f"N{i+1}")
            ]
        ))
    
    nets = []
    for i in range(n + 1):
        pins = []
        if i > 0:
            pins.append((f"R{i-1}", "2"))
        if i < n:
            pins.append((f"R{i}", "1"))
        nets.append(Net(name=f"N{i}", pins=pins))
        
    return Netlist(components=components, nets=nets)

def calculate_wirelength(positions, netlist):
    # Simplified HPWL calculation
    total_wl = 0
    ref_to_idx = {c.ref: i for i, c in enumerate(netlist.components)}
    for net in netlist.nets:
        if len(net.pins) < 2:
            continue
        xs = []
        ys = []
        for ref, _ in net.pins:
            idx = ref_to_idx[ref]
            xs.append(positions[idx, 0])
            ys.append(positions[idx, 1])
        total_wl += (max(xs) - min(xs)) + (max(ys) - min(ys))
    return total_wl

def main():
    n = 100
    netlist = create_chain_netlist(n)
    board = Board(width=100, height=100)
    
    # Spectral
    initializer = SpectralInitializer()
    pos_spectral = initializer.initialize(netlist, board)
    wl_spectral = calculate_wirelength(pos_spectral, netlist)
    
    # Random
    import jax
    key = jax.random.PRNGKey(42)
    state_random = PlacementState.random_init(n, board.width, board.height, key)
    pos_random = state_random.positions
    wl_random = calculate_wirelength(pos_random, netlist)
    
    print(f"Spectral Wirelength: {wl_spectral:.2f}")
    print(f"Random Wirelength: {wl_random:.2f}")
    print(f"Ratio: {wl_spectral / wl_random:.4f}")
    
    if wl_spectral < 0.5 * wl_random:
        print("SUCCESS: Spectral wirelength is less than 50% of random.")
    else:
        print("FAILURE: Spectral wirelength is NOT less than 50% of random.")

if __name__ == "__main__":
    main()
