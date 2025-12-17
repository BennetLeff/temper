"""
Unit tests for CriticalPathLengthLoss.

Tests cover:
- Basic path length computation
- Zero penalty for paths within limits
- Positive penalty for paths exceeding limits
- Priority-based weighting
- Gradient computation for optimization
- Edge cases (missing components, empty paths)
"""

import pytest
import jax
import jax.numpy as jnp

from temper_placer.losses.critical_path import (
    CriticalPath,
    CriticalPathLengthLoss,
    compute_critical_path_penalty,
    create_temper_critical_paths,
)
from temper_placer.losses.base import LossContext, LossResult
from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def simple_netlist():
    """Create a simple netlist with components for testing critical paths."""
    components = [
        Component(
            ref="U_GATE",
            footprint="SOIC-8",
            bounds=(5.0, 4.0),
            pins=[Pin("OUT", "1", (0.0, 0.0))],
            net_class="Signal",
        ),
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(16.0, 20.0),
            pins=[Pin("G", "1", (0.0, 0.0))],
            net_class="HighVoltage",
        ),
        Component(
            ref="Q2",
            footprint="TO-247",
            bounds=(16.0, 20.0),
            pins=[Pin("G", "1", (0.0, 0.0))],
            net_class="HighVoltage",
        ),
        Component(
            ref="U_MCU",
            footprint="QFP-48",
            bounds=(10.0, 10.0),
            pins=[Pin("SPI", "1", (0.0, 0.0))],
            net_class="Signal",
        ),
    ]

    nets = [
        Net("GATE1", [("U_GATE", "OUT"), ("Q1", "G")]),
        Net("GATE2", [("U_GATE", "OUT"), ("Q2", "G")]),
    ]

    return Netlist(components=components, nets=nets)


@pytest.fixture
def simple_board():
    """Create a simple board for testing."""
    return Board(width=100.0, height=80.0, origin=(0.0, 0.0))


@pytest.fixture
def simple_context(simple_netlist, simple_board):
    """Create a LossContext for testing."""
    return LossContext.from_netlist_and_board(simple_netlist, simple_board)


@pytest.fixture
def sample_rotations():
    """Sample rotation one-hots (all 0 degrees)."""
    return jnp.array(
        [
            [1.0, 0.0, 0.0, 0.0],  # U_GATE
            [1.0, 0.0, 0.0, 0.0],  # Q1
            [1.0, 0.0, 0.0, 0.0],  # Q2
            [1.0, 0.0, 0.0, 0.0],  # U_MCU
        ],
        dtype=jnp.float32,
    )


# =============================================================================
# Test CriticalPath dataclass
# =============================================================================


class TestCriticalPath:
    """Tests for CriticalPath dataclass."""

    def test_critical_path_weight_critical(self):
        """Test that critical priority gives weight 10.0."""
        path = CriticalPath("test", "A", "B", 10.0, priority="critical")
        assert path.weight == 10.0

    def test_critical_path_weight_high(self):
        """Test that high priority gives weight 5.0."""
        path = CriticalPath("test", "A", "B", 10.0, priority="high")
        assert path.weight == 5.0

    def test_critical_path_weight_normal(self):
        """Test that normal priority gives weight 1.0."""
        path = CriticalPath("test", "A", "B", 10.0, priority="normal")
        assert path.weight == 1.0

    def test_critical_path_default_priority(self):
        """Test that default priority is normal."""
        path = CriticalPath("test", "A", "B", 10.0)
        assert path.priority == "normal"
        assert path.weight == 1.0


# =============================================================================
# Test CriticalPathLengthLoss
# =============================================================================


class TestCriticalPathLengthLoss:
    """Tests for CriticalPathLengthLoss."""

    def test_name(self):
        """Test loss function name."""
        loss = CriticalPathLengthLoss([])
        assert loss.name == "critical_path_length"

    def test_empty_paths_zero_loss(self, sample_rotations, simple_context):
        """Test that empty path list produces zero loss."""
        positions = jnp.array(
            [[10.0, 10.0], [50.0, 50.0], [60.0, 50.0], [80.0, 20.0]],
            dtype=jnp.float32,
        )
        loss = CriticalPathLengthLoss([])
        result = loss(positions, sample_rotations, simple_context)

        assert isinstance(result, LossResult)
        assert float(result.value) == 0.0

    def test_path_within_limit_zero_penalty(self, sample_rotations, simple_context):
        """Test that path within limit produces zero penalty."""
        # U_GATE at (10, 10), Q1 at (20, 10) -> Manhattan distance = 10mm
        positions = jnp.array(
            [[10.0, 10.0], [20.0, 10.0], [60.0, 50.0], [80.0, 20.0]],
            dtype=jnp.float32,
        )

        path = CriticalPath("gate_high", "U_GATE", "Q1", max_length_mm=15.0)
        loss = CriticalPathLengthLoss([path])
        result = loss(positions, sample_rotations, simple_context)

        # Distance is 10mm, max is 15mm -> no penalty
        assert float(result.value) == pytest.approx(0.0, abs=1e-6)

    def test_path_exceeding_limit_positive_penalty(self, sample_rotations, simple_context):
        """Test that path exceeding limit produces positive penalty."""
        # U_GATE at (10, 10), Q1 at (40, 30) -> Manhattan distance = 30 + 20 = 50mm
        positions = jnp.array(
            [[10.0, 10.0], [40.0, 30.0], [60.0, 50.0], [80.0, 20.0]],
            dtype=jnp.float32,
        )

        path = CriticalPath("gate_high", "U_GATE", "Q1", max_length_mm=15.0, priority="normal")
        loss = CriticalPathLengthLoss([path])
        result = loss(positions, sample_rotations, simple_context)

        # Distance is 50mm, max is 15mm, excess = 35mm
        # Penalty = 1.0 * 35^2 = 1225
        expected_penalty = 1.0 * (50.0 - 15.0) ** 2
        assert float(result.value) == pytest.approx(expected_penalty, rel=1e-5)

    def test_critical_priority_higher_penalty(self, sample_rotations, simple_context):
        """Test that critical priority produces 10x higher penalty."""
        # U_GATE at (10, 10), Q1 at (30, 10) -> distance = 20mm
        positions = jnp.array(
            [[10.0, 10.0], [30.0, 10.0], [60.0, 50.0], [80.0, 20.0]],
            dtype=jnp.float32,
        )

        path_normal = CriticalPath("gate", "U_GATE", "Q1", max_length_mm=15.0, priority="normal")
        path_critical = CriticalPath(
            "gate", "U_GATE", "Q1", max_length_mm=15.0, priority="critical"
        )

        loss_normal = CriticalPathLengthLoss([path_normal])
        loss_critical = CriticalPathLengthLoss([path_critical])

        result_normal = loss_normal(positions, sample_rotations, simple_context)
        result_critical = loss_critical(positions, sample_rotations, simple_context)

        # Critical should be 10x normal
        assert float(result_critical.value) == pytest.approx(
            10.0 * float(result_normal.value), rel=1e-5
        )

    def test_multiple_paths_summed(self, sample_rotations, simple_context):
        """Test that penalties from multiple paths are summed."""
        # U_GATE at (10, 10), Q1 at (30, 10), Q2 at (30, 30)
        # Path 1: U_GATE -> Q1 = 20mm (exceeds 15mm by 5mm)
        # Path 2: U_GATE -> Q2 = 20 + 20 = 40mm (exceeds 15mm by 25mm)
        positions = jnp.array(
            [[10.0, 10.0], [30.0, 10.0], [30.0, 30.0], [80.0, 20.0]],
            dtype=jnp.float32,
        )

        paths = [
            CriticalPath("gate_high", "U_GATE", "Q1", max_length_mm=15.0, priority="normal"),
            CriticalPath("gate_low", "U_GATE", "Q2", max_length_mm=15.0, priority="normal"),
        ]
        loss = CriticalPathLengthLoss(paths)
        result = loss(positions, sample_rotations, simple_context)

        # Penalty 1: (20 - 15)^2 = 25
        # Penalty 2: (40 - 15)^2 = 625
        # Total: 650
        expected = (20.0 - 15.0) ** 2 + (40.0 - 15.0) ** 2
        assert float(result.value) == pytest.approx(expected, rel=1e-5)

    def test_missing_component_skipped(self, sample_rotations, simple_context):
        """Test that paths with missing components are skipped."""
        positions = jnp.array(
            [[10.0, 10.0], [30.0, 10.0], [30.0, 30.0], [80.0, 20.0]],
            dtype=jnp.float32,
        )

        paths = [
            CriticalPath("valid", "U_GATE", "Q1", max_length_mm=15.0),
            CriticalPath("invalid", "U_GATE", "NONEXISTENT", max_length_mm=15.0),
        ]
        loss = CriticalPathLengthLoss(paths)
        result = loss(positions, sample_rotations, simple_context)

        # Only valid path should contribute
        # Distance U_GATE -> Q1 = 20mm, excess = 5mm, penalty = 25
        assert float(result.value) == pytest.approx(25.0, rel=1e-5)

    def test_gradient_computation(self, sample_rotations, simple_context):
        """Test that gradients can be computed for optimization."""
        positions = jnp.array(
            [[10.0, 10.0], [30.0, 10.0], [30.0, 30.0], [80.0, 20.0]],
            dtype=jnp.float32,
        )

        path = CriticalPath("gate", "U_GATE", "Q1", max_length_mm=15.0)
        loss = CriticalPathLengthLoss([path])

        def loss_wrapper(pos):
            return loss(pos, sample_rotations, simple_context).value

        grad = jax.grad(loss_wrapper)(positions)

        # Gradients should be finite
        assert jnp.all(jnp.isfinite(grad))
        assert grad.shape == positions.shape

        # Gradient points in direction that increases loss.
        # Since we want to minimize path length, gradient descent will move
        # U_GATE and Q1 closer together.
        # U_GATE (idx 0) at x=10, Q1 (idx 1) at x=30
        # Moving U_GATE right (positive x) decreases distance -> decreases loss
        # So gradient w.r.t. U_GATE x should be negative (loss decreases as x increases)
        # Moving Q1 left (negative x) decreases distance -> decreases loss
        # So gradient w.r.t. Q1 x should be positive (loss decreases as x decreases)
        assert grad[0, 0] < 0  # U_GATE: negative gradient (move right to reduce loss)
        assert grad[1, 0] > 0  # Q1: positive gradient (move left to reduce loss)

    def test_jit_compatible(self, sample_rotations, simple_context):
        """Test that loss can be JIT compiled."""
        positions = jnp.array(
            [[10.0, 10.0], [30.0, 10.0], [30.0, 30.0], [80.0, 20.0]],
            dtype=jnp.float32,
        )

        path = CriticalPath("gate", "U_GATE", "Q1", max_length_mm=15.0)
        loss = CriticalPathLengthLoss([path])

        @jax.jit
        def jit_loss(pos):
            return loss(pos, sample_rotations, simple_context).value

        result = jit_loss(positions)
        assert jnp.isfinite(result)


# =============================================================================
# Test standalone function
# =============================================================================


class TestComputeCriticalPathPenalty:
    """Tests for standalone compute_critical_path_penalty function."""

    def test_within_limit(self):
        """Test penalty is zero when within limit."""
        positions = jnp.array([[0.0, 0.0], [10.0, 0.0]], dtype=jnp.float32)
        penalty = compute_critical_path_penalty(positions, from_idx=0, to_idx=1, max_length_mm=15.0)
        assert float(penalty) == pytest.approx(0.0, abs=1e-6)

    def test_exceeds_limit(self):
        """Test penalty when exceeding limit."""
        positions = jnp.array([[0.0, 0.0], [20.0, 5.0]], dtype=jnp.float32)
        # Manhattan distance = 25mm
        penalty = compute_critical_path_penalty(
            positions, from_idx=0, to_idx=1, max_length_mm=15.0, weight=2.0
        )
        # Excess = 10mm, penalty = 2.0 * 100 = 200
        assert float(penalty) == pytest.approx(200.0, rel=1e-5)


# =============================================================================
# Test factory function
# =============================================================================


class TestCreateTemperCriticalPaths:
    """Tests for Temper-specific critical path factory."""

    def test_returns_list(self):
        """Test that factory returns a list of CriticalPath."""
        paths = create_temper_critical_paths()
        assert isinstance(paths, list)
        assert len(paths) > 0
        assert all(isinstance(p, CriticalPath) for p in paths)

    def test_gate_drive_paths_critical(self):
        """Test that gate drive paths have critical priority."""
        paths = create_temper_critical_paths()
        gate_paths = [p for p in paths if "gate" in p.name.lower()]
        assert len(gate_paths) >= 2
        for p in gate_paths:
            assert p.priority == "critical"
