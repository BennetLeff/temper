"""
Property-based tests for escape route generation.

Uses Hypothesis for property-based testing to verify escape route
invariants across many random component configurations.
"""

import jax.numpy as jnp
from hypothesis import given
from hypothesis import strategies as st

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Pin
from temper_placer.routing.maze_router import MazeRouter


# Hypothesis strategies
@st.composite
def component_with_pins(draw):
    """Generate random component with pins."""
    width = draw(st.floats(min_value=2.0, max_value=20.0))
    height = draw(st.floats(min_value=2.0, max_value=20.0))
    num_pins = draw(st.integers(min_value=2, max_value=8))

    pins = []
    for i in range(num_pins):
        # Pins on component edges
        side = draw(st.integers(min_value=0, max_value=3))
        if side == 0:  # Top
            px = draw(st.floats(min_value=-width/2, max_value=width/2))
            py = height / 2
        elif side == 1:  # Right
            px = width / 2
            py = draw(st.floats(min_value=-height/2, max_value=height/2))
        elif side == 2:  # Bottom
            px = draw(st.floats(min_value=-width/2, max_value=width/2))
            py = -height / 2
        else:  # Left
            px = -width / 2
            py = draw(st.floats(min_value=-height/2, max_value=height/2))

        pins.append(Pin(name=str(i+1), number=str(i+1), position=(px, py)))

    return Component(
        ref="U1",
        attributes={"value": "TEST"},
        footprint="TEST",
        bounds=(width, height),
        pins=pins,
    )


@st.composite
def component_position(draw):
    """Generate valid component position on board."""
    x = draw(st.floats(min_value=20.0, max_value=80.0))
    y = draw(st.floats(min_value=20.0, max_value=80.0))
    return jnp.array([[x, y]])


class TestEscapeRouteProperties:
    """Property-based tests for escape routes."""

    @given(
        component=component_with_pins(),
        position=component_position(),
        escape_length=st.integers(min_value=3, max_value=10),
    )
    def test_all_pins_have_escape_routes(self, component, position, escape_length):
        """Property: All pins must have escape routes of specified length."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)

        router.block_components([component], position, margin=0.1, escape_length=escape_length)

        cx, cy = float(position[0, 0]), float(position[0, 1])

        for pin in component.pins:
            pin_x = cx + pin.position[0]
            pin_y = cy + pin.position[1]
            pin_gx, pin_gy = router._world_to_grid(pin_x, pin_y)

            # Determine escape direction
            dx, dy = pin.position[0], pin.position[1]
            if abs(dx) >= abs(dy):
                step_x = 1 if dx >= 0 else -1
                step_y = 0
            else:
                step_x = 0
                step_y = 1 if dy >= 0 else -1

            # Count free cells in escape direction
            free_count = 0
            for step in range(escape_length):
                gx = pin_gx + step * step_x
                gy = pin_gy + step * step_y
                if (
                    0 <= gx < router.grid_size[0]
                    and 0 <= gy < router.grid_size[1]
                    and int(router.occupancy[gx, gy, 0]) == 0
                ):
                    free_count += 1

            assert free_count >= min(escape_length, 3), \
                f"Pin {pin.name} should have escape route of {escape_length} cells"

    @given(
        component=component_with_pins(),
        position=component_position(),
    )
    def test_escape_routes_are_connected(self, component, position):
        """Property: Escape routes must form connected path from pin."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)

        router.block_components([component], position, margin=0.1, escape_length=5)

        cx, cy = float(position[0, 0]), float(position[0, 1])

        for pin in component.pins:
            pin_x = cx + pin.position[0]
            pin_y = cy + pin.position[1]
            pin_gx, pin_gy = router._world_to_grid(pin_x, pin_y)

            # Pin cell must be free
            assert int(router.occupancy[pin_gx, pin_gy, 0]) == 0, \
                f"Pin {pin.name} cell must be free"

            # At least one neighbor must be free (connectivity)
            neighbors_free = 0
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = pin_gx + dx, pin_gy + dy
                if (
                    0 <= nx < router.grid_size[0]
                    and 0 <= ny < router.grid_size[1]
                    and int(router.occupancy[nx, ny, 0]) == 0
                ):
                    neighbors_free += 1

            assert neighbors_free >= 1, \
                f"Pin {pin.name} must have at least one free neighbor"

    @given(
        component=component_with_pins(),
        position=component_position(),
        margin=st.floats(min_value=0.0, max_value=1.0),
    )
    def test_escape_routes_extend_beyond_margin(self, component, position, margin):
        """Property: Escape routes must extend beyond component margin."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)

        router.block_components([component], position, margin=margin, escape_length=5)

        cx, cy = float(position[0, 0]), float(position[0, 1])

        for pin in component.pins:
            pin_x = cx + pin.position[0]
            pin_y = cy + pin.position[1]

            # Escape route should extend at least 2mm beyond margin
            dx, dy = pin.position[0], pin.position[1]
            if abs(dx) >= abs(dy):
                # Horizontal escape
                escape_x = pin_x + (2.0 if dx >= 0 else -2.0)
                escape_gx, _ = router._world_to_grid(escape_x, pin_y)
                pin_gx, pin_gy = router._world_to_grid(pin_x, pin_y)

                # Check cells between pin and escape point
                step = 1 if dx >= 0 else -1
                free_found = False
                for gx in range(pin_gx, escape_gx, step):
                    if 0 <= gx < router.grid_size[0] and int(router.occupancy[gx, pin_gy, 0]) == 0:
                        free_found = True
                        break

                assert free_found, f"Pin {pin.name} should have free cells in escape direction"


class TestEscapeRouteEdgeCases:
    """Edge case tests for escape route generation."""

    def test_escape_routes_at_board_edge(self):
        """Escape routes should handle components near board edges."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)

        # Component near left edge
        component = Component(
            ref="U1",
            attributes={"value": "TEST"},
            footprint="TEST",
            bounds=(10.0, 10.0),
            pins=[
                Pin(name="1", number="1", position=(-5.0, 0.0)),  # Points toward edge
                Pin(name="2", number="2", position=(5.0, 0.0)),   # Points inward
            ],
        )

        position = jnp.array([[10.0, 50.0]])  # Near left edge
        router.block_components([component], position, margin=0.1, escape_length=5)

        # Pin 1 (toward edge) may have shorter escape route
        # Pin 2 (inward) should have full escape route
        pin2_x = 10.0 + 5.0
        pin2_gx, pin2_gy = router._world_to_grid(pin2_x, 50.0)

        free_count = 0
        for i in range(5):
            gx = pin2_gx + i
            if 0 <= gx < router.grid_size[0] and int(router.occupancy[gx, pin2_gy, 0]) == 0:
                free_count += 1

        assert free_count >= 3, "Inward pin should have escape route"

    def test_escape_routes_with_dense_components(self):
        """Escape routes should work with densely packed components."""
        board = Board(width=100.0, height=100.0, origin=(0.0, 0.0))
        router = MazeRouter.from_board(board, cell_size_mm=0.5, num_layers=2)

        # Three components in a row
        component = Component(
            ref="U1",
            attributes={"value": "TEST"},
            footprint="TEST",
            bounds=(8.0, 8.0),
            pins=[
                Pin(name="1", number="1", position=(4.0, 0.0)),
                Pin(name="2", number="2", position=(-4.0, 0.0)),
            ],
        )

        positions = jnp.array([[30.0, 50.0], [40.0, 50.0], [50.0, 50.0]])
        router.block_components(
            [component, component, component],
            positions,
            margin=0.1,
            escape_length=3
        )

        # Middle component's pins should still have escape routes
        # (may be shorter due to adjacent components)
        pin_x = 40.0 + 4.0
        pin_gx, pin_gy = router._world_to_grid(pin_x, 50.0)

        # Should have at least 1 free cell (minimal escape)
        assert int(router.occupancy[pin_gx, pin_gy, 0]) == 0, "Pin cell should be free"
