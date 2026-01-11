import sys
from pathlib import Path

HEADER = """(kicad_pcb (version 20221018) (generator temper_mvb_gen)
  (general
    (thickness 1.6)
  )
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (44 "Edge.Cuts" user)
  )
  (setup
    (pad_to_mask_clearance 0.1)
  )
"

def get_footer(width=10, height=10):
    return f"""
  (gr_line (start 0 0) (end {width} 0) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start {width} 0) (end {width} {height}) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start {width} {height}) (end 0 {height}) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 0 {height}) (end 0 0) (layer "Edge.Cuts") (width 0.1))
)
"

def generate_mvb_level_0(output_path: Path):
    nets = """
  (net 0 "")
  (net 1 "GND")
  (net 2 "VCC")
"
    components = """
  (footprint "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical" (layer "F.Cu")
    (tedit 0) (tstamp 00000000-0000-0000-0000-000000000001)
    (at 2.5 5 0)
    (property "Reference" "J1")
    (property "Value" "Conn_01x02")
    (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 1 "GND"))
    (pad "2" thru_hole oval (at 0 2.54) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 2 "VCC"))
  )

  (footprint "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical" (layer "F.Cu")
    (tedit 0) (tstamp 00000000-0000-0000-0000-000000000002)
    (at 7.5 5 0)
    (property "Reference" "J2")
    (property "Value" "Conn_01x02")
    (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 1 "GND"))
    (pad "2" thru_hole oval (at 0 2.54) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 2 "VCC"))
  )
"
    content = HEADER + nets + components + get_footer()
    output_path.write_text(content)
    print(f"Generated {output_path}")

def generate_mvb_level_1(output_path: Path):
    # Level 1: Basic Routing (4 comps, 6 nets)
    nets = """
  (net 0 "")
  (net 1 "GND")
  (net 2 "VCC")
  (net 3 "SIG1")
  (net 4 "SIG2")
  (net 5 "SIG3")
  (net 6 "SIG4")
"
    components = """
  (footprint "Connector_PinHeader_2.54mm:PinHeader_2x04_P2.54mm_Vertical" (layer "F.Cu")
    (tedit 0) (tstamp 00000000-0000-0000-0000-000000000011)
    (at 2.5 5 0)
    (property "Reference" "J1")
    (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 1 "GND"))
    (pad "2" thru_hole oval (at 2.54 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 2 "VCC"))
    (pad "3" thru_hole oval (at 0 2.54) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 3 "SIG1")),
    (pad "4" thru_hole oval (at 2.54 2.54) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 4 "SIG2")),
    (pad "5" thru_hole oval (at 0 5.08) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 5 "SIG3")),
    (pad "6" thru_hole oval (at 2.54 5.08) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 6 "SIG4")),
  )
  
  (footprint "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical" (layer "F.Cu")
    (tedit 0) (tstamp 00000000-0000-0000-0000-000000000012)
    (at 7.5 2 0)
    (property "Reference" "J2")
    (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 1 "GND")),
    (pad "2" thru_hole oval (at 0 2.54) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 3 "SIG1")),
  )

  (footprint "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical" (layer "F.Cu")
    (tedit 0) (tstamp 00000000-0000-0000-0000-000000000013)
    (at 7.5 5 0)
    (property "Reference" "J3")
    (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 2 "VCC")),
    (pad "2" thru_hole oval (at 0 2.54) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 4 "SIG2")),
  )
  
   (footprint "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical" (layer "F.Cu")
    (tedit 0) (tstamp 00000000-0000-0000-0000-000000000014)
    (at 7.5 8 0)
    (property "Reference" "J4")
    (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 5 "SIG3")),
    (pad "2" thru_hole oval (at 0 2.54) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 6 "SIG4")),
  )
"
    content = HEADER + nets + components + get_footer(width=15, height=15)
    output_path.write_text(content)
    print(f"Generated {output_path}")

def generate_mvb_level_2(output_path: Path):
    # Level 2: Layer Transition (Crossing Nets)
    nets = """
  (net 0 "")
  (net 1 "N1")
  (net 2 "N2")
  (net 3 "N3")
  (net 4 "N4")
"
    components = """
  (footprint "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical" (layer "F.Cu")
    (tedit 0) (tstamp 00000000-0000-0000-0000-000000000021)
    (at 2.5 2.5 0)
    (property "Reference" "J1")
    (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 1 "N1")),
    (pad "2" thru_hole oval (at 2.54 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 2 "N2")),
    (pad "3" thru_hole oval (at 5.08 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 3 "N3")),
    (pad "4" thru_hole oval (at 7.62 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 4 "N4")),
  )
  
  (footprint "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical" (layer "F.Cu")
    (tedit 0) (tstamp 00000000-0000-0000-0000-000000000022)
    (at 2.5 7.5 0)
    (property "Reference" "J2")
    (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 4 "N4")),
    (pad "2" thru_hole oval (at 2.54 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 3 "N3")),
    (pad "3" thru_hole oval (at 5.08 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 2 "N2")),
    (pad "4" thru_hole oval (at 7.62 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 1 "N1")),
  )
"
    content = HEADER + nets + components + get_footer(width=15, height=10)
    output_path.write_text(content)
    print(f"Generated {output_path}")

def generate_mvb_level_3(output_path: Path):
    # Level 3: Zone Introduction
    nets = """
  (net 0 "")
  (net 1 "GND")
  (net 2 "SIG")
  (net 3 "HV")
"
    components = """
  (footprint "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical" (layer "F.Cu")
    (tedit 0) (tstamp 00000000-0000-0000-0000-000000000031)
    (at 2.5 5 0)
    (property "Reference" "J1")
    (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 1 "GND")),
    (pad "2" thru_hole oval (at 0 2.54) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 2 "SIG")),
  )
  
  (footprint "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical" (layer "F.Cu")
    (tedit 0) (tstamp 00000000-0000-0000-0000-000000000032)
    (at 12.5 5 0)
    (property "Reference" "J2")
    (pad "1" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 1 "GND")),
    (pad "2" thru_hole oval (at 0 2.54) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net 2 "SIG")),
  )
"
    zone = """
  (zone (net 3) (net_name "HV") (layer "F.Cu") (tstamp 00000000-0000-0000-0000-000000000033) (hatch edge 0.5)
    (connect_pads thermal_reliefs (clearance 3.0))
    (min_thickness 0.25)
    (filled_areas_thickness no)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon
      (pts
        (xy 5 0) (xy 10 0) (xy 10 10) (xy 5 10)
      )
    )
  )
"
    content = HEADER + nets + components + zone + get_footer(width=15, height=10)
    output_path.write_text(content)
    print(f"Generated {output_path}")

def generate_mvb_level_4(output_path: Path):
    # Level 4: Mixed Complexity
    nets_str = "\n  (net 0 "")"
    for i in range(1, 21):
        nets_str += f"\n  (net {i} \"N{i}\")"
    
    fine_pitch_fp = """
  (footprint "Package_SO:SOIC-10_3.9x4.9mm_P0.5mm" (layer "F.Cu")
    (tedit 0) (tstamp 00000000-0000-0000-0000-000000000041)
    (at 10 10 0)
    (property "Reference" "U1")
    (pad "1" smd rect (at -2 -2.25) (size 1.5 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 1 "N1")),
    (pad "2" smd rect (at -2 -1.75) (size 1.5 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 2 "N2")),
    (pad "3" smd rect (at -2 -1.25) (size 1.5 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 3 "N3")),
    (pad "4" smd rect (at -2 -0.75) (size 1.5 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 4 "N4")),
    (pad "5" smd rect (at -2 -0.25) (size 1.5 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 5 "N5")),
    (pad "6" smd rect (at 2 0.25) (size 1.5 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 6 "N6")),
    (pad "7" smd rect (at 2 0.75) (size 1.5 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 7 "N7")),
    (pad "8" smd rect (at 2 1.25) (size 1.5 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 8 "N8")),
    (pad "9" smd rect (at 2 1.75) (size 1.5 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 9 "N9")),
    (pad "10" smd rect (at 2 2.25) (size 1.5 0.3) (layers "F.Cu" "F.Paste" "F.Mask") (net 10 "N10")),
  )
"
    headers = ""
    for i in range(1, 10):
        # 9 headers (J2-J10), connecting to nets 1-18 roughly
        # Net i connects to Net i+10
        # Wait, nets go up to 20.
        n1 = i
        n2 = i+10 if i+10 <= 20 else 0
        headers += f"\n  (footprint \"Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical\" (layer \"F.Cu\")\n    (tedit 0) (tstamp 00000000-0000-0000-0000-00000000004{i+1})\n    (at {2 + ((i-1)%3)*8} {2 + ((i-1)//3)*8} 0)\n    (property \"Reference\" \"J{i+1}\")\n    (pad \"1\" thru_hole rect (at 0 0) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net {n1} \"N{n1}\"))\n    (pad \"2\" thru_hole oval (at 0 2.54) (size 1.7 1.7) (drill 1.0) (layers *.Cu *.Mask) (net {n2} \"N{n2}\"))\n  )"
    
    zone = """
  (zone (net 20) (net_name "N20") (layer "B.Cu") (tstamp 00000000-0000-0000-0000-00000000004X) (hatch edge 0.5)
    (connect_pads thermal_reliefs (clearance 0.5))
    (min_thickness 0.25)
    (filled_areas_thickness no)
    (fill yes (thermal_gap 0.5) (thermal_bridge_width 0.5))
    (polygon
      (pts
        (xy 5 5) (xy 15 5) (xy 15 15) (xy 5 15)
      )
    )
  )
"

    content = HEADER + nets_str + fine_pitch_fp + headers + zone + get_footer(width=20, height=20)
    output_path.write_text(content)
    print(f"Generated {output_path}")

def main():
    output_dir = Path("test-boards/mvb")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    generate_mvb_level_0(output_dir / "mvb_level_0.kicad_pcb")
    generate_mvb_level_1(output_dir / "mvb_level_1.kicad_pcb")
    generate_mvb_level_2(output_dir / "mvb_level_2.kicad_pcb")
    generate_mvb_level_3(output_dir / "mvb_level_3.kicad_pcb")
    generate_mvb_level_4(output_dir / "mvb_level_4.kicad_pcb")

if __name__ == "__main__":
    main()
