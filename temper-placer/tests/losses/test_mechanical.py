from typing import List, Tuple, Any
from dataclasses import dataclass, field
import jax.numpy as jnp
from temper_placer.losses.base import LossFunction, LossResult, LossContext, MountingRule
from temper_placer.core.board import Board
import pytest


@dataclass
class MockComponent:
    ref: str


@dataclass
class MockBoard:
    width: float = 100.0
    height: float = 80.0


class MockNetlist:
    def __init__(self, components):
        self.components = components
        self.n_components = len(components)

    def get_component_index(self, ref):
        for i, c in enumerate(self.components):
            if c.ref == ref:
                return i
        raise KeyError(ref)


# Import real classes if possible
try:
    from temper_placer.losses.mechanical import (
        MechanicalMountingLoss,
        create_mechanical_loss,
        ResolvedMountingRule,
    )
except ImportError:
    pass


def test_mechanical_loss_initialization():
    netlist = MockNetlist(
        [
            MockComponent("J1"),
            MockComponent("L1"),
            MockComponent("LED1"),
        ]
    )

    rules = [
        MountingRule(
            component_idx=0,  # J1
            rule_type="edge",
            edge="LEFT",
            max_distance_mm=2.0,
        ),
        MountingRule(
            component_idx=1,  # L1
            rule_type="near_mount",
            mount_positions=((10.0, 10.0), (90.0, 10.0)),
            max_distance_mm=5.0,
        ),
        MountingRule(
            component_idx=2,  # LED1
            rule_type="fixed_position",
            target_position=(50.0, 50.0),
        ),
    ]

    loss_fn = create_mechanical_loss(netlist, rules)
    assert isinstance(loss_fn, MechanicalMountingLoss)
    assert len(loss_fn.rules) == 3

    # Check resolved rules
    r0 = loss_fn.rules[0]
    assert r0.rule_type_idx == 0  # edge
    assert r0.edge_idx == 2  # LEFT

    r1 = loss_fn.rules[1]
    assert r1.rule_type_idx == 1  # near_mount
    assert r1.mount_positions.shape == (2, 2)

    r2 = loss_fn.rules[2]
    assert r2.rule_type_idx == 2  # fixed_position
    assert r2.target_position.shape == (2,)


def test_mechanical_loss_edge():
    netlist = MockNetlist([MockComponent("J1")])
    board = MockBoard(100.0, 100.0)

    # Rule: J1 must be within 2mm of LEFT edge
    rule = MountingRule(0, "edge", edge="LEFT", max_distance_mm=2.0)
    loss_fn = create_mechanical_loss(netlist, [rule])

    context = LossContext(netlist=netlist, board=board, bounds=None, fixed_mask=None)

    # Case 1: At x=1.0 (Valid, dist=1.0 < 2.0)
    pos1 = jnp.array([[1.0, 50.0]])
    res1 = loss_fn(pos1, None, context)
    assert res1.value < 1e-6

    # Case 2: At x=5.0 (Invalid, dist=5.0 > 2.0, viol=3.0)
    pos2 = jnp.array([[5.0, 50.0]])
    res2 = loss_fn(pos2, None, context)
    # Penalty = 3.0^2 = 9.0
    assert jnp.isclose(res2.value, 9.0, atol=1e-3)


def test_mechanical_loss_near_mount():
    netlist = MockNetlist([MockComponent("L1")])
    board = MockBoard(100.0, 100.0)

    # Rule: L1 within 5mm of (10,10) OR (90,10)
    rule = MountingRule(
        0, "near_mount", mount_positions=((10.0, 10.0), (90.0, 10.0)), max_distance_mm=5.0
    )
    loss_fn = create_mechanical_loss(netlist, [rule])

    context = LossContext(netlist, board, None, None)

    # Case 1: Near first mount (12, 12) -> dist ~2.8 < 5
    pos1 = jnp.array([[12.0, 12.0]])
    res1 = loss_fn(pos1, None, context)
    assert res1.value < 1e-6

    # Case 2: Far from all (50, 50) -> dist to (10,10) is ~56
    pos2 = jnp.array([[50.0, 50.0]])
    res2 = loss_fn(pos2, None, context)
    # dist ~56.56, max=5. viol ~51.56. Loss huge.
    assert res2.value > 100.0


def test_mechanical_loss_fixed_position():
    netlist = MockNetlist([MockComponent("LED1")])
    board = MockBoard(100.0, 100.0)

    # Rule: LED1 at (50, 50) exactly
    rule = MountingRule(0, "fixed_position", target_position=(50.0, 50.0), weight=2.0)
    loss_fn = create_mechanical_loss(netlist, [rule])

    context = LossContext(netlist, board, None, None)

    # Case 1: At target
    pos1 = jnp.array([[50.0, 50.0]])
    res1 = loss_fn(pos1, None, context)
    # The value is ~2e-6 because of 1e-6 epsilon inside sqrt. sqrt(1e-6) = 1e-3.
    # Loss = (1e-3)^2 * weight(2.0) = 1e-6 * 2.0 = 2e-6.
    # Assert slightly looser tolerance or exactly 2e-6
    assert res1.value < 5e-6

    # Case 2: Offset by (3, 4) -> dist 5
    pos2 = jnp.array([[53.0, 54.0]])
    res2 = loss_fn(pos2, None, context)
    # Penalty = 5^2 * weight(2) = 25 * 2 = 50
    assert jnp.isclose(res2.value, 50.0, atol=1e-3)
