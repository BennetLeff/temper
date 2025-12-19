from typing import List, Tuple, Any
from dataclasses import dataclass, field
import jax.numpy as jnp
from temper_placer.losses.base import LossFunction, LossResult, LossContext
import pytest
from unittest.mock import MagicMock


@dataclass
class MockComponent:
    ref: str


class MockNetlist:
    def __init__(self, components):
        self.components = components


@dataclass
class CrystalRule:
    """Configuration for crystal placement constraints."""

    crystal_ref: str
    mcu_ref: str
    load_cap_refs: List[str]
    noise_source_refs: List[str] = field(default_factory=list)

    max_mcu_distance_mm: float = 10.0
    max_cap_distance_mm: float = 3.0
    min_noise_distance_mm: float = 15.0

    # Weights
    mcu_dist_weight: float = 1.0
    cap_dist_weight: float = 1.0
    noise_dist_weight: float = 2.0


# --- Re-implementation of the Resolved Logic for Testing ---
# (Usually we import this, but importing from src during test runs can be tricky if not installed)
# Ideally, we should import the real class. Let's try to assume we can import it.
# If not, we will need to adjust the PYTHONPATH or rely on installed package.
# For this test file, I will attempt to import from the file I just created.

try:
    from temper_placer.losses.crystal import (
        ResolvedCrystalPlacementLoss,
        create_crystal_loss,
        CrystalRule as RealCrystalRule,
    )

    # If successful, use the real one.
    CrystalRule = RealCrystalRule
except ImportError:
    # Fallback if the path isn't set up (shouldn't happen in a proper dev env)
    pass


def test_crystal_loss_initialization():
    netlist = MockNetlist(
        [
            MockComponent("Y1"),
            MockComponent("U1"),
            MockComponent("C1"),
            MockComponent("C2"),
            MockComponent("L1"),
        ]
    )

    rule = CrystalRule(
        crystal_ref="Y1",
        mcu_ref="U1",
        load_cap_refs=["C1", "C2"],
        noise_source_refs=["L1"],
        max_mcu_distance_mm=5.0,
        max_cap_distance_mm=2.0,
        min_noise_distance_mm=10.0,
    )

    loss_fn = create_crystal_loss(netlist, [rule])
    assert isinstance(loss_fn, ResolvedCrystalPlacementLoss)
    assert len(loss_fn.rules) == 1

    r = loss_fn.rules[0]
    assert r.crystal_idx == 0  # Y1 is 0
    assert r.mcu_idx == 1  # U1 is 1
    assert len(r.load_cap_indices) == 2
    assert len(r.noise_source_indices) == 1


def test_crystal_loss_happy_path():
    # Setup: Components placed ideally
    # Y1 at (10, 10)
    # U1 at (12, 10) -> Dist 2.0 (OK < 5.0)
    # C1 at (10, 11) -> Dist 1.0 (OK < 2.0)
    # L1 at (100, 100) -> Dist HUGE (OK > 10.0)

    netlist = MockNetlist(
        [
            MockComponent("Y1"),  # 0
            MockComponent("U1"),  # 1
            MockComponent("C1"),  # 2
            MockComponent("L1"),  # 3
        ]
    )

    rule = CrystalRule(
        crystal_ref="Y1",
        mcu_ref="U1",
        load_cap_refs=["C1"],
        noise_source_refs=["L1"],
        max_mcu_distance_mm=5.0,
        max_cap_distance_mm=2.0,
        min_noise_distance_mm=10.0,
    )

    loss_fn = create_crystal_loss(netlist, [rule])

    positions = jnp.array(
        [
            [10.0, 10.0],  # Y1
            [12.0, 10.0],  # U1
            [10.0, 11.0],  # C1
            [100.0, 100.0],  # L1
        ]
    )

    result = loss_fn(positions, None, None)
    assert result.value < 1e-6


def test_crystal_loss_mcu_too_far():
    netlist = MockNetlist([MockComponent("Y1"), MockComponent("U1")])
    rule = CrystalRule("Y1", "U1", [], [], max_mcu_distance_mm=5.0)
    loss_fn = create_crystal_loss(netlist, [rule])

    positions = jnp.array(
        [
            [0.0, 0.0],  # Y1
            [10.0, 0.0],  # U1 (Dist 10 > 5)
        ]
    )

    result = loss_fn(positions, None, None)
    # Penalty: (10 - 5)^2 = 25 * weight(1.0) = 25
    assert jnp.isclose(result.value, 25.0, atol=1e-3)


def test_crystal_loss_cap_too_far():
    netlist = MockNetlist([MockComponent("Y1"), MockComponent("U1"), MockComponent("C1")])
    rule = CrystalRule("Y1", "U1", ["C1"], [], max_cap_distance_mm=2.0)
    loss_fn = create_crystal_loss(netlist, [rule])

    positions = jnp.array(
        [
            [0.0, 0.0],  # Y1
            [1.0, 0.0],  # U1 (OK)
            [0.0, 5.0],  # C1 (Dist 5 > 2)
        ]
    )

    result = loss_fn(positions, None, None)
    # Penalty: (5 - 2)^2 = 9 * weight(1.0) = 9
    assert jnp.isclose(result.value, 9.0, atol=1e-3)


def test_crystal_loss_noise_too_close():
    netlist = MockNetlist([MockComponent("Y1"), MockComponent("U1"), MockComponent("L1")])
    rule = CrystalRule("Y1", "U1", [], ["L1"], min_noise_distance_mm=10.0, noise_dist_weight=2.0)
    loss_fn = create_crystal_loss(netlist, [rule])

    positions = jnp.array(
        [
            [0.0, 0.0],  # Y1
            [1.0, 0.0],  # U1 (OK)
            [0.0, 4.0],  # L1 (Dist 4 < 10)
        ]
    )

    result = loss_fn(positions, None, None)
    # Penalty: (10 - 4)^2 * weight(2.0) = 36 * 2 = 72
    assert jnp.isclose(result.value, 72.0, atol=1e-3)


def test_missing_components_graceful_handling():
    netlist = MockNetlist([MockComponent("Y1"), MockComponent("U1")])
    # C1 and L1 do not exist
    rule = CrystalRule("Y1", "U1", ["C1"], ["L1"])
    loss_fn = create_crystal_loss(netlist, [rule])

    # Indices should be empty
    r = loss_fn.rules[0]
    assert len(r.load_cap_indices) == 0
    assert len(r.noise_source_indices) == 0

    positions = jnp.array([[0.0, 0.0], [1.0, 0.0]])
    result = loss_fn(positions, None, None)
    assert result.value < 1e-6
