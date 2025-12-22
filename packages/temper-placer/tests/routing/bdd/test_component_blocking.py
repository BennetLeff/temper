"""
BDD specifications for MazeRouter component blocking behavior.

These specs define the expected behavior for how components should block
routing grid cells, including margin requirements, layer-specific blocking,
and escape route generation.
"""

import pytest
from pytest_bdd import scenarios, given, when, then, parsers
import jax.numpy as jnp

from temper_placer.routing.maze_router import MazeRouter, GridCell
from temper_placer.core.netlist import Component, Pin
from temper_placer.core.board import Board


# Load all scenarios from feature file
scenarios('../features/component_blocking.feature')


@pytest.fixture
def board():
    """Standard test board."""
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        layer_count=2,
    )


@pytest.fixture
def router(board):
    """Router with 1mm cell size."""
    return MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)


@pytest.fixture
def component():
    """Standard test component (10mm x 10mm)."""
    return Component(
        ref="U1",
        value="TEST",
        footprint="TEST_10x10",
        bounds=(10.0, 10.0),
        pins=[
            Pin(name="1", number="1", position=(5.0, 0.0)),
            Pin(name="2", number="2", position=(-5.0, 0.0)),
            Pin(name="3", number="3", position=(0.0, 5.0)),
            Pin(name="4", number="4", position=(0.0, -5.0)),
        ],
    )


@given("a router with default blocking margin")
def router_default_margin(router):
    """Router with default 0.5mm margin."""
    return router


@given(parsers.parse("a router with {margin:f}mm blocking margin"))
def router_custom_margin(board, margin):
    """Router with custom margin."""
    router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
    router.blocking_margin = margin
    return router


@given(parsers.parse("a component at position ({x:f}, {y:f})"))
def component_at_position(component, x, y):
    """Component positioned at given coordinates."""
    return (component, jnp.array([[x, y]]))


@when("I block the component on all layers")
def block_component_all_layers(router, component_at_position):
    """Block component using default behavior (all layers)."""
    comp, pos = component_at_position
    router.block_components([comp], pos, margin=router.blocking_margin)


@when("I block the component on its actual layer only")
def block_component_single_layer(router, component_at_position):
    """Block component on single layer."""
    comp, pos = component_at_position
    router.block_components([comp], pos, margin=router.blocking_margin, layer_specific=True)


@then(parsers.parse("cell ({x:d}, {y:d}) on layer {layer:d} should be blocked"))
def cell_should_be_blocked(router, x, y, layer):
    """Verify cell is blocked."""
    assert int(router.occupancy[x, y, layer]) == 1, \
        f"Cell ({x}, {y}) on layer {layer} should be blocked but is {router.occupancy[x, y, layer]}"


@then(parsers.parse("cell ({x:d}, {y:d}) on layer {layer:d} should be free"))
def cell_should_be_free(router, x, y, layer):
    """Verify cell is free."""
    assert int(router.occupancy[x, y, layer]) == 0, \
        f"Cell ({x}, {y}) on layer {layer} should be free but is {router.occupancy[x, y, layer]}"


@then(parsers.parse("pin {pin_num:d} should have an escape route of at least {length:d} cells"))
def pin_has_escape_route(router, component_at_position, pin_num, length):
    """Verify pin has escape route of minimum length."""
    comp, pos = component_at_position
    cx, cy = float(pos[0, 0]), float(pos[0, 1])
    pin = comp.pins[pin_num - 1]
    
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
    for step in range(length):
        gx = pin_gx + step * step_x
        gy = pin_gy + step * step_y
        if 0 <= gx < router.grid_size[0] and 0 <= gy < router.grid_size[1]:
            if int(router.occupancy[gx, gy, 0]) == 0:
                free_count += 1
    
    assert free_count >= length, \
        f"Pin {pin_num} should have {length} free cells in escape route, found {free_count}"


@then(parsers.parse("the blocked area should be {width:d}x{height:d} cells"))
def verify_blocked_area_size(router, width, height):
    """Verify total blocked area matches expected size."""
    blocked_cells = jnp.sum(router.occupancy[:, :, 0] == 1)
    expected = width * height
    assert int(blocked_cells) == expected, \
        f"Expected {expected} blocked cells, found {blocked_cells}"
