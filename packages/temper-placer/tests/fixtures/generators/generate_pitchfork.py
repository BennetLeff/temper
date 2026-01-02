#!/usr/bin/env python3
"""
Generate Pitchfork test board for fanout unit testing.

Pitchfork is a synthetic PCB fixture with 1.27mm (50mil) pitch headers
designed to test router fanout on fine grids. The pattern resembles
a pitchfork with multiple rows of pins that require escape routing.

Run this script to regenerate the fixture:
    python3 tests/fixtures/generators/generate_pitchfork.py
"""

import uuid
from dataclasses import dataclass


from typing import Optional, List, Tuple


def generate_uuid() -> str:
    """Generate a UUID for KiCad."""
    return str(uuid.uuid4())


def generate_tstamp(index: int) -> str:
    """Generate a deterministic tstamp based on index."""
    return f"00000000-0000-0000-{index:012d}"


@dataclass
class PitchforkConfig:
    """Configuration for pitchfork board generation."""

    rows: int = 4
    cols: int = 10
    pitch_mm: float = 1.27
    header_gap_mm: float = 5.0
    board_width_mm: float = 80.0
    board_height_mm: float = 60.0
    via_drill_mm: float = 0.3
    via_size_mm: float = 0.6


class PitchforkGenerator:
    """Generator for pitchfork test board."""

    def __init__(self, config: Optional[PitchforkConfig] = None):
        if config is None:
            config = PitchforkConfig()
        self.config = config
        self.components = []
        self.nets = [""]
        self.net_index = 1
        self.comp_index = 1
        self.pin_index = 1

    def add_net(self, name: str) -> int:
        """Add a net and return its index."""
        self.nets.append(name)
        idx = self.net_index
        self.net_index += 1
        return idx

    def generate_header(self) -> str:
        """Generate KiCad PCB header."""
        return """(kicad_pcb (version 20221018) (generator pitchfork)

  (general
    (thickness 1.6)
  )

  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (32 "B.Adhes" user "B.Adhesive")
    (33 "F.Adhes" user "F.Adhesive")
    (34 "B.Paste" user)
    (35 "F.Paste" user)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (44 "Edge.Cuts" user)
    (45 "Margin" user)
    (46 "B.CrtYd" user "B.Courtyard")
    (47 "F.CrtYd" user "F.Courtyard")
    (48 "B.Fab" user)
    (49 "F.Fab" user)
  )

  (setup
    (pad_to_mask_clearance 0)
    (pcbplotparams
      (layerselection 0x00010fc_ffffffff)
      (plot_on_all_layers_selection 0x0000000_00000000)
    )
  )

"""

    def generate_nets_section(self) -> str:
        """Generate nets section."""
        lines = []
        for i, net in enumerate(self.nets):
            lines.append(f'  (net {i} "{net}")')
        return "\n".join(lines) + "\n\n"

    def generate_conn_header(
        self,
        ref: str,
        x: float,
        y: float,
        rows: int,
        cols: int,
        pitch: float,
        rotation: float = 0,
        vertical: bool = True,
    ) -> str:
        """Generate a pin header footprint with specified rows and columns.

        Args:
            ref: Component reference (e.g., "J1")
            x: X position
            y: Y position
            rows: Number of rows
            cols: Number of columns
            pitch: Pin pitch in mm
            rotation: Rotation in degrees
            vertical: If True, pins are arranged vertically (default)
        """
        tstamp = generate_tstamp(self.comp_index)
        self.comp_index += 1

        rot_str = f" {rotation}" if rotation != 0 else ""

        lines = [
            f'  (footprint "Connector_PinHeader_2.54mm:PinHeader_1x{rows}_P2.54mm_Vertical" (layer "F.Cu")',
            f"    (tstamp {tstamp})",
            f"    (at {x} {y}{rot_str})",
            f'    (property "Reference" "{ref}")',
            f'    (property "Value" "Conn_01x{rows}")',
            f'    (property "Footprint" "Connector_PinHeader_2.54mm:PinHeader_1x{rows}_P2.54mm_Vertical")',
            f'    (path "/{tstamp}")',
        ]

        if vertical:
            for row in range(rows):
                pin_num = row + 1
                net_name = f"NET_{self.pin_index}"
                self.pin_index += 1
                if net_name not in self.nets:
                    self.add_net(net_name)
                net_idx = self.nets.index(net_name)

                pin_y = -row * pitch
                pad_size = 1.4  # 2.54mm header pad diameter
                drill = 1.0

                lines.append(
                    f'    (pad "{pin_num}" thru_hole oval (at 0 {pin_y}) '
                    f"(size {pad_size} {pad_size}) (drill {drill}) "
                    f'(layers "*.Cu" "*.Mask") (net {net_idx} "{net_name}"))'
                )
        else:
            for col in range(cols):
                pin_num = col + 1
                net_name = f"NET_{self.pin_index}"
                self.pin_index += 1
                if net_name not in self.nets:
                    self.add_net(net_name)
                net_idx = self.nets.index(net_name)

                pin_x = col * pitch

                lines.append(
                    f'    (pad "{pin_num}" thru_hole oval (at {pin_x} 0) '
                    f"(size 1.4 1.4) (drill 1.0) "
                    f'(layers "*.Cu" "*.Mask") (net {net_idx} "{net_name}"))'
                )

        lines.append("  )\n")
        return "\n".join(lines)

    def generate_board_outline(self) -> str:
        """Generate board edge cuts."""
        x_min = 0
        y_min = 0
        x_max = self.config.board_width_mm
        y_max = self.config.board_height_mm

        return f'  (gr_rect (start {x_min} {y_min}) (end {x_max} {y_max}) (layer "Edge.Cuts") (width 0.1))\n'

    def generate(self) -> str:
        """Generate the complete KiCad PCB file."""
        pitch = self.config.pitch_mm
        rows = self.config.rows
        cols = self.config.cols
        gap = self.config.header_gap_mm
        width = self.config.board_width_mm
        height = self.config.board_height_mm

        output = self.generate_header()
        output += self.generate_nets_section()

        start_x = 10.0
        start_y = height - 20.0

        for row in range(rows):
            header_x = start_x + row * (cols * pitch + gap)
            if header_x > width - 15:
                break
            y_pos = start_y
            output += self.generate_conn_header(
                ref=f"J{row + 1}",
                x=header_x,
                y=y_pos,
                rows=cols,
                cols=cols,
                pitch=pitch,
                vertical=True,
            )

        output += self.generate_board_outline()
        output += "\n)"

        return output


def main():
    """Generate the pitchfork test board."""
    import os

    generator = PitchforkGenerator()
    pcb_content = generator.generate()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "..", "pitchfork.kicad_pcb")

    with open(output_path, "w") as f:
        f.write(pcb_content)

    comp_count = generator.comp_index - 1
    net_count = len(generator.nets) - 1

    print(f"Generated {output_path}")
    print(f"  - {comp_count} pin headers")
    print(f"  - {net_count} nets")
    print(f"  - Board size: {generator.config.board_width_mm}x{generator.config.board_height_mm}mm")
    print(f"  - Pin pitch: {generator.config.pitch_mm}mm (fine grid)")


if __name__ == "__main__":
    main()
