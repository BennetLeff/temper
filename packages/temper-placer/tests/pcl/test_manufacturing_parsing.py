"""
Tests for manufacturing constraint parsing and loss functions.

These tests are for planned manufacturing constraint features that are not yet implemented.
The AssemblySide, ManufacturingConstraint types, and ManufacturingOrientationLoss do not exist.
Skip the entire module until these features are added.
"""
# ruff: noqa: F821

import pytest

pytestmark = pytest.mark.skip(
    reason="Manufacturing constraint feature not yet implemented: "
    "AssemblySide, ManufacturingConstraint, ManufacturingOrientationLoss do not exist"
)

# Imports guarded - these don't exist yet and would cause collection errors
# import jax.numpy as jnp
# from temper_placer.pcl.parser import parse_constraint_dict
# from temper_placer.pcl.constraints import ConstraintType, AssemblySide, ManufacturingConstraint
# from temper_placer.io.config_loader import load_constraints, PlacementConstraints
# from temper_placer.losses.base import LossContext
# from temper_placer.core.board import Board
# from temper_placer.core.netlist import Netlist, Component
# from temper_placer.losses.manufacturing import ManufacturingOrientationLoss

def test_manufacturing_pcl_parsing():
    """Test that manufacturing constraints are correctly parsed from dict."""
    d = {
        "type": "manufacturing",
        "components": ["Q1", "Q2"],
        "allowed_orientations": [0, 180],
        "side": "top",
        "tier": "hard",
        "because": "Thermal alignment"
    }

    constraint = parse_constraint_dict(d)

    assert isinstance(constraint, ManufacturingConstraint)
    assert constraint.components == ["Q1", "Q2"]
    assert constraint.allowed_orientations == [0, 180]
    assert constraint.side == AssemblySide.TOP
    assert constraint.tier.value == 1 # ConstraintTier.HARD is 1
    assert constraint.because == "Thermal alignment"

def test_manufacturing_yaml_parsing(tmp_path):
    """Test that manufacturing constraints are parsed from YAML config."""
    yaml_content = """
manufacturing_constraints:
  - components: ["Q1", "Q2"]
    allowed_orientations: [0, 180]
    side: "top"
    because: "Heatsink alignment"
"""
    yaml_file = tmp_path / "constraints.yaml"
    yaml_file.write_text(yaml_content)

    constraints = load_constraints(yaml_file)

    assert len(constraints.manufacturing_constraints) == 1
    mfg = constraints.manufacturing_constraints[0]
    assert mfg.components == ["Q1", "Q2"]
    assert mfg.allowed_orientations == [0, 180]
    assert mfg.side == "top"
    assert mfg.because == "Heatsink alignment"

def test_loss_context_mask_population():
    """Test that LossContext correctly populates orientation and side masks."""
    # Setup mock netlist and board
    comp1 = Component(ref="Q1", footprint="TO-220", bounds=(10.0, 15.0), pins=[])
    comp2 = Component(ref="Q2", footprint="TO-220", bounds=(10.0, 15.0), pins=[])
    netlist = Netlist(components=[comp1, comp2])
    board = Board(width=100, height=100)

    # Setup constraints
    from temper_placer.io.config_loader import ManufacturingConstraint as ConfigMFG
    constraints = PlacementConstraints()
    constraints.manufacturing_constraints = [
        ConfigMFG(
            components=["Q1"],
            allowed_orientations=[0, 180],
            side="top",
            because="Constraint 1"
        ),
        ConfigMFG(
            components=["Q2"],
            side="bottom",
            because="Constraint 2"
        )
    ]

    context = LossContext.from_netlist_and_board(netlist, board, constraints=constraints)

    # Check orientation_mask (N, 4)
    # 0, 90, 180, 270
    # Q1: allowed [0, 180] -> [True, False, True, False]
    expected_q1_orient = jnp.array([True, False, True, False])
    assert jnp.all(context.constraints_data.orientation_mask[0] == expected_q1_orient)

    # Q2: allowed all (default) -> [True, True, True, True]
    assert jnp.all(context.constraints_data.orientation_mask[1] == jnp.ones(4, dtype=bool))

    # Check side_mask (N, 2)
    # 0: Top, 1: Bottom
    # Q1: Top -> [True, False]
    assert jnp.all(context.constraints_data.side_mask[0] == jnp.array([True, False]))
    # Q2: Bottom -> [False, True]
    assert jnp.all(context.constraints_data.side_mask[1] == jnp.array([False, True]))

def test_manufacturing_orientation_loss():
    """Test that ManufacturingOrientationLoss computes penalty correctly."""
    # Setup context with mask
    # Q1 only allowed at 0 deg (index 0)
    orient_mask = jnp.array([
        [True, False, False, False],
        [True, True, True, True]
    ])

    class MockConstraintsData:
        orientation_mask = orient_mask

    class MockContext:
        constraints_data = MockConstraintsData()

    loss_fn = ManufacturingOrientationLoss(weight=10.0)

    # Case 1: All correct
    # Q1 at 0 deg, Q2 at 90 deg (both allowed)
    rotations = jnp.array([
        [1.0, 0.0, 0.0, 0.0], # Q1
        [0.0, 1.0, 0.0, 0.0]  # Q2
    ])

    result = loss_fn(None, rotations, MockContext())
    assert result.value == 0.0

    # Case 2: Q1 at 90 deg (disallowed)
    rotations = jnp.array([
        [0.0, 1.0, 0.0, 0.0], # Q1
        [0.0, 1.0, 0.0, 0.0]  # Q2
    ])

    result = loss_fn(None, rotations, MockContext())
    # 1.0 mass on disallowed rotation * 10.0 weight = 10.0
    assert result.value == 10.0

    # Case 3: Soft rotation (Gumbel-Softmax intermediate)
    # Q1 is 50/50 0 deg and 90 deg
    rotations = jnp.array([
        [0.5, 0.5, 0.0, 0.0],
        [1.0, 0.0, 0.0, 0.0]
    ])
    result = loss_fn(None, rotations, MockContext())
    # 0.5 mass on disallowed * 10.0 weight = 5.0
    assert result.value == 5.0
