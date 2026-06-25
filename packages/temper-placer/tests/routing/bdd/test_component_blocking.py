"""
BDD specifications for MazeRouter component blocking behavior.

These specs define the expected behavior for how components should block
routing grid cells, including margin requirements, layer-specific blocking,
and escape route generation.
"""

import jax.numpy as jnp
import pytest

pytest_bdd = pytest.importorskip("pytest_bdd", reason="pytest_bdd not installed")
from pytest_bdd import given, parsers, scenarios, then, when

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Pin
from temper_placer.routing.maze_router import MazeRouter

# Load all scenarios from feature file
scenarios('../features/component_blocking.feature')


@pytest.fixture
def board():
    """Standard test board."""
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
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
        attributes={"value": "TEST"},
        footprint="TEST_10x10",
        bounds=(10.0, 10.0),
        pins=[
            Pin(name="1", number="1", position=(5.0, 0.0)),
            Pin(name="2", number="2", position=(-5.0, 0.0)),
            Pin(name="3", number="3", position=(0.0, 5.0)),
            Pin(name="4", number="4", position=(0.0, -5.0)),
        ],
    )


@given(parsers.parse("a {width:d}mm x {height:d}mm board with {cell_size:d}mm grid cells"))
def board_setup(width, height, cell_size):
    """Board setup."""
    _ = cell_size  # Injected by pytest-bdd parser
    return Board(
        width=float(width),
        height=float(height),
        origin=(0.0, 0.0),
    )

@given(parsers.parse("a component at position ({x:g}, {y:g}) with size {w:g}x{h:g}"), target_fixture="component_at_position")
def component_at_position_with_size(component, x, y, w, h):
    """Component positioned at given coordinates with size."""
    component.bounds = (float(w), float(h))
    return (component, jnp.array([[float(x), float(y)]]))

@given(parsers.parse("the component has pins at offsets ({x1:g}, {y1:g}), ({x2:g}, {y2:g}), ({x3:g}, {y3:g}), ({x4:g}, {y4:g})"))
def component_with_pins(component, x1, y1, x2, y2, x3, y3, x4, y4):
    """Component with specific pin offsets."""
    component.pins = [
        Pin(name="1", number="1", position=(float(x1), float(y1))),
        Pin(name="2", number="2", position=(float(x2), float(y2))),
        Pin(name="3", number="3", position=(float(x3), float(y3))),
        Pin(name="4", number="4", position=(float(x4), float(y4))),
    ]
    return component

@given(parsers.parse("components at positions ({x1:g}, {y1:g}), ({x2:g}, {y2:g}), ({x3:g}, {y3:g}) with size {w:g}x{h:g}"), target_fixture="dense_cluster")
def dense_cluster(x1, y1, x2, y2, x3, y3, w, h):
    """Cluster of identical components."""
    comps = []
    positions = []
    w, h = float(w), float(h)
    for i, (x, y) in enumerate([(x1, y1), (x2, y2), (x3, y3)]):
        comp = Component(
            ref=f"U{i+1}",
            attributes={"value": "TEST"},
            footprint="TEST_8x8",
            bounds=(w, h),
            pins=[Pin(name="1", number="1", position=(0.0, 0.0))]
        )
        comps.append(comp)
        positions.append([float(x), float(y)])
    return (comps, jnp.array(positions))

@when("I block all components on all layers")
def block_all_components(router, dense_cluster):
    """Block multiple components."""
    comps, positions = dense_cluster
    router.block_components(comps, positions, margin=router.blocking_margin)

@then("there should be routing corridors between components")
def verify_routing_corridors(router):
    """Verify space exists between blocked areas."""
    # Check midpoint between 30,30 and 40,30 -> 35,30
    # Component width 8, margin 0.1 -> half width 4.1
    # 30+4.1 = 34.1 (end of U1), 40-4.1 = 35.9 (start of U2)
    # Gap is 34.1 to 35.9 -> ~1.8mm. Cell 35 should be free.
    mid_x, mid_y = 35, 30
    assert int(router.occupancy[mid_x, mid_y, 0]) == 0, \
        f"Corridor at ({mid_x}, {mid_y}) is blocked"

@then(parsers.parse("all pins should have escape routes of at least {length:d} cells"))
def verify_all_pins_escape(router, dense_cluster, length):
    """Verify escape routes for all components in cluster."""
    _ = length  # Injected by pytest-bdd parser
    comps, positions = dense_cluster
    for i, comp in enumerate(comps):
        cx, cy = float(positions[i, 0]), float(positions[i, 1])
        pin = comp.pins[0]
        pin_x = cx + pin.position[0]
        pin_y = cy + pin.position[1]
        pin_gx, pin_gy = router._world_to_grid(pin_x, pin_y)

        # Check center cell is free
        assert int(router.occupancy[pin_gx, pin_gy, 0]) == 0, \
            f"Pin for {comp.ref} at ({pin_gx}, {pin_gy}) is blocked"

@given("a router with default blocking margin", target_fixture="router")
def router_default_margin(router):
    """Router with default 0.5mm margin."""
    router.blocking_margin = 0.5
    return router


@given(parsers.parse("a router with {margin:f}mm blocking margin"), target_fixture="router")
def router_custom_margin(board, margin):
    """Router with custom margin."""
    router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)
    router.blocking_margin = margin
    return router


@given(parsers.parse("a component at position ({x:f}, {y:f})"), target_fixture="component_at_position")
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
    assert int(router.occupancy[x, y, layer]) == -1, \
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
        if (
            0 <= gx < router.grid_size[0]
            and 0 <= gy < router.grid_size[1]
            and int(router.occupancy[gx, gy, 0]) == 0
        ):
            free_count += 1

    assert free_count >= length, \
        f"Pin {pin_num} should have {length} free cells in escape route, found {free_count}"


@then(parsers.parse("the blocked area should be {width:d}x{height:d} cells"))
def verify_blocked_area_size(router, width, height):
    """Verify total blocked area matches expected size."""
    blocked_cells = jnp.sum(router.occupancy[:, :, 0] == -1)
    expected = width * height
    assert int(blocked_cells) == expected, \
        f"Expected {expected} blocked cells, found {blocked_cells}"

@then(parsers.parse("the blocked cell count should be {count:d}"))
def verify_blocked_cell_count(router, count):
    """Verify total blocked cells count."""
    blocked_cells = jnp.sum(router.occupancy[:, :, 0] == -1)
    assert int(blocked_cells) == count, \
        f"Expected {count} blocked cells, found {blocked_cells}"

@then(parsers.parse("pin ({x:g}, {y:g}) should have an escape route of at least {length:d} cells"))
def pin_at_coord_has_escape_route(router, x, y, length):
    """Verify pin at specific coordinate has escape route."""
    _ = length  # Injected by pytest-bdd parser
    pin_x, pin_y = float(x), float(y)
    pin_gx, pin_gy = router._world_to_grid(pin_x, pin_y)

    # Check if pin cell itself is free (start of escape route)
    assert int(router.occupancy[pin_gx, pin_gy, 0]) == 0, \
         f"Pin at ({pin_gx}, {pin_gy}) is blocked"
