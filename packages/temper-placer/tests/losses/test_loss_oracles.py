import jax
import jax.numpy as jnp
import pytest
from temper_placer.losses.grid import GridAlignmentLoss
from temper_placer.losses.aesthetic import WhitespaceLoss
from temper_placer.losses.thermal import ThermalLoss
from temper_placer.losses.grouping import GroupClusterLoss, ProximityLoss
from temper_placer.losses.base import LossContext, LoopConstraint

# =============================================================================
# temper-83gx.2: AestheticLoss: Grid alignment oracles
# =============================================================================

def test_grid_alignment_oracles():
    """Verify grid-based density calculation and alignment."""
    grid_size = 1.0
    loss_fn = GridAlignmentLoss(grid_size=grid_size)
    
    # 1. Component at grid center (integer coords) has minimal penalty
    pos_aligned = jnp.array([[10.0, 20.0]])
    rot = jnp.zeros((1, 4)).at[:, 0].set(1.0)
    res_aligned = loss_fn(pos_aligned, rot, None)
    assert float(res_aligned.value) == pytest.approx(0.0, abs=1e-6)
    
    # 2. Component at grid boundary (midway) has max penalty
    pos_misaligned = jnp.array([[10.5, 20.5]])
    res_misaligned = loss_fn(pos_misaligned, rot, None)
    # dist_x = 0.5, dist_y = 0.5. penalty = 0.5^2 + 0.5^2 = 0.5
    assert float(res_misaligned.value) == pytest.approx(0.5)
    
    # 3. Smooth transition / gradient
    grad_fn = jax.grad(lambda p: loss_fn(p, rot, None).value)
    # At (10.25, 20.0), dist_x = 0.25. penalty = x^2. grad = 2*x = 0.5
    g = grad_fn(jnp.array([[10.25, 20.0]]))
    assert float(g[0, 0]) == pytest.approx(0.5)

# =============================================================================
# temper-83gx.3: ThermalLoss: Edge distance oracles
# =============================================================================

def test_thermal_edge_distance_oracles(simple_netlist, simple_board):
    """Verify edge distance calculation for thermal components."""
    # simple_board is 100x100 at (0,0)
    from temper_placer.losses.types import ThermalConstraint
    thermal_constraints = [
        ThermalConstraint(component_ref="U1", edge="TOP", weight=1.0)
    ]
    context = LossContext.from_netlist_and_board(
        simple_netlist, 
        simple_board, 
        thermal_constraints=thermal_constraints
    )
    
    loss_fn = ThermalLoss()
    # U1 is 5x4 (WxH). Top edge is y=100.
    # Center at (50, 98) -> Top of component is 98 + 2 = 100.
    
    # 1. Component touching TOP edge has zero top-distance
    pos_touching = jnp.array([
        [50.0, 98.0], # U1 center
        [0.0, 0.0],
        [0.0, 0.0]
    ])
    rot = jnp.zeros((3, 4)).at[:, 0].set(1.0)
    res_touching = loss_fn(pos_touching, rot, context)
    # distance = 100 - 98 = 2.0. max_distance = 5.0. 
    # excess = 2.0 - 5.0 = -3.0. softplus(-3.0) approx 0.05.
    assert float(res_touching.value) < 0.1
    
    # 2. Distance increases as component moves away
    # Move U1 to y=50. dist = 50. excess = 45. penalty = 45^2 = 2025.
    pos_away = pos_touching.at[0, 1].set(50.0) 
    res_away = loss_fn(pos_away, rot, context)
    assert float(res_away.value) > 2000.0

# =============================================================================
# temper-83gx.4: GroupingLoss: Diameter calculation oracles
# =============================================================================

def test_grouping_diameter_oracles(simple_netlist, simple_board):
    """Verify pairwise diameter calculations for component groups."""
    from temper_placer.losses.grouping import GroupConfig, GroupClusterLoss, GroupSeparationLoss
    
    # Group U1 and R1
    g1_indices = jnp.array([0, 1], dtype=jnp.int32)
    g1 = GroupConfig(name="G1", component_indices=g1_indices, max_diameter_mm=10.0)
    loss_fn = GroupClusterLoss(groups=[g1])
    
    # 1. Single component group: zero penalty
    g_solo = GroupConfig(name="Solo", component_indices=jnp.array([0]), max_diameter_mm=5.0)
    solo_loss_fn = GroupClusterLoss(groups=[g_solo])
    pos = jnp.zeros((3, 2))
    rot = jnp.zeros((3, 4)).at[:, 0].set(1.0)
    res_solo = solo_loss_fn(pos, rot, None)
    assert float(res_solo.value) == 0.0
    
    # 2. Two components: diameter = distance between centers
    # pos0 = (0,0), pos1 = (6,8) -> dist = 10
    pos_two = jnp.array([
        [0.0, 0.0],
        [6.0, 8.0],
        [0.0, 0.0]
    ])
    res_two = loss_fn(pos_two, rot, None)
    # diameter = 10.0, max_diameter = 10.0 -> diameter_penalty = 0
    # Radius of gyration (RoG): centroid = (3, 4). 
    # distsq0 = 3^2+4^2=25. distsq1 = 3^2+4^2=25. mean distsq = 25.
    # target_rog_sq = (10/2)^2 = 25. rog_excess = 25 - 25 = 0.
    assert float(res_two.value) == pytest.approx(0.0, abs=1e-6)
    
    # 3. Diameter mode vs centroid mode
    # For separation loss
    g2 = GroupConfig(name="G2", component_indices=jnp.array([2]), max_diameter_mm=10.0)
    # G1: [0, 1] at (0,0) and (10,0) -> centroid (5,0)
    # G2: [2] at (20,0)
    pos_sep = jnp.array([
        [0.0, 0.0],
        [10.0, 0.0],
        [20.0, 0.0]
    ])
    
    # Centroid mode: dist = 20 - 5 = 15
    sep_loss_centroid = GroupSeparationLoss(separations=[(g1, g2, 18.0)], use_min_distance=False)
    res_c = sep_loss_centroid(pos_sep, rot, None)
    # dist = 15. deficit = 18 - 15 = 3. penalty = 3^2 = 9.
    assert float(res_c.value) == pytest.approx(9.0, abs=1e-3)
    
    # Min distance mode: dist = 10 - 10 = 10
    sep_loss_min = GroupSeparationLoss(separations=[(g1, g2, 18.0)], use_min_distance=True)
    res_m = sep_loss_min(pos_sep, rot, None)
    # dist = 10. deficit = 18 - 10 = 8. penalty = 8^2 = 64.
    assert float(res_m.value) == pytest.approx(64.0, abs=1e-3)

# =============================================================================
# temper-83gx.7: LoopAreaLoss: Collinear and degenerate cases
# =============================================================================

def test_loop_area_degenerate_cases():
    """Test edge cases: collinear pins, 2 pins, identical pins."""
    from temper_placer.losses.loop_area import compute_loop_area_penalty
    
    # 1. 3 collinear pins
    pins_collinear = jnp.array([[0, 0], [10, 0], [20, 0]], dtype=jnp.float32)
    penalty = compute_loop_area_penalty(pins_collinear, max_area=10.0)
    assert float(penalty) == pytest.approx(0.0, abs=1e-6)
    
    # 2. 2 pins
    pins_two = jnp.array([[0, 0], [10, 0]], dtype=jnp.float32)
    penalty = compute_loop_area_penalty(pins_two, max_area=10.0)
    assert float(penalty) == 0.0
    
    # 3. Identical pins
    pins_identical = jnp.array([[5, 5], [5, 5], [5, 5]], dtype=jnp.float32)
    penalty = compute_loop_area_penalty(pins_identical, max_area=10.0)
    assert float(penalty) == pytest.approx(0.0, abs=1e-6)

# =============================================================================
# temper-83gx.8: AestheticLoss: Empty and single-element groups
# =============================================================================

def test_aesthetic_empty_groups():
    """Test edge cases in alignment losses: empty group, single component."""
    from temper_placer.losses.aesthetic import AlignmentLoss
    
    pos = jnp.array([[10, 10], [20, 20]])
    rot = jnp.zeros((2, 4)).at[:, 0].set(1.0)
    
    # 1. Empty group (all -1 padding)
    empty_groups = jnp.array([[-1, -1]], dtype=jnp.int32)
    loss_fn = AlignmentLoss(prefix_groups=empty_groups)
    res = loss_fn(pos, rot, None)
    assert float(res.value) == 0.0
    
    # 2. Single component group
    solo_group = jnp.array([[0, -1]], dtype=jnp.int32)
    loss_fn = AlignmentLoss(prefix_groups=solo_group)
    res = loss_fn(pos, rot, None)
    assert float(res.value) == 0.0

# =============================================================================
# temper-83gx.9: ThermalLoss: Components at/outside board edges
# =============================================================================

def test_thermal_boundary_conditions(simple_netlist, simple_board):
    """Test thermal components at board edges and outside board."""
    from temper_placer.losses.types import ThermalConstraint
    
    # Board is 100x100 at (0,0)
    constraints = [ThermalConstraint(component_ref="U1", edge="TOP", weight=1.0)]
    context = LossContext.from_netlist_and_board(simple_netlist, simple_board, thermal_constraints=constraints)
    loss_fn = ThermalLoss()
    
    rot = jnp.zeros((3, 4)).at[:, 0].set(1.0)
    
    # 1. Component outside board (TOP)
    # y = 110. y_max = 100. dist = 100 - 110 = -10.
    pos_outside = jnp.array([[50.0, 110.0], [0, 0], [0, 0]])
    res = loss_fn(pos_outside, rot, context)
    # distance = -10. excess = -15. softplus(-15) approx 0.
    assert float(res.value) == pytest.approx(0.0, abs=1e-3)
    
    # 2. Component at board corner
    # Add BOTTOM and LEFT constraints
    constraints2 = [
        ThermalConstraint(component_ref="U1", edge="BOTTOM", weight=1.0),
        ThermalConstraint(component_ref="U1", edge="LEFT", weight=1.0)
    ]
    context2 = LossContext.from_netlist_and_board(simple_netlist, simple_board, thermal_constraints=constraints2)
    # Center at (0, 0)
    pos_corner = jnp.array([[0.0, 0.0], [0, 0], [0, 0]])
    res = loss_fn(pos_corner, rot, context2)
    # dist_bottom = 0, dist_left = 0. Both satisfy max_distance=5.0.
    assert float(res.value) == pytest.approx(0.0, abs=1e-3)

# =============================================================================
# temper-83gx.10: ThermalLoss: Identical component positions
# =============================================================================

def test_thermal_spread_identical_positions():
    """Test thermal spread when components are at identical position."""
    from temper_placer.losses.thermal import ThermalSpreadLoss
    
    # High power indices: 0 and 1
    loss_fn = ThermalSpreadLoss(high_power_indices=jnp.array([0, 1]))
    
    # Identical positions
    pos = jnp.array([[50.0, 50.0], [50.0, 50.0]])
    res = loss_fn(pos, None, None)
    
    # Should be finite penalty
    assert jnp.isfinite(res.value)
    assert float(res.value) > 0.0
    
    # Gradient should be finite and push apart
    grad_fn = jax.grad(lambda p: loss_fn(p, None, None).value)
    # If both at (50,50), they are too close. 
    # But current implementation uses diff = pos[:, None] - pos[None, :]
    # If they are IDENTICAL, diff is [0,0]. dist is sqrt(0+eps) = 1e-6.
    # softplus(min_sep - 1e-6) approx 15.
    # gradient should be defined.
    # Wait, grad of sqrt(x^2+y^2) at (0,0) is undefined.
    # We use 1e-12 epsilon in dist = sqrt(sum(diff^2) + 1e-12)
    g = grad_fn(pos)
    # Actually, with identical positions, the direction is arbitrary or zero?
    # No, it should be defined due to 1e-12.
    assert jnp.all(jnp.isfinite(g))
