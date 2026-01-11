
import sys
from pathlib import Path
import re

# Add root to sys.path to import add_power_planes
sys.path.append(str(Path(__file__).parent.parent))
from add_power_planes import add_unified_gnd_plane

def test_add_unified_gnd_plane_thermal_relief(tmp_path):
    """Verify that add_unified_gnd_plane adds thermal relief to the zone."""
    input_pcb = tmp_path / "input.kicad_pcb"
    output_pcb = tmp_path / "output.kicad_pcb"
    
    # Minimal KiCad PCB content with a GND net
    content = """(kicad_pcb (version 20211014)
  (net 1 "GND")
  (gr_rect (start 0 0) (end 100 150) (layer "Edge.Cuts") (width 0.1))
)"""
    input_pcb.write_text(content)
    
    add_unified_gnd_plane(input_pcb, output_pcb)
    
    output_content = output_pcb.read_text()
    
    # Check if connect_pads thermal_reliefs is present
    assert "(connect_pads thermal_reliefs (clearance 0.3))" in output_content
    # Check if fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5) is present
    assert "(fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))" in output_content

if __name__ == "__main__":
    import pytest
    pytest.main([__file__])
