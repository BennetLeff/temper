import pytest
from temper_placer.core.netlist import Net
from temper_placer.deterministic.stages.layer_assignment import LayerAssignmentStage, LayerAssignment
from temper_placer.deterministic.state import BoardState
from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist

def test_gnd_assigned_to_inner_plane():
    net = Net('GND', pins=[('C1', '2'), ('U1', 'GND')], net_class='Ground')
    stage = LayerAssignmentStage(net_classes={'GND': 'Ground'})
    state = BoardState(netlist=Netlist(nets=[net], components=[]))
    
    result = stage.run(state)
    assignment = result.layer_assignments[0]
    
    assert assignment.net_name == 'GND'
    assert assignment.layer == 1  # In1.Cu
    assert assignment.is_plane == True

def test_power_assigned_to_inner_plane():
    net = Net('+3V3', pins=[('C1', '1'), ('U1', 'VCC')], net_class='Power')
    stage = LayerAssignmentStage(net_classes={'+3V3': 'Power'})
    state = BoardState(netlist=Netlist(nets=[net], components=[]))
    
    result = stage.run(state)
    assignment = result.layer_assignments[0]
    
    assert assignment.net_name == '+3V3'
    assert assignment.layer == 2  # In2.Cu
    assert assignment.is_plane == True

def test_signal_not_plane():
    net = Net('SIG', pins=[('U1', '1'), ('U2', '2')], net_class='Signal')
    stage = LayerAssignmentStage(net_classes={'SIG': 'Signal'})
    state = BoardState(netlist=Netlist(nets=[net], components=[]))
    
    result = stage.run(state)
    assignment = result.layer_assignments[0]
    
    assert assignment.net_name == 'SIG'
    assert assignment.layer == 0  # F.Cu
    assert assignment.is_plane == False

def test_plane_net_generates_vias_only():
    from temper_placer.deterministic.stages.sequential_routing import SequentialRoutingStage
    from temper_placer.deterministic.stages.clearance_grid import ClearanceGrid
    from temper_placer.core.netlist import Component, Pin
    
    # Setup state
    p1 = Pin(name='1', number='1', position=(0,0))
    p2 = Pin(name='2', number='2', position=(0,0))
    c1 = Component(ref='C1', footprint='C', bounds=(1,1), pins=[p1], initial_position=(10, 10))
    c2 = Component(ref='C2', footprint='C', bounds=(1,1), pins=[p2], initial_position=(20, 20))
    net = Net('GND', pins=[('C1', '1'), ('C2', '2')])
    
    # Mock layer assignment with is_plane=True
    assignments = (LayerAssignment(net_name='GND', layer=1, is_plane=True),)
    
    board = Board(width=30, height=30)
    grid = ClearanceGrid(30, 30, 0.5, layer_count=4)
    state = BoardState(
        board=board,
        netlist=Netlist(components=[c1, c2], nets=[net]),
        grid=grid,
        layer_assignments=assignments,
        net_order=['GND']
    )
    
    stage = SequentialRoutingStage(trace_width_mm=0.2)
    result = stage.run(state)
    
    # Check that no traces were generated
    assert len(result.routes) == 0
    
    # Check that vias were generated (one for each pin)
    assert len(result.vias) == 2
    
    # Check via locations
    positions = {v.position for v in result.vias}
    assert (10, 10) in positions
    assert (20, 20) in positions
