from temper_placer.core.netlist import Netlist, Component, Net
from temper_placer.extraction.hypergraph_factory import netlist_to_hypergraph
from temper_placer.algo.coarsening import coarsen_hypergraph
from temper_placer.algo.spectral import spectral_layout
import jax.numpy as jnp

def test_full_pipeline_flow():
    """
    Test the full Netlist -> Hypergraph -> Coarsen -> Spectral flow.
    """
    # 1. Create a chain of 4 components: U0 -- U1 -- U2 -- U3
    components = [
        Component(ref=f"U{i}", footprint="R", bounds=(1,1))
        for i in range(4)
    ]
    
    nets = [
        Net("n0", [("U0", "1"), ("U1", "1")]),
        Net("n1", [("U1", "2"), ("U2", "2")]),
        Net("n2", [("U2", "3"), ("U3", "3")])
    ]
    
    netlist = Netlist(components=components, nets=nets)
    
    # 2. Build Hypergraph
    hg = netlist_to_hypergraph(netlist)
    assert hg.n_nodes == 4
    
    # 3. Coarsen (Ratio 0.5 -> Should reduce to ~2 nodes)
    # U0-U1 and U2-U3 should likely merge
    coarse_hg, projection = coarsen_hypergraph(hg, reduction_ratio=0.5)
    
    assert coarse_hg.n_nodes == 2
    assert projection.shape == (4, 2)
    
    # 4. Spectral Layout
    positions = spectral_layout(coarse_hg, dim=2)
    assert positions.shape == (2, 2)
    
    # 5. Projection back
    fine_positions = projection @ positions
    assert fine_positions.shape == (4, 2)
    
    # Verify that U0 and U1 (merged) have same position
    # The projection matrix P[0] and P[1] should point to same col
    # So fine_positions[0] should equal fine_positions[1]
    # (Assuming simple 1.0 weights in projection)
    
    assert jnp.allclose(fine_positions[0], fine_positions[1])
    assert jnp.allclose(fine_positions[2], fine_positions[3])
