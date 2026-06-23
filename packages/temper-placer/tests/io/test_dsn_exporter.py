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
    # With S=100 scale factor (resolution um 10), 100mm -> 10000, 80mm -> 8000
    assert "(boundary (rect pcb 0 0 10000 8000))" in s

def test_export_structure_4layer():
    stackup = LayerStackup.default_4layer()
    board = Board(width=50, height=50, layer_stackup=stackup)
    netlist = Netlist()
    exporter = DSNExporter(board, netlist)
    
    structure = exporter.export_structure()
    s = str(structure)
    
    # Default all_layers_signal=True marks all layers as signal for autorouting
    assert "(layer F.Cu (type signal)" in s
    assert "(layer In1.Cu (type signal)" in s
    assert "(layer In2.Cu (type signal)" in s
    assert "(layer B.Cu (type signal)" in s
    # With S=100 scale factor (resolution um 10), 50mm -> 5000
    assert "(boundary (rect pcb 0 0 5000 5000))" in s
    
    # Test that all_layers_signal=False uses original layer types
    structure_with_types = exporter.export_structure(all_layers_signal=False)
    s2 = str(structure_with_types)
    assert "(layer In1.Cu (type power)" in s2
    assert "(layer In2.Cu (type power)" in s2

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
    # Image ID now includes component ref for uniqueness
    assert "(image Package_SOIC-8_U1" in s_lib
    # Pin positions are scaled by S=100 and centered. Original pins at (2,1.5) and (-2,-1.5)
    # Center offset = (0, 0) since pins are symmetric. Scaled: 2*100=200, 1.5*100=150
    assert "(pin" in s_lib  # Basic pin check
    assert "200" in s_lib  # Scaled x position
    assert "150" in s_lib  # Scaled y position
    
    placement = exporter.export_placement()
    s_place = str(placement)
    assert "(component Package_SOIC-8_U1" in s_place
    # Position is scaled by S=100: 50*100=5000
    assert "(place U1 5000" in s_place
    assert "front 90" in s_place

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
        # Mounting holes are not exported as keepouts in export_structure
        # They are handled separately via the board model
    )
    netlist = Netlist()
    exporter = DSNExporter(board, netlist)
    
    structure = exporter.export_structure()
    s = str(structure)
    
    # Keepouts use layer name (F.Cu) instead of "signal", and are scaled by S=100
    # 10*100=1000, 20*100=2000
    assert "(keepout KO_0 (rect F.Cu 1000 1000 2000 2000))" in s
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
        # Resolution is now "um 10" (1 unit = 10 micrometers)
        assert "(resolution um 10)" in s


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


def test_deterministic_output_identical_on_repeat():
    """Two DSNExporter calls with same inputs produce identical output."""
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
        ],
        nets=[
            Net(name="SIG1", pins=[("U1", "1"), ("R1", "1")]),
            Net(name="GND", pins=[("U1", "4"), ("R1", "2")]),
        ]
    )

    exp1 = DSNExporter(board, netlist, deterministic=True)
    exp2 = DSNExporter(board, netlist, deterministic=True)

    s1 = str(exp1.export_pcb("test"))
    s2 = str(exp2.export_pcb("test"))

    assert s1 == s2


def test_deterministic_sorts_nets_alphabetically():
    """Deterministic mode sorts nets by sanitized name, not fanout."""
    board = Board(width=100, height=100)
    netlist = Netlist(
        components=[
            Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[
                Pin("1", "1", (0, 0)),
                Pin("2", "2", (0, 1)),
                Pin("3", "3", (0, 2)),
            ]),
            Component(ref="R1", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0))]),
            Component(ref="R2", footprint="0805", bounds=(2, 1), pins=[Pin("1", "1", (0, 0))]),
        ],
        nets=[
            Net(name="SIG_A", pins=[("U1", "1"), ("R1", "1")]),
            Net(name="SIG_B", pins=[("U1", "2"), ("R2", "1")]),
            Net(name="SIG_C", pins=[("U1", "3")]),
        ]
    )

    # Non-deterministic would sort by fanout (3-pin then 2-pin then 1-pin)
    exp_non_det = DSNExporter(board, netlist, deterministic=False)
    s_non = str(exp_non_det.export_network(use_net_classes=False))
    # With deterministic=False, net with most pins (SIG_A has 2, SIG_C has 1) comes later
    # Actually they're sorted by fanout then span, SIG_A and SIG_B both have 2 pins
    # In non-det mode, they should NOT be strictly alphabetical

    exp_det = DSNExporter(board, netlist, deterministic=True)
    s_det = str(exp_det.export_network(use_net_classes=False))

    # Deterministic: alphabetical order: SIG_A, SIG_B, SIG_C
    idx_a = s_det.index("SIG_A")
    idx_b = s_det.index("SIG_B")
    idx_c = s_det.index("SIG_C")
    assert idx_a < idx_b < idx_c


def test_deterministic_embedded_schema_hash():
    """Deterministic mode embeds schema-version header."""
    board = Board(width=100, height=100)
    netlist = Netlist()
    exporter = DSNExporter(board, netlist, deterministic=True)
    s = str(exporter.export_pcb("test"))
    assert s.startswith(";schema-version: sha256:")


def test_non_deterministic_no_schema_hash():
    """Non-deterministic mode does NOT embed schema-version header."""
    board = Board(width=100, height=100)
    netlist = Netlist()
    exporter = DSNExporter(board, netlist, deterministic=False)
    s = str(exporter.export_pcb("test"))
    assert not s.startswith(";schema-version:")
