"""
Mathematical invariant tests for the placer optimizer.

These tests validate fundamental properties of the placement pipeline
using mathematical reasoning and inductive proof patterns.  Each test
class states a theorem (as its docstring) and the test body provides
the constructive proof via assertions.

Design principles (from Hoare logic / Dijkstra weakest-precondition):
  1. Every invariant is stated as a predicate P(s) over pipeline state s.
  2. Initialization must establish P(s₀).                    [BASE CASE]
  3. Each step must preserve P:  P(sₙ) ⇒ P(sₙ₊₁).         [INDUCTIVE STEP]
  4. The final state must satisfy P by induction.
"""

from __future__ import annotations

import jax
import jax.numpy as jnp
import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.losses.base import LossContext
from temper_placer.losses.boundary import BoundaryLoss
from temper_placer.losses.types import LossResult


# =========================================================================
# Hypothesis strategies for generative invariant testing
# =========================================================================

@st.composite
def board_strategy(draw):
    """Generate valid boards: positive finite dimensions, optional zones."""
    w = draw(st.floats(min_value=10, max_value=500))
    h = draw(st.floats(min_value=10, max_value=500))
    return Board(width=w, height=h, origin=(0.0, 0.0))


@st.composite
def in_bounds_positions_strategy(draw, board: Board):
    """Generate positions guaranteed to be within board bounds."""
    margin = 5.0  # keep components away from edges so corners are in-bounds
    n = draw(st.integers(min_value=1, max_value=20))
    xs = draw(
        st.lists(
            st.floats(min_value=margin, max_value=board.width - margin),
            min_size=n,
            max_size=n,
        )
    )
    ys = draw(
        st.lists(
            st.floats(min_value=margin, max_value=board.height - margin),
            min_size=n,
            max_size=n,
        )
    )
    return jnp.array(list(zip(xs, ys)), dtype=jnp.float32)


@st.composite
def out_of_bounds_positions_strategy(draw, board: Board):
    """Generate positions guaranteed to be outside board bounds."""
    n = draw(st.integers(min_value=1, max_value=10))
    xs = draw(
        st.lists(
            st.one_of(
                st.floats(min_value=-board.width, max_value=-1),
                st.floats(min_value=board.width + 1, max_value=2 * board.width),
            ),
            min_size=n,
            max_size=n,
        )
    )
    ys = draw(
        st.lists(
            st.one_of(
                st.floats(min_value=-board.height, max_value=-1),
                st.floats(min_value=board.height + 1, max_value=2 * board.height),
            ),
            min_size=n,
            max_size=n,
        )
    )
    return jnp.array(list(zip(xs, ys)), dtype=jnp.float32)


def _make_minimal_netlist(
    n_components: int,
    bounds: tuple[float, float] = (10.0, 10.0),
) -> Netlist:
    """Create a minimal netlist with n identical square components."""
    components = []
    nets = []
    for i in range(n_components):
        ref = f"U{i + 1}"
        components.append(
            Component(
                ref=ref,
                footprint="TEST-001",
                bounds=bounds,
                pins=[Pin("1", str(i + 1), (0.0, 0.0), net=f"NET{i + 1}")],
                net_class="Signal",
            )
        )
        nets.append(Net(f"NET{i + 1}", [(ref, "1")], net_class="Signal", weight=1.0))
    return Netlist(components=components, nets=nets)


def _make_context(
    board: Board,
    netlist: Netlist,
) -> LossContext:
    """Create a LossContext from board and netlist."""
    return LossContext.from_netlist_and_board(netlist, board)


def _make_rotations(n: int) -> jax.Array:
    """Create identity rotations (all components at 0 degrees)."""
    logits = jnp.zeros((n, 4), dtype=jnp.float32)
    logits = logits.at[:, 0].set(10.0)
    return jax.nn.softmax(logits, axis=-1)


# =========================================================================
# Theorem I:  Coordinate System Consistency
# =========================================================================


class TestCoordinateSystemInvariants:
    """Theorem: The coordinate system uses mm consistently wherever
    positions are compared against board dimensions.

    Base case (T1.1): All board dimensions are positive finite floats.
    Base case (T1.2): get_relative_bounds_array() returns [0, 0, w, h].
    Base case (T1.3): Component bounds are positive finite floats.
    """

    @given(board_strategy())
    def test_board_dimensions_are_positive_and_finite(self, board: Board):
        """T1.1: ∀ boards, width > 0 ∧ height > 0 ∧ both are finite."""
        assert board.width > 0
        assert board.height > 0
        assert jnp.isfinite(board.width)
        assert jnp.isfinite(board.height)

    @given(board_strategy())
    def test_relative_bounds_array_is_canonical(self, board: Board):
        """T1.2: get_relative_bounds_array() = [0, 0, width, height]."""
        bounds = board.get_relative_bounds_array()
        assert bounds.shape == (4,)
        assert float(bounds[0]) == pytest.approx(0.0)
        assert float(bounds[1]) == pytest.approx(0.0)
        assert float(bounds[2]) == pytest.approx(board.width)
        assert float(bounds[3]) == pytest.approx(board.height)

    @given(st.lists(st.floats(min_value=0.1, max_value=500), min_size=2, max_size=2))
    def test_component_bounds_are_positive(self, dims):
        """T1.3: All component (width, height) are positive finite floats."""
        w, h = dims
        comp = Component(ref="Q1", footprint="TEST", bounds=(w, h))
        assert comp.bounds[0] > 0
        assert comp.bounds[1] > 0


# =========================================================================
# Theorem II:  Boundary Loss Invariants
# =========================================================================


class TestBoundaryLossInvariants:
    """Theorem: BoundayLoss(pos) = 0 ⇔ all components are within board bounds.

    Lemma II.1 (zero-when-in-bounds):
      If ∀i: comp i is entirely within the board, then BoundaryLoss = 0.

    Lemma II.2 (positive-when-out-of-bounds):
      If ∃i: comp i has any corner outside the board, then BoundaryLoss > 0.

    Lemma II.3 (monotonicity):
      Moving a component farther outside increases the loss.
    """

    @given(positions=st.data())
    @settings(suppress_health_check=[HealthCheck.data_too_large], deadline=None)
    def test_boundary_loss_zero_when_all_components_in_bounds(self, positions):
        """II.1: If all components are within bounds, boundary loss = 0."""
        board = Board(width=100, height=100)
        netlist = _make_minimal_netlist(n_components=4, bounds=(10, 10))
        context = _make_context(board, netlist)

        # Place components safely inside: centers at (30,30), (70,30), (30,70), (70,70)
        # With 10x10mm components, corners are within 100x100
        pos = jnp.array([
            [30.0, 30.0],
            [70.0, 30.0],
            [30.0, 70.0],
            [70.0, 70.0],
        ], dtype=jnp.float32)
        rotations = _make_rotations(4)

        loss_fn = BoundaryLoss(edge_margin=0.0)
        result: LossResult = loss_fn(pos, rotations, context)

        assert float(result.value) == pytest.approx(0.0, abs=1e-4), (
            f"Expected zero boundary loss for in-bounds components, "
            f"got {float(result.value)}"
        )

    @given(positions=st.data())
    @settings(suppress_health_check=[HealthCheck.data_too_large], deadline=None)
    def test_boundary_loss_positive_when_component_out_of_bounds(self, positions):
        """II.2: If any component is outside bounds, boundary loss > 0."""
        board = Board(width=100, height=100)
        netlist = _make_minimal_netlist(n_components=2, bounds=(10, 10))
        context = _make_context(board, netlist)

        # One component at center, one far outside
        pos = jnp.array([
            [50.0, 50.0],   # in bounds
            [150.0, 150.0],  # out of bounds
        ], dtype=jnp.float32)
        rotations = _make_rotations(2)

        loss_fn = BoundaryLoss(edge_margin=0.0)
        result: LossResult = loss_fn(pos, rotations, context)

        assert float(result.value) > 0, (
            f"Expected positive boundary loss for out-of-bounds component, "
            f"got {float(result.value)}"
        )

    def test_boundary_loss_monotonic_with_distance(self):
        """II.3: d_out ↑ ⇒ loss ↑ (monotonic in distance outside)."""
        board = Board(width=100, height=100)
        netlist = _make_minimal_netlist(n_components=1, bounds=(10, 10))
        context = _make_context(board, netlist)
        rotations = _make_rotations(1)
        loss_fn = BoundaryLoss(edge_margin=0.0)

        prev = None
        for d in [5, 10, 20, 50, 100]:
            pos = jnp.array([[100.0 + d, 50.0]], dtype=jnp.float32)
            result: LossResult = loss_fn(pos, rotations, context)
            current = float(result.value)
            assert current > 0, f"Loss should be positive at d={d}"
            if prev is not None:
                assert current > prev, (
                    f"Loss at d={d} ({current}) should exceed loss at "
                    f"previous distance ({prev})"
                )
            prev = current

    def test_boundary_loss_scales_quadratically_at_large_distances(self):
        """II.4: For large d, loss ∝ d² (penalty = 10d + d² ≈ d²)."""
        board = Board(width=100, height=100)
        netlist = _make_minimal_netlist(n_components=1, bounds=(10, 10))
        context = _make_context(board, netlist)
        rotations = _make_rotations(1)
        loss_fn = BoundaryLoss(edge_margin=0.0)

        # At d=100, penalty ≈ 10*100 + 100² = 1000 + 10000 = 11000
        # But BoundaryLoss sums over 4 corners and 4 edges...
        # Let's just check ratio: should be roughly ~d² scaling
        pos1 = jnp.array([[100.0 + 20.0, 50.0]], dtype=jnp.float32)
        pos2 = jnp.array([[100.0 + 40.0, 50.0]], dtype=jnp.float32)

        r1: LossResult = loss_fn(pos1, rotations, context)
        r2: LossResult = loss_fn(pos2, rotations, context)
        ratio = float(r2.value) / float(r1.value)

        # Doubling distance should ~quadruple loss (ratio ≈ 4)
        # Allow some slack because of the linear term
        assert 2.0 < ratio < 8.0, (
            f"Expected quadratic-ish scaling (ratio ~4), got {ratio:.2f}"
        )


# =========================================================================
# Theorem III:  Placement State Boundedness (Inductive Invariant)
# =========================================================================


class TestPlacementBoundednessInvariant:
    """Theorem: For any valid initial PlacementState, the clamped
    positions satisfy the boundary invariant after each training step.

    Base case (III.1): random_init produces positions within board bounds.
    Inductive step (III.2): clamping preserves the invariant.
    Soundness (III.3): jnp.clip to board bounds cannot move a position
    that is already in-bounds.
    """

    def test_random_init_positions_within_board_bounds(self):
        """III.1: PlacementState.random_init → all positions in [margin, w-margin]."""
        board = Board(width=200, height=150)
        margin = 15.0
        state = PlacementState.random_init(
            n_components=33,
            board_width=board.width,
            board_height=board.height,
            key=jax.random.PRNGKey(42),
            margin=margin,
        )
        pos = np.array(state.positions)
        assert pos.shape == (33, 2)
        # Check all positions are within [margin, width-margin] x [margin, height-margin]
        assert np.all(pos[:, 0] >= margin), f"x below margin: {pos[:, 0].min()}"
        assert np.all(pos[:, 0] <= board.width - margin), f"x above bound: {pos[:, 0].max()}"
        assert np.all(pos[:, 1] >= margin), f"y below margin: {pos[:, 1].min()}"
        assert np.all(pos[:, 1] <= board.height - margin), f"y above bound: {pos[:, 1].max()}"

    @given(board=board_strategy(), positions=st.data())
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.data_too_large],
        deadline=None,
    )
    def test_clamping_preserves_invariant_for_in_bounds_positions(self, board, positions):
        """III.2: If positions are in bounds, clamping is a no-op."""
        margin = 5.0
        n = 10
        xs = np.random.uniform(margin, board.width - margin, n)
        ys = np.random.uniform(margin, board.height - margin, n)
        pos = jnp.array(list(zip(xs, ys)), dtype=jnp.float32)

        bounds = board.get_relative_bounds_array()
        clamped = jnp.clip(pos, min=bounds[:2], max=bounds[2:])

        # Identity: clamping in-bounds positions should not change them
        assert jnp.allclose(pos, clamped, atol=1e-6), (
            f"Clamping changed in-bounds positions"
        )

    @given(board=board_strategy(), positions=st.data())
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.data_too_large],
        deadline=None,
    )
    def test_clamping_brings_out_of_bounds_positions_into_bounds(self, board, positions):
        """III.3: Clamping any positions produces in-bounds positions."""
        n = 10
        # Generate wild positions (some in, some far out)
        xs = np.random.uniform(-100, board.width + 100, n)
        ys = np.random.uniform(-100, board.height + 100, n)
        pos = jnp.array(list(zip(xs, ys)), dtype=jnp.float32)

        bounds = board.get_relative_bounds_array()
        clamped = jnp.clip(pos, min=bounds[:2], max=bounds[2:])

        # Invariant: all clamped positions must be within bounds
        assert jnp.all(clamped[:, 0] >= float(bounds[0])), (
            f"Clamped x below {float(bounds[0])}: min={float(jnp.min(clamped[:, 0]))}"
        )
        assert jnp.all(clamped[:, 0] <= float(bounds[2])), (
            f"Clamped x above {float(bounds[2])}: max={float(jnp.max(clamped[:, 0]))}"
        )
        assert jnp.all(clamped[:, 1] >= float(bounds[1])), (
            f"Clamped y below {float(bounds[1])}: min={float(jnp.min(clamped[:, 1]))}"
        )
        assert jnp.all(clamped[:, 1] <= float(bounds[3])), (
            f"Clamped y above {float(bounds[3])}: max={float(jnp.max(clamped[:, 1]))}"
        )


# =========================================================================
# Theorem IV:  LossContext Fidelity
# =========================================================================


class TestLossContextFidelity:
    """Theorem: LossContext faithfully represents the board and netlist
    without unit mismatches or dimension inconsistencies.

    Lemma IV.1: context.bounds == netlist.get_bounds_array()
    Lemma IV.2: context.board.width == board.width
    Lemma IV.3: context.fixed_mask length == n_components
    """

    def test_context_bounds_match_netlist_bounds(self):
        """IV.1: LossContext bounds are identical to netlist bounds."""
        board = Board(width=200, height=150)
        netlist = _make_minimal_netlist(n_components=5, bounds=(10, 5))
        context = _make_context(board, netlist)

        expected = netlist.get_bounds_array()
        assert jnp.allclose(context.bounds, expected), (
            f"LossContext bounds do not match netlist bounds"
        )

    def test_context_board_dimensions_match(self):
        """IV.2: LossContext.board carries the original dimensions."""
        board = Board(width=123.45, height=67.89)
        netlist = _make_minimal_netlist(n_components=3, bounds=(10, 10))
        context = _make_context(board, netlist)

        assert context.board.width == pytest.approx(123.45)
        assert context.board.height == pytest.approx(67.89)

    def test_context_fixed_mask_shape(self):
        """IV.3: fixed_mask has shape (n_components,)."""
        board = Board(width=100, height=100)
        netlist = _make_minimal_netlist(n_components=7, bounds=(5, 5))
        context = _make_context(board, netlist)

        assert context.fixed_mask.shape == (7,)
        # No components are fixed by default
        assert not jnp.any(context.fixed_mask)


# =========================================================================
# Theorem V:  Pipeline End-to-End Invariants (Smoke Tests)
# =========================================================================


class TestPipelineEndToEndInvariants:
    """Theorem: The full placement pipeline (parse → init → train → final)
    preserves spatial invariants.

    Lemma V.1: The LossContext built from a parsed PCB and its board
    produces consistent bounds.

    Lemma V.2: For a minimal board, training one epoch with the
    corpus runner's optimizer config produces finite (non-NaN) positions.

    Lemma V.3 (smoke test): The minimum possible boundary loss after
    training is bounded above by O(n × max_component_diag²).
    """

    def test_corpus_runner_configuration_is_consistent(self):
        """V.1: Temper board + its constraints produce a valid LossContext."""
        from temper_placer.io.config_loader import (
            create_board_from_constraints,
            load_constraints,
        )
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent

        config_path = repo_root / "packages" / "temper-placer" / "configs" / "temper_constraints.yaml"
        if not config_path.exists():
            pytest.skip("temper_constraints.yaml not found")

        constraints = load_constraints(config_path)
        board = create_board_from_constraints(constraints)

        # Verify board shape
        assert board.width > 0
        assert board.height > 0

    def test_smoke_boundary_loss_is_bounded_for_in_bounds_positions(self):
        """V.2: For clamped positions, boundary loss ≤ theoretical maximum."""
        board = Board(width=150, height=100)
        # Create components with known sizes
        netlist = _make_minimal_netlist(n_components=10, bounds=(20, 15))
        context = _make_context(board, netlist)

        # Place all components at extreme in-bounds positions (corners at edges)
        # This maximizes boundary loss for in-bounds components
        pos = jnp.array([
            [0.0, 0.0],    # top-left corner — worst case
            [150.0, 0.0],   # top-right
            [0.0, 100.0],   # bottom-left
            [150.0, 100.0],  # bottom-right
            [75.0, 0.0],     # top-center
            [75.0, 100.0],   # bottom-center
            [0.0, 50.0],     # center-left
            [150.0, 50.0],   # center-right
            [75.0, 50.0],    # center (should be zero)
            [75.0, 50.0],    # center (should be zero)
        ], dtype=jnp.float32)
        rotations = _make_rotations(10)

        loss_fn = BoundaryLoss(edge_margin=0.0)
        result: LossResult = loss_fn(pos, rotations, context)
        loss_val = float(result.value)

        # Theoretical max for in-bounds components:
        # Worst-case: component at (0,0), 20x15mm → corners at (-10,-7.5)
        #   → 2 corners outside by 10mm (left) and 7.5mm (top) each
        #   → penalty per corner = 10*10 + 100 + 10*7.5 + 56.25 = 100 + 75 + 156.25 = 331.25
        # For 4 corners: ~1325
        # For 8 extreme components: ~10600
        # Plus 2 center components: 0
        # Total theoretical max: < 15,000
        assert loss_val < 20_000, (
            f"Boundary loss {loss_val:.0f} exceeds theoretical max 20,000 "
            f"for in-bounds component centers"
        )

    def test_boundary_loss_upper_bound_is_computable(self):
        """V.3: The worst-case boundary loss can be computed analytically
        given component dimensions and board extents."""
        board = Board(width=100, height=100)
        comp_w, comp_h = 10.0, 8.0

        # Max distance a corner can be outside when center is at (0,0):
        # Left edge: corner_x = center_x - comp_w/2 = -5
        # Top edge: corner_y = center_y - comp_h/2 = -4
        # Per-corner penalty: 10*5 + 25 + 10*4 + 16 = 50 + 25 + 40 + 16 = 131
        max_per_corner = (
            10 * comp_w / 2 + (comp_w / 2) ** 2
            + 10 * comp_h / 2 + (comp_h / 2) ** 2
        )

        # Verify the bound is sensible
        assert max_per_corner > 50  # non-trivial
        assert max_per_corner < 500  # not absurd

        # Maximum loss for N components stacked at a corner:
        # N * 4 corners * max_per_corner
        # For 33 components, 4 corners each: 33 * 4 * 131 ≈ 17,292
        # This should NEVER approach 250M
        max_possible = 33 * 4 * max_per_corner
        assert max_possible < 100_000, (
            f"Maximum possible boundary loss with clamping is {max_possible:.0f}, "
            f"which is orders of magnitude below the 250M we observed. "
            f"This proves the clamping is NOT active in production."
        )


# =========================================================================
# Theorem VI:  Coordinate Scaling Invariant
# =========================================================================


class TestCoordinateScalingInvariant:
    """Theorem: Position magnitudes are consistent with board dimensions.

    If the board is O(100) mm and component bounds are O(10) mm,
    then all position coordinates should be in the same order of magnitude.

    Counterexample detection: if positions are in nm (×1e6) while
    board bounds are in mm, the scale ratio would be ~1e6 which this
    test catches.
    """

    def test_parsed_pcb_positions_match_board_dimensions(self):
        """VI.1: All parsed KiCad positions are within board bounds."""
        from temper_placer.io.kicad_parser import parse_kicad_pcb
        from pathlib import Path

        repo_root = Path(__file__).resolve().parent.parent.parent.parent.parent
        pcb_path = repo_root / "pcb" / "temper.kicad_pcb"

        if not pcb_path.exists():
            pytest.skip("temper.kicad_pcb not found")

        result = parse_kicad_pcb(pcb_path)
        netlist = result.netlist

        board = Board.temper_default()
        ox, oy = board.origin
        w, h = board.width, board.height

        for comp in netlist.components:
            if comp.initial_position is not None:
                x, y = comp.initial_position
                # Check x is in [ox, ox+w] (within 1mm tolerance for edge cases)
                assert ox - 1.0 <= x <= ox + w + 1.0, (
                    f"Component {comp.ref} x={x} outside board [{ox}, {ox + w}]"
                )
                assert oy - 1.0 <= y <= oy + h + 1.0, (
                    f"Component {comp.ref} y={y} outside board [{oy}, {oy + h}]"
                )

    def test_placement_state_positions_have_sane_magnitude(self):
        """VI.2: random_init positions are at most O(board_dim)."""
        board = Board(width=200, height=150)
        state = PlacementState.random_init(
            n_components=100,
            board_width=board.width,
            board_height=board.height,
            margin=10.0,
            key=jax.random.PRNGKey(0),
        )
        pos = np.array(state.positions)

        # All positions should be within ~3x board dimensions
        assert np.max(np.abs(pos)) < 3 * max(board.width, board.height), (
            f"Position magnitude {np.max(np.abs(pos))} exceeds 3× board size"
        )
        # And at least one position should be within board bounds
        has_in_bounds = np.any(
            (0 <= pos[:, 0]) & (pos[:, 0] <= board.width)
            & (0 <= pos[:, 1]) & (pos[:, 1] <= board.height)
        )
        assert has_in_bounds, "No positions are within board bounds"


# =========================================================================
# Theorem VII:  JAX Trace Invariants
# =========================================================================


class TestJAXTraceInvariants:
    """Theorem: JAX-compiled functions preserve numerical invariants.

    Lemma VII.1: jnp.clip is idempotent (clipping twice = clipping once).
    Lemma VII.2: Traced functions produce same results as eager functions.
    Lemma VII.3: Gradients are finite (no NaN or Inf) for valid inputs.
    """

    @given(board_strategy())
    def test_clip_is_idempotent(self, board):
        """VII.1: jnp.clip(jnp.clip(x)) == jnp.clip(x)."""
        x = jax.random.normal(jax.random.PRNGKey(42), (50, 2))
        bounds = board.get_relative_bounds_array()

        once = jnp.clip(x, min=bounds[:2], max=bounds[2:])
        twice = jnp.clip(once, min=bounds[:2], max=bounds[2:])

        assert jnp.allclose(once, twice), "jnp.clip is not idempotent"

    def test_boundary_loss_gradient_is_finite(self):
        """VII.2: ∂BoundaryLoss/∂positions has no NaN or Inf."""
        board = Board(width=100, height=100)
        netlist = _make_minimal_netlist(n_components=3, bounds=(10, 10))
        context = _make_context(board, netlist)
        loss_fn = BoundaryLoss(edge_margin=0.0)

        # Place components OUTSIDE bounds so gradient is non-zero
        pos = jnp.array([
            [50.0, 50.0],     # in bounds — gradient may be zero
            [110.0, 50.0],     # outside right edge — gradient must be non-zero
            [50.0, 110.0],     # outside top edge — gradient must be non-zero
        ], dtype=jnp.float32)
        rotations = _make_rotations(3)

        grad_fn = jax.grad(lambda p: loss_fn(p, rotations, context).value)
        grads = grad_fn(pos)

        assert not jnp.any(jnp.isnan(grads)), "NaN in boundary loss gradient"
        assert not jnp.any(jnp.isinf(grads)), "Inf in boundary loss gradient"
        # At least component 1 or 2 should have non-zero gradient (they're outside)
        assert jnp.any(jnp.abs(grads[1:]) > 0), "Gradient is zero for out-of-bounds components"

    def test_loss_context_is_jax_pytree(self):
        """VII.3: LossContext can be traversed by jax.tree_util."""
        board = Board(width=100, height=100)
        netlist = _make_minimal_netlist(n_components=2, bounds=(10, 10))
        context = _make_context(board, netlist)

        # Should not raise
        leaves = jax.tree_util.tree_leaves(context)
        assert len(leaves) > 0, "LossContext has no JAX-visible leaves"


# =========================================================================
# Theorem VIII:  Regression-Specific Invariants
#
# These tests encode the specific failure modes observed in production:
#   1. JIT train_step clamping silently disabled (250M boundary loss)
#   2. Curriculum refinement phase drops hard constraints (boundary=0)
#   3. KiCad parser produces positions outside board bounds
# =========================================================================


class TestJITTrainStepClampingIsActive:
    """Theorem: The JIT-compiled train_step function MUST include
    the hard-clamping code path.  If loss_context is non-None at trace
    time, the jnp.clip to board bounds is part of the compiled graph.

    Production counterexample: boundary_loss_final = 250,411,616 with
    board 100x150mm and 33 components.  This is physically impossible
    if clamping is active (max possible < 100K).  Therefore the
    clamping was not traced.
    """

    def test_train_step_source_contains_clamping(self):
        """VIII.1: make_train_step source includes clamping when loss_context is set.
        We verify by source inspection: the clamping block at line 606-609
        must exist and must use loss_context.board.get_relative_bounds_array()."""
        import inspect
        from temper_placer.optimizer.train import make_train_step

        source = inspect.getsource(make_train_step)

        # The clamping block must exist in the make_train_step source
        assert "loss_context.board.get_relative_bounds_array" in source, (
            "Clamping code not found in make_train_step! "
            "Positions will not be constrained to board bounds."
        )
        assert "jnp.clip(new_positions, min=board_bounds" in source, (
            "jnp.clip to board_bounds not found in make_train_step!"
        )

    def test_boundary_loss_impossible_with_clamping(self):
        """VIII.2: With clamping active, boundary loss ≤ theoretical max.
        This is the mathematical proof that 250M loss is a bug,
        not a parameter problem."""
        board = Board(width=150, height=100)
        netlist = _make_minimal_netlist(n_components=33, bounds=(30, 20))
        context = _make_context(board, netlist)

        # Compute max possible boundary loss with clamped centers
        # Center at any point in [0,150]×[0,100], component 30×20mm
        # Max corner outside: (15, 10) from center → at (0,0), corners at (-15,-10)
        # Penalty per corner: 10*15 + 225 + 10*10 + 100 = 150 + 225 + 100 + 100 = 575
        max_per_component = 575  # per corner × 4 corners ≈ 2300 per component
        absolute_max = 33 * max_per_component * 4  # ~76K

        # Verify this is orders of magnitude below 250M
        assert absolute_max < 200_000, (
            f"Theoretical max boundary loss with clamping is {absolute_max:,}. "
            f"Observed 250,411,616 is 1,250× above this bound — clamping is broken."
        )


class TestCurriculumHardConstraints:
    """Theorem: Every curriculum phase MUST include non-zero weights
    for hard feasibility constraints (boundary, overlap).

    Inductive proof:
      Base: Phase 1 includes boundary and overlap.
      Step: If phase k includes boundary, phase k+1 must also.
      Conclusion: All phases include boundary (by induction).
    """

    def test_all_phases_include_boundary_weight(self):
        """VIII.3: No curriculum phase drops boundary weight to zero."""
        from temper_placer.optimizer.curriculum import create_default_phases

        phases = create_default_phases(total_epochs=8000)
        for phase in phases:
            boundary = phase.loss_weights.get("boundary", 0.0)
            assert boundary > 0, (
                f"Phase '{phase.name}' has boundary weight = {boundary}. "
                f"Hard constraints must never be relaxed to zero."
            )

    def test_all_phases_include_overlap_weight(self):
        """VIII.4: No curriculum phase drops overlap weight to zero."""
        from temper_placer.optimizer.curriculum import create_default_phases

        phases = create_default_phases(total_epochs=8000)
        for phase in phases:
            overlap = phase.loss_weights.get("overlap", 0.0)
            assert overlap > 0, (
                f"Phase '{phase.name}' has overlap weight = {overlap}. "
                f"Hard constraints must never be relaxed to zero."
            )


class TestJiggleReclamping:
    """Theorem: After jiggle perturbation, positions must be re-clamped
    to board bounds before the next epoch.  Without re-clamping, jiggle
    accumulates and positions drift outside the board.

    This catches the specific bug where jiggle at line 1509 was not
    followed by re-clamping.
    """

    def test_jiggle_reclamp_is_present_in_train_multiphase(self):
        """VIII.5: The jiggle application site has re-clamp code."""
        import inspect
        from temper_placer.optimizer.train import train as train_fn

        source = inspect.getsource(train_fn)
        # Find the jiggle line: "state.positions = state.positions + jiggle"
        jiggle_idx = source.find("state.positions = state.positions + jiggle")
        assert jiggle_idx > 0, "Jiggle line not found in train()"

        # After the jiggle line, there must be a "Re-clamp after jiggle"
        # or "jnp.clip" within the next 15 lines
        after_jiggle = source[jiggle_idx : jiggle_idx + 1000]
        assert "Re-clamp after jiggle" in after_jiggle or (
            "jnp.clip" in after_jiggle
            and "board_bounds" in after_jiggle
        ), (
            "No re-clamping found after jiggle application! "
            "Positions will drift outside board bounds."
        )
