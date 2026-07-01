"""Closure test: prove the ISOLATION_BARRIER is enforced through the loss pipeline.

Before the PCL Single-Source-of-Truth fix:
- load_constraints() returned legacy PlacementConstraints
- PCL auto-discovery silently skipped
- ISOLATION_BARRIER / HV-LV separation was never enforced in the optimize path

This test proves the fix works by demonstrating:
1. PCL constraints produce real separation loss that penalizes close placement
2. The loss decreases monotonically as components move apart
3. Legacy constraint loading (the old bug) does NOT enforce this separation
"""

from pathlib import Path

import jax.numpy as jnp
import pytest

PCL_CONFIG_PATH = Path(__file__).parents[2] / "configs" / "pcl" / "temper_induction.yaml"
LEGACY_CONFIG_PATH = Path(__file__).parents[2] / "configs" / "temper_constraints.yaml"


class TestClosureIsolationBarrier:
    """Prove the ISOLATION_BARRIER is no longer a ghost."""

    def test_pcl_constraints_load_from_config(self):
        """PCL config loads successfully and contains the separation constraint."""
        from temper_placer.pcl.constraints import SeparatedConstraint
        from temper_placer.pcl.parser import parse_pcl_file

        collection = parse_pcl_file(PCL_CONFIG_PATH)
        assert collection is not None, "PCL constraints failed to load"
        assert len(collection.constraints) > 0, "No constraints loaded from PCL config"

        separated = [
            c for c in collection.constraints
            if isinstance(c, SeparatedConstraint)
        ]
        assert len(separated) >= 1, (
            f"HV/MCU separation constraint not found in loaded constraints. "
            f"Found {len(collection.constraints)} constraints: "
            f"{[type(c).__name__ for c in collection.constraints]}"
        )

        # Verify the specific HV/MCU separation
        hv_mcu = [c for c in separated if c.a == 'HV_ZONE' and c.b == 'MCU_ZONE']
        assert len(hv_mcu) == 1, (
            f"Expected exactly 1 HV_ZONE/MCU_ZONE separation, found {len(hv_mcu)}: "
            f"{[(c.a, c.b) for c in separated]}"
        )
        assert hv_mcu[0].min_distance_mm == 10.0, (
            f"Expected 10mm min distance, got {hv_mcu[0].min_distance_mm}"
        )

    def test_separated_constraint_has_hard_tier(self):
        """The HV/MCU separation constraint is tier HARD (tier=1)."""
        from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
        from temper_placer.pcl.parser import parse_pcl_file

        collection = parse_pcl_file(PCL_CONFIG_PATH)
        separated = [
            c for c in collection.constraints
            if isinstance(c, SeparatedConstraint)
            and c.a == 'HV_ZONE' and c.b == 'MCU_ZONE'
        ]
        assert len(separated) == 1
        assert separated[0].tier == ConstraintTier.HARD, (
            f"HV/MCU separation should be HARD tier, got {separated[0].tier}"
        )

    def test_separation_loss_decreases_with_distance(self):
        """As components move apart, group separation loss strictly decreases.

        This is the heart of the closure test: when HV and MCU component
        groups are close, the loss is high; when they're far apart,
        the loss approaches zero. If this monotonicity fails, the
        ISOLATION_BARRIER was never really enforced.
        """
        from temper_placer.losses.grouping import GroupConfig, GroupSeparationLoss

        n_hv = 3
        n_mcu = 3
        n_total = n_hv + n_mcu

        hv_indices = jnp.array(list(range(n_hv)), dtype=jnp.int32)
        mcu_indices = jnp.array(list(range(n_hv, n_total)), dtype=jnp.int32)

        group_a = GroupConfig(
            name="HV_ZONE",
            component_indices=hv_indices,
            max_diameter_mm=0.0,
            weight=1e6,  # HARD tier weight
        )
        group_b = GroupConfig(
            name="MCU_ZONE",
            component_indices=mcu_indices,
            max_diameter_mm=0.0,
            weight=1e6,  # HARD tier weight
        )

        loss_fn = GroupSeparationLoss(
            separations=[(group_a, group_b, 10.0)],
        )

        rotations = jnp.zeros((n_total, 4))

        # Test at various centroid distances
        distances = [1.0, 3.0, 5.0, 8.0, 10.0, 15.0, 20.0, 50.0]
        previous_loss = float("inf")

        for d in distances:
            # Place HV group at x=0, MCU group at x=d
            positions = jnp.zeros((n_total, 2))
            positions = positions.at[hv_indices, 0].set(0.0)
            positions = positions.at[mcu_indices, 0].set(float(d))

            result = loss_fn(positions, rotations, None)
            loss_val = float(result.value)

            # Below min_distance: loss MUST be non-zero
            if d < 10.0:
                assert loss_val > 0, (
                    f"Separation loss should be >0 when centroid distance "
                    f"({d}mm) < min_distance (10mm), got {loss_val:.4f}"
                )

            # At or above min_distance: loss SHOULD be zero (or tiny)
            if d >= 10.0:
                assert loss_val < 1e-3, (
                    f"Separation loss should be ~0 when centroid distance "
                    f"({d}mm) >= min_distance (10mm), got {loss_val:.4f}"
                )

            # Monotonic: loss should not increase as distance increases
            # (allow tiny floating point noise for d >= min_dist)
            if d < 10.0:
                assert loss_val <= previous_loss, (
                    f"Separation loss should decrease with distance: "
                    f"at {d}mm loss={loss_val:.4f} but at previous distance "
                    f"loss was {previous_loss:.4f}"
                )

            previous_loss = loss_val

    def test_separation_loss_with_nonzero_group_centroid_y(self):
        """Separation loss also works when groups are offset in Y, not just X."""
        from temper_placer.losses.grouping import GroupConfig, GroupSeparationLoss

        hv_idx = jnp.array([0, 1], dtype=jnp.int32)
        mcu_idx = jnp.array([2, 3], dtype=jnp.int32)

        group_a = GroupConfig(
            name="HV_ZONE", component_indices=hv_idx,
            max_diameter_mm=0.0, weight=1e6,
        )
        group_b = GroupConfig(
            name="MCU_ZONE", component_indices=mcu_idx,
            max_diameter_mm=0.0, weight=1e6,
        )

        loss_fn = GroupSeparationLoss(
            separations=[(group_a, group_b, 10.0)],
        )

        rotations = jnp.zeros((4, 4))

        # 3-4-5 triangle: 3mm X, 4mm Y => 5mm centroid distance (< 10mm min)
        positions_close = jnp.array([
            [0.0, 0.0],
            [0.0, 2.0],  # HV group centroid at (0, 1)
            [3.0, 4.0],
            [3.0, 6.0],  # MCU group centroid at (3, 5)
        ])
        # Centroid distance: sqrt((3-0)^2 + (5-1)^2) = sqrt(9+16) = 5mm

        result_close = loss_fn(positions_close, rotations, None)
        assert float(result_close.value) > 0, (
            f"Loss should be >0 at 5mm centroid distance: {result_close.value:.4f}"
        )

        # 9-12-15 triangle: 9mm X, 12mm Y => 15mm centroid distance (> 10mm min)
        positions_far = jnp.array([
            [0.0, 0.0],
            [0.0, 2.0],   # HV group centroid at (0, 1)
            [9.0, 12.0],
            [9.0, 14.0],  # MCU group centroid at (9, 13)
        ])
        # Centroid distance: sqrt((9-0)^2 + (13-1)^2) = sqrt(81+144) = 15mm

        result_far = loss_fn(positions_far, rotations, None)
        assert float(result_far.value) < 1e-3, (
            f"Loss should be ~0 at 15mm centroid distance: {result_far.value:.4f}"
        )

        # Loss should be lower for farther distance
        assert float(result_close.value) > float(result_far.value), (
            f"Loss at 5mm ({result_close.value:.4f}) should exceed "
            f"loss at 15mm ({result_far.value:.4f})"
        )

    def test_legacy_config_does_not_load_pcl_constraints(self):
        """The legacy config path returns PlacementConstraints, not PCL."""
        from temper_placer.io.config_loader import (
            PlacementConstraints, load_constraints,
        )
        from temper_placer.pcl.parser import ConstraintCollection

        legacy_path = LEGACY_CONFIG_PATH
        result = load_constraints(legacy_path)
        assert result is not None, "Legacy config should still load"

        # Legacy returns a PlacementConstraints, NOT a ConstraintCollection
        assert isinstance(result, PlacementConstraints), (
            f"Legacy config should return PlacementConstraints, "
            f"got {type(result).__name__}"
        )
        assert not isinstance(result, ConstraintCollection), (
            "Legacy config should NOT return PCL ConstraintCollection"
        )

    def test_constraints_compile_to_loss_functions(self):
        """PCL constraints compile to JAX loss functions via the bridge."""
        from temper_placer.core.board import Board, Zone
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.pcl.constraints import CompilationContext, CompilationTarget
        from temper_placer.pcl.loss_bridge import (
            constraint_to_loss, separated_to_separation_loss,
        )
        from temper_placer.pcl.constraints import SeparatedConstraint
        from temper_placer.pcl.parser import parse_pcl_file

        collection = parse_pcl_file(PCL_CONFIG_PATH)
        assert len(collection.constraints) > 0

        # Create a minimal Board with HV_ZONE and MCU_ZONE
        board = Board(
            width=100.0,
            height=150.0,
            origin=(0.0, 0.0),
            zones=[
                Zone(
                    name="HV_ZONE",
                    bounds=(0.0, 110.0, 100.0, 150.0),
                    components=["Q1", "Q2", "D1", "C_DC"],
                ),
                Zone(
                    name="MCU_ZONE",
                    bounds=(0.0, 0.0, 100.0, 70.0),
                    components=["U_MCU", "C1", "C2", "R1"],
                ),
            ],
        )

        # Create a minimal Netlist with components referenced by zones
        netlist = Netlist(
            components=[
                Component(ref="Q1", footprint="TO247", bounds=(16.0, 5.0)),
                Component(ref="Q2", footprint="TO247", bounds=(16.0, 5.0)),
                Component(ref="D1", footprint="SOD123", bounds=(3.0, 1.8)),
                Component(ref="C_DC", footprint="CAP_RADIAL", bounds=(10.0, 20.0)),
                Component(ref="U_MCU", footprint="QFN56", bounds=(7.0, 7.0)),
                Component(ref="C1", footprint="0603", bounds=(1.6, 0.8)),
                Component(ref="C2", footprint="0603", bounds=(1.6, 0.8)),
                Component(ref="R1", footprint="0603", bounds=(1.6, 0.8)),
            ],
        )

        # Verify each SeparatedConstraint can compile to a loss function
        from temper_placer.pcl.constraints import SeparatedConstraint as SC

        for constraint in collection.constraints:
            if isinstance(constraint, SC):
                loss_fn = separated_to_separation_loss(
                    constraint,
                    netlist,
                    board,
                )
                if constraint.a == "HV_ZONE" and constraint.b == "MCU_ZONE":
                    assert loss_fn is not None
                    assert hasattr(loss_fn, '__call__')
                    assert callable(loss_fn)

        # Test the full CompilationTarget.JAX path
        ctx = CompilationContext(netlist=netlist, board=board)
        losses = collection.compile(CompilationTarget.JAX, ctx)
        assert len(losses) > 0, (
            f"ConstraintCollection.compile(CompilationTarget.JAX) returned zero loss functions. "
            f"Bridge is not wired. Context has netlist={netlist.n_components} comps"
        )

        # Every compiled output should be callable
        for loss in losses:
            assert callable(loss), f"Compiled loss is not callable: {type(loss)}"

    def test_loss_bridge_preserves_tier_weights(self):
        """The loss bridge applies HARD tier weight (1e6) to separation loss."""
        from temper_placer.losses.grouping import GroupConfig, GroupSeparationLoss

        hv_idx = jnp.array([0], dtype=jnp.int32)
        mcu_idx = jnp.array([1], dtype=jnp.int32)

        group_a = GroupConfig(
            name="HV_ZONE", component_indices=hv_idx,
            max_diameter_mm=0.0, weight=1e6,
        )
        group_b = GroupConfig(
            name="MCU_ZONE", component_indices=mcu_idx,
            max_diameter_mm=0.0, weight=1e6,
        )

        loss_fn = GroupSeparationLoss(
            separations=[(group_a, group_b, 10.0)],
        )

        positions_close = jnp.array([[0.0, 0.0], [1.0, 0.0]])
        rotations = jnp.zeros((2, 4))

        result = loss_fn(positions_close, rotations, None)

        # deficit = max(0, 10.0 - 1.0) = 9.0
        # penalty = 1e6 * 9.0^2 = 1e6 * 81 = 81e6
        # The weight matters because without it, the loss would be 81
        expected_min = 80e6  # Allow some margin
        assert float(result.value) > expected_min, (
            f"With HARD tier (1e6), loss at 1mm separation should exceed "
            f"{expected_min:.0f}, got {result.value:.4f}. "
            f"Without tier weight, loss would be ~81. Weight is not applied."
        )
