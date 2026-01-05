import pytest
from temper_placer.core.netlist import Pin
from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid, ClearanceGridStage
from temper_placer.deterministic.state import BoardState
from temper_placer.core.board import Board

def is_pth_pad(pin: Pin) -> bool:
    '''Check if pin is plated through-hole.'''
    # This will be implemented in the core Pin class, but we use it here for the test
    return getattr(pin, 'is_pth', False) or (hasattr(pin, 'drill') and pin.drill > 0)

def get_pad_mask_expansion(pin: Pin) -> float:
    '''Return mask expansion based on pad type.'''
    if is_pth_pad(pin):
        return 0.15
    return 0.1

def test_pth_pad_identified():
    # Test that we can identify PTH pads based on drill
    pth_pin = Pin(name='1', number='1', position=(0,0), shape='thru_hole')
    # We will add drill attribute to Pin
    pth_pin.drill = 1.0
    pth_pin.is_pth = True
    
    smd_pin = Pin(name='1', number='1', position=(0,0), shape='rect')
    smd_pin.drill = 0.0
    smd_pin.is_pth = False
    
    assert is_pth_pad(pth_pin) == True
    assert is_pth_pad(smd_pin) == False

def test_pth_larger_mask_expansion():
    pth_pin = Pin(name='1', number='1', position=(0,0))
    pth_pin.is_pth = True
    
    smd_pin = Pin(name='1', number='1', position=(0,0))
    smd_pin.is_pth = False
    
    assert get_pad_mask_expansion(pth_pin) == 0.15
    assert get_pad_mask_expansion(smd_pin) == 0.1

def test_pth_blocked_larger_radius():
    from temper_placer.core.netlist import Component, Netlist
    
    grid = ClearanceGrid(50, 50, 0.5, layer_count=2)
    
    # Create two components, one with PTH, one with SMD
    pth_pin = Pin(name='1', number='1', position=(0,0), shape='thru_hole')
    pth_pin.drill = 1.0
    pth_pin.is_pth = True
    
    smd_pin = Pin(name='1', number='1', position=(0,0), shape='rect')
    smd_pin.drill = 0.0
    smd_pin.is_pth = False
    
    comp_pth = Component(ref='J1', footprint='Conn', bounds=(5,5), pins=[pth_pin], initial_position=(10, 10))
    comp_smd = Component(ref='U1', footprint='SOIC', bounds=(5,5), pins=[smd_pin], initial_position=(30, 30))
    
    netlist = Netlist(components=[comp_pth, comp_smd], nets=[])
    board = Board(width=50, height=50)
    state = BoardState(board=board, netlist=netlist, placements=[('J1', (10,10)), ('U1', (30,30))])
    
    # We need to manually invoke the blocking logic or use the stage
    # But for now let's just test that the grid reflects the difference
    cell_size = 0.1
    stage = ClearanceGridStage(cell_size_mm=cell_size, layer_count=2)
    new_state = stage.run(state)
    grid = new_state.grid
    
    # Count blocked cells around J1 (PTH) and U1 (SMD)
    # Both have default pad_radius = 0.5 in the stage if not in pad_sizes
    # PTH: clearance = 0.2 + 0.125 + 0.15 = 0.475 -> total radius = 0.5 + 0.475 = 0.975
    # SMD: clearance = 0.2 + 0.125 + 0.10 = 0.425 -> total radius = 0.5 + 0.425 = 0.925
    
    def count_blocked_around(center, search_radius):
        count = 0
        cx, cy = center
        min_col = int((cx - search_radius) / cell_size)
        max_col = int((cx + search_radius) / cell_size) + 1
        min_row = int((cy - search_radius) / cell_size)
        max_row = int((cy + search_radius) / cell_size) + 1
        for r in range(min_row, max_row):
            for c in range(min_col, max_col):
                if not grid.is_available(c * cell_size + cell_size / 2, r * cell_size + cell_size / 2, layer=0):
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
    p1 = Pin(name='1', number='1', position=(0,0), is_pth=True)
    p2 = Pin(name='1', number='1', position=(0,0), is_pth=True)
    comp_j1 = Component(ref='J1', footprint='Conn', bounds=(2,2), pins=[p1], initial_position=(10, 10))
    comp_j2 = Component(ref='J2', footprint='Conn', bounds=(2,2), pins=[p2], initial_position=(20, 10))
    net1 = Net(name='NET1', pins=[('J1', '1'), ('J2', '1')])
    
    # Net 2: U1 -> U2 (SMD)
    p3 = Pin(name='1', number='1', position=(0,0), is_pth=False)
    p4 = Pin(name='1', number='1', position=(0,0), is_pth=False)
    comp_u1 = Component(ref='U1', footprint='SOIC', bounds=(2,2), pins=[p3], initial_position=(10, 30))
    comp_u2 = Component(ref='U2', footprint='SOIC', bounds=(2,2), pins=[p4], initial_position=(20, 30))
    net2 = Net(name='NET2', pins=[('U1', '1'), ('U2', '1')])
    
    netlist = Netlist(components=[comp_j1, comp_j2, comp_u1, comp_u2], nets=[net1, net2])
    
    # Setup initial state with grid
    cell_size = 0.1
    grid = ClearanceGrid(50, 50, cell_size, layer_count=2)
    state = BoardState(
        board=board, 
        netlist=netlist, 
        grid=grid, 
        net_order=['NET1', 'NET2'],
        placements=[('J1', (10,10)), ('J2', (20,10)), ('U1', (10,30)), ('U2', (20,30))]
    )
    
    # Run ClearanceGridStage first to populate grid
    state = ClearanceGridStage(cell_size_mm=cell_size).run(state)
    
    # Now run SequentialRoutingStage
    # We want to verify that when routing NET2, it respects the larger clearance of PTH pins in NET1
    stage = SequentialRoutingStage(trace_width_mm=0.2, clearance_mm=0.2)
    final_state = stage.run(state)
    
    # The grid in final_state should have NET1 and NET2 blocked
    # Check that a point just outside SMD clearance but inside PTH clearance is blocked for NET1
    # PTH clearance = 0.2 (elec) + 0.1 (width/2) + 0.15 (mask) = 0.45
    # SMD clearance = 0.2 (elec) + 0.1 (width/2) + 0.10 (mask) = 0.40
    # Pad radius = 0.5
    # Total PTH = 0.95
    # Total SMD = 0.90
    
    # Point at (10.92, 10) is 0.92 from J1:1 center.
    # 0.90 < 0.92 < 0.95.
    # So it should be blocked near J1 (PTH) but would be available if it were SMD.
    
    assert final_state.grid.is_available(10.92, 10.0, layer=0) == False
    
    # Point at (10.92, 30) is 0.92 from U1:1 center.
    # 0.92 > 0.90 (SMD total radius).
    # So it should be available near U1 (SMD) IF it wasn't for the trace itself.
    # Wait, the trace also blocks cells. NET2 is at y=30.
    # Let's check a point offset in Y.
    # Point at (10, 30.92) is 0.92 from U1:1.
    assert final_state.grid.is_available(10.0, 30.92, layer=0) == True
