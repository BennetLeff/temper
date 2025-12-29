from temper_placer.core.board import Board, LayerStackup, Layer
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.dsn_exporter import DSNExporter
import jax.numpy as jnp

def test_export_structure_basic():
    board = Board(width=100, height=80)
    netlist = Netlist()
    exporter = DSNExporter(board, netlist)
    
    structure = exporter.export_structure()
    s = str(structure)
    
    assert "(layer F.Cu (type signal)" in s
    assert "(layer B.Cu (type signal)" in s
    assert "(boundary (rect pcb 0 0 100 80))" in s

def test_export_structure_4layer():
    stackup = LayerStackup.default_4layer()
    board = Board(width=50, height=50, layer_stackup=stackup)
    netlist = Netlist()
    exporter = DSNExporter(board, netlist)
    
    structure = exporter.export_structure()
    s = str(structure)
    
    assert "(layer F.Cu (type signal)" in s
    assert "(layer In1.Cu (type power)" in s # Plane layer
    assert "(layer In2.Cu (type power)" in s
    assert "(layer B.Cu (type signal)" in s
    assert "(boundary (rect pcb 0 0 50 50))" in s

def test_export_library_and_placement():
    board = Board(width=100, height=100)
    comp = Component(
        ref="U1", 
        footprint="Package:SOIC-8", 
        bounds=(5.0, 4.0),
        pins=[
            Pin("VCC", "8", (2.0, 1.5)),
            Pin("GND", "4", (-2.0, -1.5))
        ],
        initial_position=(50.0, 50.0),
        initial_rotation=1 # 90 deg
    )
    netlist = Netlist(components=[comp])
    
    exporter = DSNExporter(board, netlist)
    
    library = exporter.export_library()
    s_lib = str(library)
    assert "(image Package_SOIC-8" in s_lib
    assert "(outline (rect signal -2.5 -2 2.5 2))" in s_lib
    assert "(pin PS_RECT_1.5x1.5 8 (at 2 1.5))" in s_lib
    
    placement = exporter.export_placement()
    s_place = str(placement)
    assert "(component Package_SOIC-8" in s_place
    assert "(place U1 50 50 front 90)" in s_place

def test_export_network():
    board = Board(width=100, height=100)
    netlist = Netlist(
        components=[
            Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[Pin("1", "1", (0, 0))]),
            Component(ref="R1", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0))]),
        ],
        nets=[
            Net(name="SIG1", pins=[("U1", "1"), ("R1", "1")])
        ]
    )
    exporter = DSNExporter(board, netlist)
    
    network = exporter.export_network()
    s = str(network)
    assert "(net SIG1 (pins U1-1 R1-1))" in s

def test_export_structure_keepouts():
    from temper_placer.core.board import MountingHole
    board = Board(
        width=100, 
        height=100, 
        keepouts=[(10, 10, 20, 20)],
        mounting_holes=[MountingHole(position=(50, 50), diameter=3, keepout_radius=5)]
    )
    netlist = Netlist()
    exporter = DSNExporter(board, netlist)
    
    structure = exporter.export_structure()
    s = str(structure)
    
    assert "(keepout KO_0 (rect signal 10 10 20 20))" in s
    assert "(keepout HOLE_0 (rect signal 45 45 55 55))" in s
    assert "(via VIA)" in s

def test_export_pcb_full():
    board = Board(width=100, height=100)
    netlist = Netlist()
    exporter = DSNExporter(board, netlist)
    
    pcb = exporter.export_pcb("test_design")
    s = str(pcb)
    
    assert "(pcb test_design" in s
    assert "(unit mm)" in s
    assert "(structure" in s
    assert "(library" in s
    assert "(placement" in s

def test_export_wiring():
    from temper_placer.io.kicad_parser import TraceData
    board = Board(width=100, height=100)
    netlist = Netlist()
    exporter = DSNExporter(board, netlist)
    
    traces = [
        TraceData(start=(0, 0), end=(10, 10), width=0.2, layer="F.Cu", net="SIG1")
    ]
    
    wiring = exporter.export_wiring(traces)
    s = str(wiring)
    assert "(wiring (wire (path F.Cu 0.2 0 0 10 10)))" in s

def test_export_from_kicad_pcb():
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from pathlib import Path
    
    # Locate the fixture relative to this test file
    fixture_path = Path(__file__).parent.parent / "fixtures" / "minimal_board.kicad_pcb"
    if not fixture_path.exists():
        # Fallback for different run environments
        fixture_path = Path("packages/temper-placer/tests/fixtures/minimal_board.kicad_pcb")
        
    if fixture_path.exists():
        result = parse_kicad_pcb(fixture_path)
        
        exporter = DSNExporter(result.board, result.netlist)
        pcb_dsn = exporter.export_pcb("minimal_board")
        
        s = str(pcb_dsn)
        assert "(pcb minimal_board" in s
        assert "(library" in s
        assert "(placement" in s
        assert "(network" in s
        # Spot check some content
        assert "(unit mm)" in s
        assert "(resolution um 1000)" in s


def test_export_network_exclude_nets():
    """Test that exclude_nets removes specified nets from the network section."""
    board = Board(width=100, height=100)
    netlist = Netlist(
        components=[
            Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[
                Pin("1", "1", (0, 0)),
                Pin("GND", "4", (0, 1)),
            ]),
            Component(ref="R1", footprint="0805", bounds=(2, 1), pins=[
                Pin("1", "1", (0, 0)),
                Pin("2", "2", (1, 0)),
            ]),
            Component(ref="C1", footprint="0805", bounds=(2, 1), pins=[
                Pin("1", "1", (0, 0)),
                Pin("2", "2", (1, 0)),
            ]),
        ],
        nets=[
            Net(name="SIG1", pins=[("U1", "1"), ("R1", "1")]),
            Net(name="GND", pins=[("U1", "4"), ("R1", "2"), ("C1", "2")]),
            Net(name="VCC", pins=[("C1", "1")]),
        ]
    )
    exporter = DSNExporter(board, netlist)
    
    # Without exclude_nets, GND should be present
    network_with_gnd = exporter.export_network(exclude_nets=None)
    s_with = str(network_with_gnd)
    assert "(net GND" in s_with
    assert "(net SIG1" in s_with
    assert "(net VCC" in s_with
    
    # With exclude_nets={"GND"}, GND should be absent
    network_without_gnd = exporter.export_network(exclude_nets={"GND"})
    s_without = str(network_without_gnd)
    assert "(net GND" not in s_without
    assert "(net SIG1" in s_without
    assert "(net VCC" in s_without
    
    # Test with export_pcb as well
    pcb_dsn = exporter.export_pcb("test", exclude_nets={"GND"})
    s_pcb = str(pcb_dsn)
    assert "(net GND" not in s_pcb
    assert "(net SIG1" in s_pcb
