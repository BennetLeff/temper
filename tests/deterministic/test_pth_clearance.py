import pytest
from temper_placer.core.netlist import Pin
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid, ClearanceGridStage
from temper_placer.deterministic.state import BoardState
from temper_placer.core.board import Board


def is_pth_pad(pin: Pin) -> bool:
    """Check if pin is plated through-hole."""
    # This will be implemented in the core Pin class, but we use it here for the test
    return getattr(pin, "is_pth", False) or (hasattr(pin, "drill") and pin.drill > 0)


def get_pad_mask_expansion(pin: Pin) -> float:
    """Return mask expansion based on pad type."""
    if is_pth_pad(pin):
        return 0.15
    return 0.1


def test_pth_pad_identified():
    # Test that we can identify PTH pads based on drill
    pth_pin = Pin(name="1", number="1", position=(0, 0), shape="thru_hole")
    # We will add drill attribute to Pin
    pth_pin.drill = 1.0
    pth_pin.is_pth = True

    smd_pin = Pin(name="1", number="1", position=(0, 0), shape="rect")
    smd_pin.drill = 0.0
    smd_pin.is_pth = False

    assert is_pth_pad(pth_pin) == True
    assert is_pth_pad(smd_pin) == False


def test_pth_larger_mask_expansion():
    pth_pin = Pin(name="1", number="1", position=(0, 0))
    pth_pin.is_pth = True

    smd_pin = Pin(name="1", number="1", position=(0, 0))
    smd_pin.is_pth = False

    assert get_pad_mask_expansion(pth_pin) == 0.15
    assert get_pad_mask_expansion(smd_pin) == 0.1


def test_pth_blocked_larger_radius():
    from temper_placer.core.netlist import Component, Netlist

    grid = ClearanceGrid(50, 50, 0.5, layer_count=2)

    # Create two components, one with PTH, one with SMD
    pth_pin = Pin(name="1", number="1", position=(0, 0), shape="thru_hole")
    pth_pin.drill = 1.0
    pth_pin.is_pth = True

    smd_pin = Pin(name="1", number="1", position=(0, 0), shape="rect")
    smd_pin.drill = 0.0
    smd_pin.is_pth = False

    comp_pth = Component(
        ref="J1", footprint="Conn", bounds=(5, 5), pins=[pth_pin], initial_position=(10, 10)
    )
    comp_smd = Component(
        ref="U1", footprint="SOIC", bounds=(5, 5), pins=[smd_pin], initial_position=(30, 30)
    )

    netlist = Netlist(components=[comp_pth, comp_smd], nets=[])
    board = Board(width=50, height=50)
    state = BoardState(
        board=board, netlist=netlist, placements=[("J1", (10, 10)), ("U1", (30, 30))]
    )

    # We need to manually invoke the blocking logic or use the stage
    # But for now let's just test that the grid reflects the difference
    cell_size = 0.1
    # Use small clearance so PTH/SMD mask expansion difference is significant
    # PTH mask expansion: 0.15mm, SMD mask expansion: 0.10mm
    # Total clearance = max_clearance + mask expansion
    # PTH: 0.325 + 0.15 = 0.475, SMD: 0.325 + 0.10 = 0.425
    stage = ClearanceGridStage(
        cell_size_mm=cell_size,
        layer_count=2,
        max_clearance_mm=0.325,  # electrical clearance + half trace width
        pth_mask_expansion_mm=0.15,
        smd_mask_expansion_mm=0.10,
    )
    new_state = stage.run(state)
    grid = new_state.grid

    # Count blocked cells around J1 (PTH) and U1 (SMD)
    # Both have default pad_radius = 0.5 in the stage if not in pad_sizes
    # PTH: clearance = 0.325 + 0.15 = 0.475 -> total radius = 0.5 + 0.475 = 0.975
    # SMD: clearance = 0.325 + 0.10 = 0.425 -> total radius = 0.5 + 0.425 = 0.925

    def count_blocked_around(center, search_radius):
        count = 0
        cx, cy = center
        min_col = int((cx - search_radius) / cell_size)
        max_col = int((cx + search_radius) / cell_size) + 1
        min_row = int((cy - search_radius) / cell_size)
        max_row = int((cy + search_radius) / cell_size) + 1
        for r in range(min_row, max_row):
            for c in range(min_col, max_col):
                if not grid.is_available(
                    c * cell_size + cell_size / 2, r * cell_size + cell_size / 2, layer=0
                ):
                    count += 1
        return count

    pth_count = count_blocked_around((10, 10), 2.0)
    smd_count = count_blocked_around((30, 30), 2.0)

    # PTH should have more blocked cells due to larger mask expansion
    assert pth_count > smd_count


def test_sequential_routing_pth_clearance():
    from temper_placer.core.netlist import Component, Net, Netlist
    from temper_placer.deterministic.stages.sequential_routing import SequentialRoutingStage
    from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid

    board = Board(width=50, height=50)

    # Net 1: J1 -> J2 (PTH)
    p1 = Pin(name="1", number="1", position=(0, 0), is_pth=True)
    p2 = Pin(name="1", number="1", position=(0, 0), is_pth=True)
    comp_j1 = Component(
        ref="J1", footprint="Conn", bounds=(2, 2), pins=[p1], initial_position=(10, 10)
    )
    comp_j2 = Component(
        ref="J2", footprint="Conn", bounds=(2, 2), pins=[p2], initial_position=(20, 10)
    )
    net1 = Net(name="NET1", pins=[("J1", "1"), ("J2", "1")])

    # Net 2: U1 -> U2 (SMD)
    p3 = Pin(name="1", number="1", position=(0, 0), is_pth=False)
    p4 = Pin(name="1", number="1", position=(0, 0), is_pth=False)
    comp_u1 = Component(
        ref="U1", footprint="SOIC", bounds=(2, 2), pins=[p3], initial_position=(10, 30)
    )
    comp_u2 = Component(
        ref="U2", footprint="SOIC", bounds=(2, 2), pins=[p4], initial_position=(20, 30)
    )
    net2 = Net(name="NET2", pins=[("U1", "1"), ("U2", "1")])

    netlist = Netlist(components=[comp_j1, comp_j2, comp_u1, comp_u2], nets=[net1, net2])

    # Setup initial state with grid - use smaller cell size for better precision
    cell_size = 0.05  # 0.05mm for better discretization accuracy
    grid = ClearanceGrid(50, 50, cell_size, layer_count=2)
    state = BoardState(
        board=board,
        netlist=netlist,
        grid=grid,
        net_order=["NET1", "NET2"],
        placements=[("J1", (10, 10)), ("J2", (20, 10)), ("U1", (10, 30)), ("U2", (20, 30))],
    )

    # Run ClearanceGridStage first to populate grid with proper clearances
    # max_clearance = 0.3 (includes electrical clearance + half trace width)
    # PTH total clearance = 0.3 + 0.15 (mask) = 0.45 -> total radius = 0.5 + 0.45 = 0.95
    # SMD total clearance = 0.3 + 0.10 (mask) = 0.40 -> total radius = 0.5 + 0.40 = 0.90
    state = ClearanceGridStage(
        cell_size_mm=cell_size,
        max_clearance_mm=0.3,
        pth_mask_expansion_mm=0.15,
        smd_mask_expansion_mm=0.10,
    ).run(state)

    # Now run SequentialRoutingStage
    # We want to verify that when routing NET2, it respects the larger clearance of PTH pins in NET1
    stage = SequentialRoutingStage(trace_width_mm=0.2, clearance_mm=0.2)
    final_state = stage.run(state)

    # The grid in final_state should have pads blocked
    # PTH total radius = 0.5 + 0.45 = 0.95
    # SMD total radius = 0.5 + 0.40 = 0.90

    # Test that PTH has larger blocked radius than SMD by checking a point
    # that's inside PTH clearance but outside SMD clearance.
    # Point at (10.93, 10) is 0.93 from J1:1 center -> should be blocked (inside 0.95)
    # With cell_size=0.05, this maps to cell center ~(10.925, 10.025), dist ~0.925 < 0.95
    assert final_state.grid.is_available(10.93, 10.0, layer=0) == False

    # Point at (10.93, 30) would be 0.93 from U1:1 center
    # 0.93 > 0.90 (SMD total radius) so should be available
    # However, the trace at y=30 blocks this. Check point offset in Y instead.
    # Point at (10, 30.93) is 0.93 from U1:1 -> should be available (outside 0.90)
    assert final_state.grid.is_available(10.0, 30.93, layer=0) == True
