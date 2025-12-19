import jax.numpy as jnp
from temper_placer.losses.base import LossContext
from temper_placer.losses.coil import CoilRequirementLoss, CoilRule, create_coil_loss


class MockNetlist:
    def __init__(self, components):
        self.components = components
        self.comp_map = {c.ref: i for i, c in enumerate(components)}

    def get_component_index(self, ref):
        return self.comp_map[ref]


class MockComponent:
    def __init__(self, ref):
        self.ref = ref


def test_coil_centering():
    """Test that coil is pulled to target position."""
    # Setup context
    components = [MockComponent("L1")]
    netlist = MockNetlist(components)
    context = LossContext(netlist=netlist, board=None, bounds=None, fixed_mask=None)

    # Setup loss
    rule = CoilRule(
        coil_ref="L1",
        target_position=(100.0, 100.0),
        weight_centering=1.0,
        weight_keepout=0.0,
        weight_symmetry=0.0,
    )
    loss_fn = CoilRequirementLoss([rule])

    # Case 1: At target (Loss = 0)
    positions = jnp.array([[100.0, 100.0]])
    res = loss_fn(positions, None, context)
    assert jnp.isclose(res.value, 0.0)

    # Case 2: Away from target (Loss = distance squared)
    positions = jnp.array([[110.0, 100.0]])  # 10mm away
    res = loss_fn(positions, None, context)
    # Loss = 1.0 * (10^2) = 100.0
    assert jnp.isclose(res.value, 100.0)


def test_coil_keepout():
    """Test that sensitive components are pushed away from coil."""
    # Setup context: L1 (Coil) at idx 0, U1 (Sensitive) at idx 1
    components = [MockComponent("L1"), MockComponent("U1")]
    netlist = MockNetlist(components)
    context = LossContext(netlist=netlist, board=None, bounds=None, fixed_mask=None)

    # Setup loss
    rule = CoilRule(
        coil_ref="L1",
        target_position=(0.0, 0.0),  # Irrelevant for this test if weight_centering=0
        keepout_radius=50.0,
        sensitive_refs=("U1",),
        weight_centering=0.0,
        weight_keepout=1.0,
        weight_symmetry=0.0,
    )
    loss_fn = CoilRequirementLoss([rule])

    # Coil at (0,0)

    # Case 1: U1 inside radius (dist=30, radius=50 -> violation=20 -> loss=400)
    positions = jnp.array(
        [
            [0.0, 0.0],  # L1
            [30.0, 0.0],  # U1
        ]
    )
    res = loss_fn(positions, None, context)
    assert jnp.isclose(res.value, 400.0)  # 20^2

    # Case 2: U1 outside radius (dist=60, radius=50 -> violation=0 -> loss=0)
    positions = jnp.array(
        [
            [0.0, 0.0],  # L1
            [60.0, 0.0],  # U1
        ]
    )
    res = loss_fn(positions, None, context)
    assert jnp.isclose(res.value, 0.0)


def test_coil_symmetry():
    """Test that tank capacitors are encouraged to be symmetric around coil."""
    # L1 (Coil) at 0, C1 at 1, C2 at 2
    components = [MockComponent("L1"), MockComponent("C1"), MockComponent("C2")]
    netlist = MockNetlist(components)
    context = LossContext(netlist=netlist, board=None, bounds=None, fixed_mask=None)

    # Setup loss
    rule = CoilRule(
        coil_ref="L1",
        target_position=(0.0, 0.0),
        tank_capacitor_refs=("C1", "C2"),
        weight_centering=0.0,
        weight_keepout=0.0,
        weight_symmetry=1.0,
    )
    loss_fn = CoilRequirementLoss([rule])

    # Coil at (0,0)

    # Case 1: Symmetric (C1 at -10, C2 at +10) -> Center of caps = 0 -> Loss 0
    positions = jnp.array(
        [
            [0.0, 0.0],  # L1
            [-10.0, 0.0],  # C1
            [10.0, 0.0],  # C2
        ]
    )
    res = loss_fn(positions, None, context)
    assert jnp.isclose(res.value, 0.0, atol=1e-5)

    # Case 2: Asymmetric (C1 at 0, C2 at +10) -> Center of caps = 5 -> Dist to coil = 5 -> Loss 25
    positions = jnp.array(
        [
            [0.0, 0.0],  # L1
            [0.0, 0.0],  # C1
            [10.0, 0.0],  # C2
        ]
    )
    res = loss_fn(positions, None, context)
    # Center of caps: (5, 0). Dist to L1(0,0) is 5. Loss = 25.
    assert jnp.isclose(res.value, 25.0, atol=1e-5)


def test_factory_function():
    """Test the create_coil_loss factory."""
    rule = CoilRule(coil_ref="L1", target_position=(0, 0))
    weighted_loss = create_coil_loss([rule], weight=2.5)

    assert isinstance(weighted_loss.loss_fn, CoilRequirementLoss)
    assert weighted_loss.weight == 2.5
    assert weighted_loss.normalize_by == 1.0
