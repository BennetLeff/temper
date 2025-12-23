"""
Metamorphic and contract-based tests for MazeRouter blocking behavior.

These tests verify behavioral relationships and invariants that must hold
regardless of specific input values, providing stronger confidence than
example-based tests alone.
"""

import pytest
from hypothesis import given, strategies as st, assume, settings
import jax.numpy as jnp
from typing import List, Tuple

from temper_placer.routing.maze_router import MazeRouter, GridCell
from temper_placer.core.netlist import Component, Pin
from temper_placer.core.board import Board


# Contract decorators for design-by-contract testing
def requires(condition, message="Precondition failed"):
    """Precondition decorator."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            if not condition(*args, **kwargs):
                raise AssertionError(f"{message}: {func.__name__}")
            return func(*args, **kwargs)
        return wrapper
    return decorator


def ensures(condition, message="Postcondition failed"):
    """Postcondition decorator."""
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            if not condition(result, *args, **kwargs):
                raise AssertionError(f"{message}: {func.__name__}")
            return result
        return wrapper
    return decorator


class TestBlockingMetamorphicProperties:
    """Metamorphic testing: relationships between test executions."""

    @given(
        margin1=st.floats(min_value=0.0, max_value=1.0),
        margin2=st.floats(min_value=0.0, max_value=1.0),
    )
    @settings(max_examples=500)
    def test_larger_margin_blocks_more_cells(self, margin1, margin2):
        """Metamorphic: Larger margin should block >= cells than smaller margin."""
        assume(margin2 > margin1 + 0.1)  # Ensure meaningful difference
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(10.0, 10.0),
            pins=[Pin(name="1", number="1", position=(5.0, 0.0))]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        router1 = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
        router1.block_components([component], positions, margin=margin1)
        blocked1 = jnp.sum(router1.occupancy == 1)
        
        router2 = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
        router2.block_components([component], positions, margin=margin2)
        blocked2 = jnp.sum(router2.occupancy == 1)
        
        assert blocked2 >= blocked1, \
            f"Larger margin {margin2} should block >= cells than {margin1}"

    @given(
        cell_size1=st.floats(min_value=0.2, max_value=1.0),
        cell_size2=st.floats(min_value=0.2, max_value=1.0),
    )
    @settings(max_examples=500)
    def test_finer_grid_blocks_more_cells(self, cell_size1, cell_size2):
        """Metamorphic: Finer grid should block more cells for same component."""
        assume(cell_size2 < cell_size1 * 0.8)  # Significantly finer
        
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(10.0, 10.0), pins=[]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        router1 = MazeRouter.from_board(board, cell_size_mm=cell_size1, num_layers=2)
        router1.block_components([component], positions, margin=0.5)
        blocked1 = jnp.sum(router1.occupancy == 1)
        
        router2 = MazeRouter.from_board(board, cell_size_mm=cell_size2, num_layers=2)
        router2.block_components([component], positions, margin=0.5)
        blocked2 = jnp.sum(router2.occupancy == 1)
        
        # Finer grid should have more cells blocked (approximately proportional to area ratio)
        ratio = (cell_size1 / cell_size2) ** 2
        assert blocked2 >= blocked1 * 0.8 * ratio, \
            f"Finer grid should block proportionally more cells"

    @given(
        num_components=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=200)
    def test_more_components_block_more_cells(self, num_components):
        """Metamorphic: More components should block more cells (non-overlapping)."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(5.0, 5.0), pins=[]
        )
        
        # Place components in non-overlapping grid
        components = [component] * num_components
        positions = jnp.array([
            [20.0 + (i % 3) * 20.0, 20.0 + (i // 3) * 20.0]
            for i in range(num_components)
        ])
        
        router.block_components(components, positions, margin=0.1)
        blocked = jnp.sum(router.occupancy == 1)
        
        # Should be roughly proportional to number of components
        # Each component blocks ~(5+0.2)^2 / 1.0^2 = ~27 cells
        expected_min = num_components * 20  # Conservative estimate
        assert blocked >= expected_min, \
            f"Expected at least {expected_min} blocked cells for {num_components} components"

    @given(
        escape_length=st.integers(min_value=3, max_value=10),
    )
    @settings(max_examples=200)
    def test_longer_escape_routes_free_more_cells(self, escape_length):
        """Metamorphic: Longer escape routes should free more cells."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(10.0, 10.0),
            pins=[Pin(name="1", number="1", position=(5.0, 0.0))]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        router1 = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
        router1.block_components([component], positions, margin=0.1, escape_length=3)
        blocked1 = jnp.sum(router1.occupancy == 1)
        
        router2 = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
        router2.block_components([component], positions, margin=0.1, escape_length=escape_length)
        blocked2 = jnp.sum(router2.occupancy == 1)
        
        # Longer escape routes should free more cells (or at least not block more)
        assert blocked2 <= blocked1, \
            f"Longer escape routes should not increase blocked cells"


class TestBlockingContractInvariants:
    """Contract-based testing: pre/post conditions and invariants."""

    @given(
        margin=st.floats(min_value=0.0, max_value=2.0),
        cx=st.floats(min_value=20.0, max_value=80.0),
        cy=st.floats(min_value=20.0, max_value=80.0),
    )
    @settings(max_examples=500)
    def test_contract_blocked_area_contains_component(self, margin, cx, cy):
        """Contract: All cells within component+margin must be blocked."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
        
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(10.0, 10.0), pins=[]
        )
        positions = jnp.array([[cx, cy]])
        
        router.block_components([component], positions, margin=margin)
        
        # Check all cells within component+margin are blocked
        half_w = 5.0 + margin
        half_h = 5.0 + margin
        
        for x in jnp.arange(cx - half_w, cx + half_w, 0.5):
            for y in jnp.arange(cy - half_h, cy + half_h, 0.5):
                gx, gy = router._world_to_grid(float(x), float(y))
                if 0 <= gx < router.grid_size[0] and 0 <= gy < router.grid_size[1]:
                    assert int(router.occupancy[gx, gy, 0]) == 1, \
                        f"Cell ({gx}, {gy}) within component+margin should be blocked"

    @given(
        margin=st.floats(min_value=0.0, max_value=2.0),
    )
    @settings(max_examples=300)
    def test_contract_pin_cells_are_free(self, margin):
        """Contract: Pin cells must be free (escape routes)."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
        
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(10.0, 10.0),
            pins=[
                Pin(name="1", number="1", position=(5.0, 0.0)),
                Pin(name="2", number="2", position=(-5.0, 0.0)),
                Pin(name="3", number="3", position=(0.0, 5.0)),
                Pin(name="4", number="4", position=(0.0, -5.0)),
            ]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        router.block_components([component], positions, margin=margin, escape_length=5)
        
        # All pin cells must be free
        for pin in component.pins:
            pin_x = 50.0 + pin.position[0]
            pin_y = 50.0 + pin.position[1]
            gx, gy = router._world_to_grid(pin_x, pin_y)
            
            assert int(router.occupancy[gx, gy, 0]) == 0, \
                f"Pin {pin.name} cell ({gx}, {gy}) must be free"

    @given(
        layer_specific=st.booleans(),
    )
    @settings(max_examples=200)
    def test_contract_layer_blocking_consistency(self, layer_specific):
        """Contract: Layer blocking must be consistent with specification."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(10.0, 10.0), layer=0, pins=[]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        router.block_components([component], positions, margin=0.1, layer_specific=layer_specific)
        
        # Check center cell
        gx, gy = router._world_to_grid(50.0, 50.0)
        
        if layer_specific:
            # Should only block component's layer
            assert int(router.occupancy[gx, gy, 0]) == 1, "Component layer should be blocked"
            assert int(router.occupancy[gx, gy, 1]) == 0, "Other layer should be free"
        else:
            # Should block all layers
            assert int(router.occupancy[gx, gy, 0]) == 1, "Layer 0 should be blocked"
            assert int(router.occupancy[gx, gy, 1]) == 1, "Layer 1 should be blocked"

    @given(
        num_calls=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=100)
    def test_contract_idempotence(self, num_calls):
        """Contract: Blocking same component multiple times should be idempotent."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(10.0, 10.0), pins=[]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        # Block multiple times
        for _ in range(num_calls):
            router.block_components([component], positions, margin=0.1)
        
        blocked = jnp.sum(router.occupancy == 1)
        
        # Create fresh router and block once
        router_fresh = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        router_fresh.block_components([component], positions, margin=0.1)
        blocked_fresh = jnp.sum(router_fresh.occupancy == 1)
        
        assert blocked == blocked_fresh, \
            "Multiple blocking calls should be idempotent"


class TestBlockingSymmetryProperties:
    """Symmetry and invariance properties."""

    @given(
        rotation=st.sampled_from([0, 90, 180, 270]),
    )
    @settings(max_examples=200)
    def test_square_component_rotation_invariance(self, rotation):
        """Symmetry: Square component blocking should be rotation-invariant."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        # Square component
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(10.0, 10.0), pins=[], rotation=rotation
        )
        positions = jnp.array([[50.0, 50.0]])
        
        router.block_components([component], positions, margin=0.1)
        blocked = jnp.sum(router.occupancy == 1)
        
        # Should block same number of cells regardless of rotation
        # (for square component)
        expected = 121  # Approximately (10+0.2)^2 cells
        assert abs(blocked - expected) < 10, \
            f"Square component should block ~{expected} cells at any rotation"

    @given(
        mirror=st.booleans(),
    )
    @settings(max_examples=100)
    def test_symmetric_component_mirror_invariance(self, mirror):
        """Symmetry: Symmetric component should be mirror-invariant."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        
        # Symmetric component (square with symmetric pins)
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(10.0, 10.0),
            pins=[
                Pin(name="1", number="1", position=(5.0, 0.0)),
                Pin(name="2", number="2", position=(-5.0, 0.0)),
            ]
        )
        
        router1 = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
        positions1 = jnp.array([[50.0, 50.0]])
        router1.block_components([component], positions1, margin=0.1, escape_length=5)
        blocked1 = jnp.sum(router1.occupancy == 1)
        
        # Mirror component (swap pin positions)
        if mirror:
            component_mirror = Component(
                ref="U1", footprint="TEST",
                bounds=(10.0, 10.0),
                pins=[
                    Pin(name="1", number="1", position=(-5.0, 0.0)),
                    Pin(name="2", number="2", position=(5.0, 0.0)),
                ]
            )
        else:
            component_mirror = component
        
        router2 = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)
        positions2 = jnp.array([[50.0, 50.0]])
        router2.block_components([component_mirror], positions2, margin=0.1, escape_length=5)
        blocked2 = jnp.sum(router2.occupancy == 1)
        
        assert blocked1 == blocked2, \
            "Symmetric component should block same cells when mirrored"


class TestBlockingBoundaryConditions:
    """Comprehensive boundary condition testing."""

    @given(
        edge=st.sampled_from(["left", "right", "top", "bottom"]),
        offset=st.floats(min_value=0.0, max_value=5.0),
    )
    @settings(max_examples=200)
    def test_component_at_board_edges(self, edge, offset):
        """Boundary: Components at board edges should be clipped correctly."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(10.0, 10.0), pins=[]
        )
        
        # Place component near edge
        if edge == "left":
            pos = jnp.array([[offset, 50.0]])
        elif edge == "right":
            pos = jnp.array([[100.0 - offset, 50.0]])
        elif edge == "top":
            pos = jnp.array([[50.0, offset]])
        else:  # bottom
            pos = jnp.array([[50.0, 100.0 - offset]])
        
        # Should not raise error
        router.block_components([component], pos, margin=0.5)
        
        # Verify no out-of-bounds blocking
        assert jnp.all(router.occupancy >= 0), "No negative occupancy values"
        assert jnp.all(router.occupancy <= 2), "No invalid occupancy values"

    @given(
        component_size=st.floats(min_value=0.1, max_value=50.0),
    )
    @settings(max_examples=200)
    def test_extreme_component_sizes(self, component_size):
        """Boundary: Extreme component sizes should be handled correctly."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
        
        component = Component(
            ref="U1", footprint="TEST",
            bounds=(component_size, component_size), pins=[]
        )
        positions = jnp.array([[50.0, 50.0]])
        
        # Should handle without error
        router.block_components([component], positions, margin=0.1)
        
        blocked = jnp.sum(router.occupancy == 1)
        
        # Sanity check: blocked cells should be reasonable
        max_possible = router.grid_size[0] * router.grid_size[1]
        assert 0 < blocked <= max_possible, \
            f"Blocked cells {blocked} should be in valid range [1, {max_possible}]"
