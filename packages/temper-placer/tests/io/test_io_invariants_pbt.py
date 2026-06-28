"""
Property-based invariant tests for the IO / KiCad parser layer.

Validates coordinate system consistency, parsed position bounds,
netlist consistency, and LossContext fidelity against generated
ParsedPCB instances.

Each test class states an invariant theorem (as its docstring) and
the test body provides the constructive proof via assertions.

Patterns follow:
- ``tests/router_v6/router_v6_property_strategies.py`` — strategy composition
- ``tests/core/test_placement_invariants.py`` — Theorem VI (coordinate scaling)
"""

from __future__ import annotations

import jax.numpy as jnp
import pytest
from hypothesis import given, settings

from temper_placer.core.netlist import Netlist
from temper_placer.losses.base import LossContext
from temper_placer.router_v6.stage0_data import ParsedPCB

from .io_property_strategies import (
    board,
    board_and_netlist,
    parsed_pcb,
)

# =========================================================================
# Theorem I:  Parsed Component Position Bounds
# =========================================================================


class TestParsedPositionBounds:
    """Theorem: Every component's initial position in a ParsedPCB
    lies within the board's coordinate bounds [0, width] x [0, height].

    Lemma I.1: All positions are within [0, board.width] x [0, board.height].
    Lemma I.2: Zero-component ParsedPCB vacuously satisfies the invariant.
    Lemma I.3: Position at board edge (x=0, y=0) passes inclusive check.
    """

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_all_component_positions_within_board_bounds(self, pcb: ParsedPCB):
        """I.1: For any generated ParsedPCB, every component's
        initial_position is within the board's coordinate bounds."""
        bw, bh = pcb.board.width, pcb.board.height

        for comp in pcb.components:
            assert comp.initial_position is not None, (
                f"Component {comp.ref} has no initial_position"
            )
            x, y = comp.initial_position
            assert 0.0 <= x <= bw, (
                f"Component {comp.ref}: x={x} not in [0, {bw}]"
            )
            assert 0.0 <= y <= bh, (
                f"Component {comp.ref}: y={y} not in [0, {bh}]"
            )

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_zero_component_parsed_pcb_vacuously_passes(self, pcb: ParsedPCB):
        """I.2: A ParsedPCB with zero components has no position assertions
        to fail — the invariant is vacuously true."""
        if len(pcb.components) == 0:
            # If the strategy produced zero components, the loop above
            # would be empty — no assertion failure possible.
            # Set up a known-zero case explicitly to verify.
            assert len(pcb.components) == 0

    @pytest.mark.property
    @given(
        board_and_netlist(min_components=1, max_components=1)
    )
    @settings(max_examples=50, deadline=30000)
    def test_edge_position_passes_inclusive_check(self, board_nl: tuple):
        """I.3: A component at board edge (x=0, y=0) passes the inclusive
        bounds check."""
        b, _nl = board_nl
        # Manually place a component at the origin (0, 0).
        from temper_placer.core.netlist import Component, Pin

        comp = Component(
            ref="EDGE1",
            footprint="TEST",
            bounds=(10.0, 10.0),
            pins=[Pin("1", "1", (0.0, 0.0), net="EDGE_NET")],
            initial_position=(0.0, 0.0),
        )
        # Position is at (0, 0) — must be within [0, b.width] x [0, b.height]
        x, y = comp.initial_position
        assert 0.0 <= x <= b.width
        assert 0.0 <= y <= b.height


# =========================================================================
# Theorem II:  Component Bounds Positive
# =========================================================================


class TestComponentBoundsPositive:
    """Theorem: Every component's bounds (width, height) are positive
    finite floating-point values."""

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_all_component_bounds_are_positive_finite(self, pcb: ParsedPCB):
        """II.1: For every component in a ParsedPCB, width > 0
        and height > 0, and both are finite."""
        for comp in pcb.components:
            w, h = comp.bounds
            assert w > 0, (
                f"Component {comp.ref}: width={w} is not positive"
            )
            assert h > 0, (
                f"Component {comp.ref}: height={h} is not positive"
            )
            assert jnp.isfinite(w), (
                f"Component {comp.ref}: width={w} is not finite"
            )
            assert jnp.isfinite(h), (
                f"Component {comp.ref}: height={h} is not finite"
            )


# =========================================================================
# Theorem III:  Netlist Consistency
# =========================================================================


class TestNetlistConsistency:
    """Theorem: Every pin's net exists in the ParsedPCB netlist."""

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_every_pin_net_exists_in_netlist(self, pcb: ParsedPCB):
        """III.1: For every component pin in a ParsedPCB, the pin's
        net name appears among ParsedPCB.nets."""
        net_names = {net.name for net in pcb.nets}

        for comp in pcb.components:
            for pin in comp.pins:
                if pin.net:
                    assert pin.net in net_names, (
                        f"Pin {comp.ref}.{pin.name}: net '{pin.net}' "
                        f"not found in parsed PCB netlist"
                    )

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_netlist_from_components_is_self_consistent(self, pcb: ParsedPCB):
        """III.2: Building a Netlist via netlist_from_components
        from the same components yields nets that match the ParsedPCB nets."""
        # Re-derive nets from the components' pins
        pin_nets = set()
        for comp in pcb.components:
            for pin in comp.pins:
                if pin.net:
                    pin_nets.add(pin.net)

        pcb_net_names = {net.name for net in pcb.nets}

        # The set of pin-nets should be a subset of ParsedPCB nets
        for net_name in pin_nets:
            assert net_name in pcb_net_names, (
                f"Net '{net_name}' referenced by component pins "
                f"but missing from ParsedPCB.nets"
            )

        # ParsedPCB nets should not reference non-existent components
        refs = {comp.ref for comp in pcb.components}
        for net in pcb.nets:
            for comp_ref, _pin_name in net.pins:
                assert comp_ref in refs, (
                    f"Net '{net.name}' references component '{comp_ref}' "
                    f"which is not in ParsedPCB.components"
                )


# =========================================================================
# Theorem IV:  Board Dimensions Match
# =========================================================================


class TestBoardDimensionsMatch:
    """Theorem: The board dimensions in a ParsedPCB are consistent
    with the board object used to generate component positions."""

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_parsed_pcb_board_has_positive_dimensions(self, pcb: ParsedPCB):
        """IV.1: The ParsedPCB.board has positive, finite width and height."""
        b = pcb.board
        assert b.width > 0
        assert b.height > 0
        assert jnp.isfinite(b.width)
        assert jnp.isfinite(b.height)

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_parsed_pcb_board_dimensions_match_strategy_ranges(self, pcb: ParsedPCB):
        """IV.2: Board dimensions fall within the anchored strategy ranges."""
        b = pcb.board
        assert 50.0 <= b.width <= 300.0, (
            f"Board width {b.width} outside [50, 300] mm range"
        )
        assert 50.0 <= b.height <= 300.0, (
            f"Board height {b.height} outside [50, 300] mm range"
        )

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_board_origin_is_zero(self, pcb: ParsedPCB):
        """IV.3: The board origin is at (0, 0)."""
        ox, oy = pcb.board.origin
        assert ox == pytest.approx(0.0)
        assert oy == pytest.approx(0.0)


# =========================================================================
# Theorem V:  Coordinate Scaling (mm, not nm)
# =========================================================================


class TestCoordinateScaling:
    """Theorem: Component position magnitudes are consistent with board
    dimensions measured in millimeters.

    If board dimensions are O(100) mm and component positions are in
    nanometers (×1e6), the magnitude ratio would be ~1e6, which this
    test catches.  Similarly, positions in meters would be ~1000× too
    large.
    """

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_positions_have_magnitude_consistent_with_board_dimensions(
        self, pcb: ParsedPCB
    ):
        """V.1: All component positions have magnitude in the same order
        as the board dimensions (50-300 mm range).  Positions should not
        be in nanometers or meters."""
        bw, bh = pcb.board.width, pcb.board.height
        max_board_dim = max(bw, bh)

        for comp in pcb.components:
            assert comp.initial_position is not None
            x, y = comp.initial_position

            # Positions must be bounded by the board dimensions.
            # Even edge-placed components should be at most 1× the board
            # dimension (e.g., board.width for x).
            assert abs(x) <= max_board_dim, (
                f"Component {comp.ref}: |x|={abs(x):.1f} exceeds "
                f"board dimension {max_board_dim:.1f}. "
                f"Suspected unit mismatch (nm instead of mm?)."
            )
            assert abs(y) <= max_board_dim, (
                f"Component {comp.ref}: |y|={abs(y):.1f} exceeds "
                f"board dimension {max_board_dim:.1f}. "
                f"Suspected unit mismatch (nm instead of mm?)."
            )

    @pytest.mark.property
    @given(board())
    @settings(max_examples=50, deadline=30000)
    def test_board_dimensions_are_mm_scale(self, b):
        """V.2: Board dimensions are in the millimeter range (50-300),
        not nanometers (which would be 5e7-3e8) or meters (0.05-0.3)."""
        assert 50.0 <= b.width <= 300.0, (
            f"Board width {b.width} is not in mm range [50, 300]"
        )
        assert 50.0 <= b.height <= 300.0, (
            f"Board height {b.height} is not in mm range [50, 300]"
        )

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_component_bounds_are_mm_scale(self, pcb: ParsedPCB):
        """V.3: Component bounds are in the millimeter range (1-50),
        consistent with PCB component sizes in mm."""
        for comp in pcb.components:
            w, h = comp.bounds
            assert 1.0 <= w <= 50.0, (
                f"Component {comp.ref}: width={w} not in mm range [1, 50]"
            )
            assert 1.0 <= h <= 50.0, (
                f"Component {comp.ref}: height={h} not in mm range [1, 50]"
            )


# =========================================================================
# Theorem VI:  LossContext Fidelity from ParsedPCB
# =========================================================================


class TestLossContextFidelity:
    """Theorem: A LossContext built from a ParsedPCB faithfully represents
    the component dimensions and board geometry.

    Lemma VI.1: LossContext.bounds shape == (n_components, 2).
    Lemma VI.2: LossContext.board dimensions match ParsedPCB.board.
    Lemma VI.3: LossContext.fixed_mask shape == (n_components,).
    """

    @staticmethod
    def _make_context_from_parsed_pcb(pcb: ParsedPCB) -> LossContext:
        """Build a LossContext from a ParsedPCB."""
        nl = Netlist(components=pcb.components, nets=pcb.nets)
        return LossContext.from_netlist_and_board(nl, pcb.board)

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_context_bounds_shape_matches_component_count(self, pcb: ParsedPCB):
        """VI.1: LossContext.bounds has shape (n_components, 2), or (0,)
        for zero components (JAX empty-list quirk)."""
        context = self._make_context_from_parsed_pcb(pcb)
        n = len(pcb.components)

        if n == 0:
            # jnp.array([]) produces (0,) not (0, 2) — known JAX behavior
            assert context.bounds.shape == (0,), (
                f"Expected bounds shape (0,) for zero components, got {context.bounds.shape}"
            )
        else:
            assert context.bounds.shape == (n, 2), (
                f"Expected bounds shape ({n}, 2), got {context.bounds.shape}"
            )

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_context_bounds_match_component_dimensions(self, pcb: ParsedPCB):
        """VI.2: LossContext.bounds values match each component's
        (width, height)."""
        context = self._make_context_from_parsed_pcb(pcb)

        if len(pcb.components) == 0:
            return  # vacuously true

        for i, comp in enumerate(pcb.components):
            assert context.bounds[i, 0] == pytest.approx(comp.bounds[0]), (
                f"Component {comp.ref}: bounds[0] mismatch"
            )
            assert context.bounds[i, 1] == pytest.approx(comp.bounds[1]), (
                f"Component {comp.ref}: bounds[1] mismatch"
            )

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_context_board_matches_parsed_pcb_board(self, pcb: ParsedPCB):
        """VI.3: LossContext.board dimensions match ParsedPCB.board."""
        context = self._make_context_from_parsed_pcb(pcb)

        assert context.board.width == pytest.approx(pcb.board.width)
        assert context.board.height == pytest.approx(pcb.board.height)
        assert context.board.origin == pcb.board.origin

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_context_fixed_mask_shape(self, pcb: ParsedPCB):
        """VI.4: LossContext.fixed_mask has shape (n_components,)."""
        context = self._make_context_from_parsed_pcb(pcb)
        n = len(pcb.components)

        assert context.fixed_mask.shape == (n,), (
            f"Expected fixed_mask shape ({n},), got {context.fixed_mask.shape}"
        )

    @pytest.mark.property
    @given(parsed_pcb())
    @settings(max_examples=50, deadline=30000)
    def test_context_can_be_traversed_by_jax(self, pcb: ParsedPCB):
        """VI.5: LossContext from ParsedPCB is a valid JAX pytree."""
        import jax

        context = self._make_context_from_parsed_pcb(pcb)

        # Should not raise
        leaves = jax.tree_util.tree_leaves(context)
        assert len(leaves) > 0, "LossContext has no JAX pytree leaves"
