
import jax.numpy as jnp
import pytest
from temper_placer.losses.aesthetic import MirrorSymmetryLoss
from temper_placer.losses.base import LossResult

def test_mirror_symmetry_loss_x_axis():
    """Test mirror symmetry about vertical axis (mirroring X)."""
    # Pairs: (0, 1) should be symmetric about x=50
    pairs = jnp.array([[0, 1]])
    
    # Case 1: Perfectly symmetric
    # 40 reflected about 50 is 60.
    pos_sym = jnp.array([
        [40.0, 10.0], # Comp 0
        [60.0, 10.0]  # Comp 1
    ])
    
    loss_fn = MirrorSymmetryLoss(pairs=pairs, axis=0, center=50.0)
    res_sym = loss_fn(pos_sym, None, None)
    assert float(res_sym.value) < 1e-4
    
    # Case 2: Asymmetric
    pos_asym = jnp.array([
        [40.0, 10.0],
        [65.0, 10.0] # Should be 60
    ])
    res_asym = loss_fn(pos_asym, None, None)
    # diff_x = 65 - 60 = 5. penalty = 5^2 = 25.
    assert float(res_asym.value) == pytest.approx(25.0)

def test_mirror_symmetry_loss_y_axis():
    """Test mirror symmetry about horizontal axis (mirroring Y)."""
    # Pairs: (0, 1) about y=20
    pairs = jnp.array([[0, 1]])
    
    pos_sym = jnp.array([
        [10.0, 15.0],
        [10.0, 25.0] # 15 mirrored about 20 is 25
    ])
    
    loss_fn = MirrorSymmetryLoss(pairs=pairs, axis=1, center=20.0)
    res_sym = loss_fn(pos_sym, None, None)
    assert float(res_sym.value) < 1e-4
    
    pos_asym = jnp.array([
        [10.0, 15.0],
        [10.0, 30.0] # Should be 25
    ])
    res_asym = loss_fn(pos_asym, None, None)
    assert float(res_asym.value) == pytest.approx(25.0)
