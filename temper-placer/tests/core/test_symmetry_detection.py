
import pytest
import jax.numpy as jnp
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.losses.grouping import SymmetryLoss, find_isomorphic_pairs

def test_symmetry_detection_rc_channels():
    """Verify that identical RC channels are detected as isomorphic."""
    # 2 identical RC channels
    components = [
        Component(ref="R1", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="C1", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="R2", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="C2", footprint="0603", bounds=(1.6, 0.8)),
    ]
    nets = [
        Net(name="N1", pins=[("R1", "1"), ("C1", "1")]),
        Net(name="N2", pins=[("R2", "1"), ("C2", "1")]),
    ]
    netlist = Netlist(components=components, nets=nets)
    
    # 1. Component grouping
    groups = netlist.find_isomorphic_groups()
    # Expect 2 groups: [R1, R2] and [C1, C2]
    assert len(groups) == 2
    for g in groups:
        assert len(g) == 2
        
    # 2. Pair matching
    pairs = find_isomorphic_pairs(netlist)
    # Should find 1 set of isomorphic edges: (R1-C1) and (R2-C2)
    assert len(pairs) == 1
    p = pairs[0]
    # Check that it paired an R-C with another R-C
    # p = (a1, b1, a2, b2)
    refs = [netlist.components[i].ref for i in p]
    assert "R1" in refs[:2] and "C1" in refs[:2]
    assert "R2" in refs[2:] and "C2" in refs[2:]

def test_symmetry_loss_values():
    """Verify SymmetryLoss calculation."""
    # Pairs: (0,1) and (2,3)
    pairs = [(0, 1, 2, 3)]
    loss_fn = SymmetryLoss(pairs)
    
    # 1. Perfectly symmetric
    # Vector (0->1) = [10, 0]
    # Vector (2->3) = [10, 0]
    pos_sym = jnp.array([
        [0.0, 0.0], [10.0, 0.0],
        [0.0, 50.0], [10.0, 50.0]
    ])
    res_sym = loss_fn(pos_sym, None, None)
    assert float(res_sym.value) == pytest.approx(0.0)
    
    # 2. Asymmetric
    # Vector (0->1) = [10, 0]
    # Vector (2->3) = [5, 5]
    pos_asym = jnp.array([
        [0.0, 0.0], [10.0, 0.0],
        [0.0, 50.0], [5.0, 55.0]
    ])
    res_asym = loss_fn(pos_asym, None, None)
    # diff = [5, -5], dist_sq = 25 + 25 = 50
    assert float(res_asym.value) == pytest.approx(50.0)
