from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.deterministic import DeterministicPipeline
from temper_placer.deterministic.stages.setup import DRCOracleSetupStage
from temper_placer.deterministic.state import BoardState


def test_setup_stage():
    # Create a simple board
    board = Board(width=100, height=100)

    # Create a component with one pin (pad)
    pin = Pin(
        name="1",
        number="1",
        position=(2.0, 0.0),
        net="GND",
        width=1.0,
        height=1.0,
        shape="circle",
        layer="F.Cu",
    )
    comp = Component(
        ref="U1",
        footprint="TestFP",
        bounds=(5.0, 5.0),
        pins=[pin],
        initial_position=(10.0, 10.0),
        initial_rotation=1,  # 90 degrees
    )

    netlist = Netlist(components=[comp], nets=[])

    # Initial state
    initial_state = BoardState(board=board, netlist=netlist)

    # Pipeline with DRCOracleSetupStage
    pipeline = DeterministicPipeline(stages=[DRCOracleSetupStage()])

    # Run pipeline
    final_state = pipeline.run(initial_state)

    # Verify DRCOracle is present
    assert final_state.drc_oracle is not None

    # Verify pad is registered and rotated
    pads = final_state.drc_oracle.geometry.pads
    assert len(pads) == 1
    pad_obj = pads[0]

    # U1 at (10, 10), pin at (2, 0), rotated 90 deg.
    #
    # KiCad's real footprint-child rotation is R(-theta), not R(+theta) --
    # confirmed against real kicad-cli 10.0.4 pcb drc ground truth, see
    # docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md
    # Sec. 2. R(-90): (x, y) -> (y, -x). Pin offset (2, 0) -> (0, -2).
    # Absolute: (10+0, 10-2) = (10, 8).
    assert abs(pad_obj.center.x - 10.0) < 1e-6
    assert abs(pad_obj.center.y - 8.0) < 1e-6
    assert pad_obj.net == "GND"
