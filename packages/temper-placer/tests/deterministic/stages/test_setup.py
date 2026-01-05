from temper_placer.core.board import Board
from temper_placer.core.netlist import Netlist, Component, Pin
from temper_placer.deterministic.state import BoardState
from temper_placer.deterministic.pipeline import DeterministicPipeline
from temper_placer.deterministic.stages.setup import SetupStage

def test_setup_stage():
    # Create a simple board
    board = Board(width=100, height=100)
    
    # Create a component with one pin (pad)
    pin = Pin(name="1", number="1", position=(2.0, 0.0), net="GND", width=1.0, height=1.0, shape="circle", layer="F.Cu")
    comp = Component(
        ref="U1", 
        footprint="TestFP", 
        bounds=(5.0, 5.0), 
        pins=[pin], 
        initial_position=(10.0, 10.0),
        initial_rotation=1 # 90 degrees
    )
    
    netlist = Netlist(components=[comp], nets=[])
    
    # Initial state
    initial_state = BoardState(board=board, netlist=netlist)
    
    # Pipeline with SetupStage
    pipeline = DeterministicPipeline(stages=[SetupStage()])
    
    # Run pipeline
    final_state = pipeline.run(initial_state)
    
    # Verify DRCOracle is present
    assert final_state.drc_oracle is not None
    
    # Verify pad is registered and rotated
    pads = final_state.drc_oracle.geometry.pads
    assert len(pads) == 1
    pad_obj = pads[0]
    
    # U1 at (10, 10), pin at (2, 0), rotated 90 deg -> relative (0, 2) -> absolute (10, 12)
    assert abs(pad_obj.center.x - 10.0) < 1e-6
    assert abs(pad_obj.center.y - 12.0) < 1e-6
    assert pad_obj.net == "GND"
