import jax.numpy as jnp
import pytest
from temper_placer.losses.net_class import (
    NetClassRule,
    NetClassSeparationLoss,
    ResolvedNetClassSeparationLoss,
    create_net_class_loss,
)
from temper_placer.losses.base import LossContext


class MockComponent:
    def __init__(self, ref):
        self.ref = ref


class MockNetlist:
    def __init__(self, components):
        self.components = components


def test_net_class_separation_loss_basic():
    # Setup: 2 components, one class A, one class B
    # Rule: A and B must be 10.0mm apart

    rules_data = [
        (
            jnp.array([0], dtype=jnp.int32),  # Index of comp A
            jnp.array([1], dtype=jnp.int32),  # Index of comp B
            10.0,  # min_sep
            1.0,  # weight
        )
    ]

    loss_fn = ResolvedNetClassSeparationLoss(rules_data)

    # Case 1: Far apart (20mm)
    positions = jnp.array([[0.0, 0.0], [20.0, 0.0]])
    rotations = jnp.zeros((2,))
    # Mock context with required fields
    context = LossContext(
        netlist=MockNetlist([]),
        board=None,
        bounds=jnp.zeros((2, 2)),
        fixed_mask=jnp.zeros((2,), dtype=bool),
    )

    result = loss_fn(positions, rotations, context)
    assert result.value == 0.0

    # Case 2: Too close (5mm)
    # Violation = 10 - 5 = 5
    # Penalty = 5^2 = 25
    positions_close = jnp.array([[0.0, 0.0], [5.0, 0.0]])

    result_close = loss_fn(positions_close, rotations, context)
    assert jnp.isclose(result_close.value, 25.0)


def test_net_class_factory():
    # Setup netlist with 4 components
    # U1 (Analog), U2 (Digital), R1 (Analog), R2 (Digital)
    netlist = MockNetlist(
        [MockComponent("U1"), MockComponent("U2"), MockComponent("R1"), MockComponent("R2")]
    )
    # Add n_components attribute usually present in real Netlist
    netlist.n_components = 4

    comp_classes = {"U1": "Analog", "R1": "Analog", "U2": "Digital", "R2": "Digital"}

    rules = [NetClassRule(class_a="Analog", class_b="Digital", min_separation_mm=10.0, weight=1.0)]

    loss_fn = create_net_class_loss(netlist, rules, comp_classes)

    # Verify internal structure
    # Should have 1 rule tuple
    assert len(loss_fn.rules_data) == 1

    indices_a, indices_b, min_sep, weight = loss_fn.rules_data[0]

    # Indices for Analog: U1(0), R1(2)
    # Indices for Digital: U2(1), R2(3)
    # Note: Sets are unordered, so check membership

    assert set(indices_a.tolist()) == {0, 2}
    assert set(indices_b.tolist()) == {1, 3}
    assert min_sep == 10.0

    # Test execution
    # Place U1 (0,0) and U2 (5,0) -> Violation (Analog vs Digital)
    # Place R1 (0,100) and R2 (0,120) -> Safe (Analog vs Digital)
    # U1 and R1 are both Analog -> No check

    positions = jnp.array(
        [
            [0.0, 0.0],  # U1 (A)
            [5.0, 0.0],  # U2 (D) - 5mm dist, violation 5
            [0.0, 100.0],  # R1 (A)
            [0.0, 120.0],  # R2 (D) - 20mm dist, safe
        ]
    )
    rotations = jnp.zeros((4,))
    context = LossContext(
        netlist=netlist,
        board=None,
        bounds=jnp.zeros((4, 2)),
        fixed_mask=jnp.zeros((4,), dtype=bool),
    )

    result = loss_fn(positions, rotations, context)

    # Expected: (10 - 5)^2 + 0 = 25.0
    assert jnp.isclose(result.value, 25.0)


def test_multiple_rules():
    # Analog, Digital, Power
    # A-D: 10mm
    # A-P: 20mm

    rules = [NetClassRule("Analog", "Digital", 10.0), NetClassRule("Analog", "Power", 20.0)]

    # U1(A), U2(D), U3(P)
    loss_fn = ResolvedNetClassSeparationLoss(
        [(jnp.array([0]), jnp.array([1]), 10.0, 1.0), (jnp.array([0]), jnp.array([2]), 20.0, 1.0)]
    )

    positions = jnp.array(
        [
            [0.0, 0.0],  # U1 (A)
            [5.0, 0.0],  # U2 (D) -> Dist 5, Req 10 -> Viol 5 -> Pen 25
            [10.0, 0.0],  # U3 (P) -> Dist to U1 is 10, Req 20 -> Viol 10 -> Pen 100
        ]
    )

    rotations = jnp.zeros((3,))
    context = LossContext(
        netlist=MockNetlist([]),
        board=None,
        bounds=jnp.zeros((3, 2)),
        fixed_mask=jnp.zeros((3,), dtype=bool),
    )

    result = loss_fn(positions, rotations, context)

    assert jnp.isclose(result.value, 125.0)
