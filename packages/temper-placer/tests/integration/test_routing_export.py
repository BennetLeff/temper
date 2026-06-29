"""
End-to-end integration test for routing export.

Tests the full pipeline from routing to KiCad PCB export.
"""

import tempfile
from pathlib import Path

import jax.numpy as jnp
import pytest

from temper_placer.core.board import Board
from temper_placer.core.loop import LoopCollection
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.kicad_exporter import export_routed_pcb
from temper_placer.router_v6.adapter import MazeRouter
from temper_placer.router_v6.layer_assignment import assign_layers
from temper_placer.router_v6.net_ordering import order_nets


@pytest.fixture
def simple_test_board():
    """Create a simple test board."""
    return Board(
        width=50.0,
        height=50.0,
        origin=(0.0, 0.0),
        zones=[],
    )


@pytest.fixture
def simple_test_netlist():
    """Create a simple netlist with 2 components and 1 net."""
    components = [
        Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(5.0, 4.0),
            pins=[Pin("1", "1", (2.5, 0.0), net="SIG")],  # Right edge
            initial_position=(10.0, 25.0),
        ),
        Component(
            ref="U2",
            footprint="SOIC-8",
            bounds=(5.0, 4.0),
            pins=[Pin("1", "1", (-2.5, 0.0), net="SIG")],  # Left edge
            initial_position=(40.0, 25.0),
        ),
    ]

    nets = [Net("SIG", [("U1", "1"), ("U2", "1")])]

    return Netlist(components=components, nets=nets)


def test_end_to_end_routing_and_export(simple_test_board, simple_test_netlist):
    """Test complete routing and export pipeline.

    This test:
    1. Creates a simple board and netlist
    2. Runs the maze router
    3. Exports the result to a KiCad PCB file
    4. Verifies the output file exists and has content
    """
    board = simple_test_board
    netlist = simple_test_netlist

    # Create router
    router = MazeRouter.from_board(board, cell_size_mm=1.0, num_layers=2)

    # Get component positions
    positions = jnp.array([[10.0, 25.0], [40.0, 25.0]])

    # Block components
    router.block_components(netlist.components, positions)

    # Get routing order and assignments
    net_order = order_nets(netlist, LoopCollection())
    assignments = assign_layers(netlist)

    # Route all nets
    results = router.route_all_nets(netlist, positions, net_order, assignments)

    # Verify routing succeeded
    assert len(results) == 1
    assert "SIG" in results
    assert results["SIG"].success, f"Routing failed: {results['SIG'].failure_reason}"

    # Export to temporary PCB file
    # Note: We don't have a valid template, so this will use a minimal PCB
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "test_output.kicad_pcb"

        # For this test, we'll create a minimal PCB template
        # In real usage, this would be a proper .kicad_pcb file
        template_path = Path(tmpdir) / "template.kicad_pcb"
        _create_minimal_kicad_pcb(template_path, netlist)

        # Export routes
        result = export_routed_pcb(
            template_pcb=template_path,
            routes=results,
            output_pcb=output_path,
            cell_size=1.0,
            origin=(0.0, 0.0),
        )

        # Verify export result
        assert result.segments_added > 0, "No segments exported"
        assert result.nets_exported == 1
        assert result.nets_failed == 0
        assert output_path.exists()

        # Verify file has content
        content = output_path.read_text()
        assert len(content) > 100  # Has meaningful content
        assert "(segment" in content  # Has trace segments


def _create_minimal_kicad_pcb(path: Path, netlist: Netlist):
    """Create a minimal KiCad PCB file for testing."""
    # This is a minimal PCB file structure
    # In production, we'd use kiutils to generate this properly
    pcb_content = """(kicad_pcb (version 20221018) (generator pcbnew)

  (general
    (thickness 1.6)
  )

  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
  )

  (setup
    (pad_to_mask_clearance 0)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (plot_on_all_layers_selection 0x0000000_00000000)
      (disableapertmacros false)
      (usegerberextensions false)
      (usegerberattributes true)
      (usegerberadvancedattributes true)
      (creategerberjobfile true)
      (dashed_line_dash_ratio 12.000000)
      (dashed_line_gap_ratio 3.000000)
      (svgprecision 4)
      (plotframeref false)
      (viasonmask false)
      (mode 1)
      (useauxorigin false)
      (hpglpennumber 1)
      (hpglpenspeed 20)
      (hpglpendiameter 15.000000)
      (dxfpolygonmode true)
      (dxfimperialunits true)
      (dxfusepcbnewfont true)
      (psnegative false)
      (psa4output false)
      (plotreference true)
      (plotvalue true)
      (plotinvisibletext false)
      (sketchpadsonfab false)
      (subtractmaskfromsilk false)
      (outputformat 1)
      (mirror false)
      (drillshape 1)
      (scaleselection 1)
      (outputdirectory "")
    )
  )

  (net 0 "")
  (net 1 "SIG")

)
"""
    path.write_text(pcb_content)


@pytest.mark.skip(reason="Requires valid KiCad PCB file from fixtures - manual testing")
def test_export_with_real_pcb():
    """Integration test with a real PCB file.

    This test would use an actual .kicad_pcb file from the fixtures directory.
    Skipped by default as it requires specific fixture files.
    """
    pass
