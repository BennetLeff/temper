#!/usr/bin/env python3
"""
Generate large_board.kicad_pcb fixture with 100+ components.

This script creates a synthetic PCB fixture for stress testing the placer.
The generated board resembles the Temper induction cooker board structure:
- Power section with IGBTs and drivers
- Control section with MCU and sensors
- Analog section with op-amps and references
- Connectors and miscellaneous components

Run this script to regenerate the fixture:
    python3 tests/fixtures/generate_large_board.py
"""

import random
import uuid
from dataclasses import dataclass

# Seed for reproducibility
random.seed(42)


@dataclass
class Component:
    """Component definition for generation."""

    ref: str
    value: str
    footprint: str
    footprint_lib: str
    bounds: tuple[float, float]  # (width, height) in mm
    pins: list[tuple[str, tuple[float, float], str]]  # (number, offset, net)
    position: tuple[float, float] = (0, 0)
    rotation: float = 0


def generate_qfp_pins(pin_count: int, body_size: float, pitch: float) -> list[tuple[str, float]]:
    """Generate pin positions for QFP packages."""
    pins_per_side = pin_count // 4
    edge_offset = 4.65  # Distance from center to pad

    pins = []

    # Left side (pins 1 to pins_per_side)
    for i in range(pins_per_side):
        y = -((pins_per_side - 1) / 2 - i) * pitch
        pins.append((f"-{edge_offset}", y))

    # Bottom side
    for i in range(pins_per_side):
        x = -((pins_per_side - 1) / 2 - i) * pitch
        pins.append((x, f"{edge_offset}"))

    # Right side
    for i in range(pins_per_side):
        y = ((pins_per_side - 1) / 2 - i) * pitch
        pins.append((f"{edge_offset}", y))

    # Top side
    for i in range(pins_per_side):
        x = ((pins_per_side - 1) / 2 - i) * pitch
        pins.append((x, f"-{edge_offset}"))

    return pins


# Footprint definitions with pin offsets
FOOTPRINTS = {
    "R_0402": {
        "lib": "Resistor_SMD:R_0402_1005Metric",
        "bounds": (1.0, 0.5),
        "pin_offsets": [("-0.51", 0), ("0.51", 0)],
        "pad_size": (0.54, 0.64),
    },
    "R_0603": {
        "lib": "Resistor_SMD:R_0603_1608Metric",
        "bounds": (1.6, 0.8),
        "pin_offsets": [("-0.825", 0), ("0.825", 0)],
        "pad_size": (0.8, 0.95),
    },
    "R_0805": {
        "lib": "Resistor_SMD:R_0805_2012Metric",
        "bounds": (2.0, 1.25),
        "pin_offsets": [("-0.9125", 0), ("0.9125", 0)],
        "pad_size": (1.025, 1.4),
    },
    "C_0402": {
        "lib": "Capacitor_SMD:C_0402_1005Metric",
        "bounds": (1.0, 0.5),
        "pin_offsets": [("-0.51", 0), ("0.51", 0)],
        "pad_size": (0.54, 0.64),
    },
    "C_0603": {
        "lib": "Capacitor_SMD:C_0603_1608Metric",
        "bounds": (1.6, 0.8),
        "pin_offsets": [("-0.825", 0), ("0.825", 0)],
        "pad_size": (0.8, 0.95),
    },
    "C_0805": {
        "lib": "Capacitor_SMD:C_0805_2012Metric",
        "bounds": (2.0, 1.25),
        "pin_offsets": [("-0.9125", 0), ("0.9125", 0)],
        "pad_size": (1.025, 1.4),
    },
    "C_1206": {
        "lib": "Capacitor_SMD:C_1206_3216Metric",
        "bounds": (3.2, 1.6),
        "pin_offsets": [("-1.4", 0), ("1.4", 0)],
        "pad_size": (1.6, 1.8),
    },
    "SOT23_3": {
        "lib": "Package_TO_SOT_SMD:SOT-23",
        "bounds": (3.0, 1.4),
        "pin_offsets": [("-0.95", "-1.0"), ("0.95", "-1.0"), ("0", "1.0")],
        "pad_size": (0.6, 0.7),
    },
    "SOT23_5": {
        "lib": "Package_TO_SOT_SMD:SOT-23-5",
        "bounds": (3.0, 1.75),
        "pin_offsets": [
            ("-0.95", "1.3"),
            ("0", "1.3"),
            ("0.95", "1.3"),
            ("0.95", "-1.3"),
            ("-0.95", "-1.3"),
        ],
        "pad_size": (0.6, 1.0),
    },
    "SOIC8": {
        "lib": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        "bounds": (4.0, 5.0),
        "pin_offsets": [
            ("-2.475", "-1.905"),
            ("-2.475", "-0.635"),
            ("-2.475", "0.635"),
            ("-2.475", "1.905"),
            ("2.475", "1.905"),
            ("2.475", "0.635"),
            ("2.475", "-0.635"),
            ("2.475", "-1.905"),
        ],
        "pad_size": (1.6, 0.6),
    },
    "TQFP32": {
        "lib": "Package_QFP:TQFP-32_7x7mm_P0.8mm",
        "bounds": (9.0, 9.0),
        "pin_offsets": generate_qfp_pins(32, 7.0, 0.8),
        "pad_size": (1.2, 0.4),
    },
    "TQFP48": {
        "lib": "Package_QFP:TQFP-48_7x7mm_P0.5mm",
        "bounds": (9.0, 9.0),
        "pin_offsets": generate_qfp_pins(48, 7.0, 0.5),
        "pad_size": (1.2, 0.3),
    },
    "TO220": {
        "lib": "Package_TO_SOT_THT:TO-220-3_Horizontal_TabDown",
        "bounds": (10.0, 16.0),
        "pin_offsets": [("-2.54", "0"), ("0", "0"), ("2.54", "0")],
        "pad_size": (1.8, 2.0),
        "is_tht": True,
    },
    "L_0805": {
        "lib": "Inductor_SMD:L_0805_2012Metric",
        "bounds": (2.0, 1.25),
        "pin_offsets": [("-0.9125", 0), ("0.9125", 0)],
        "pad_size": (1.025, 1.4),
    },
    "L_1206": {
        "lib": "Inductor_SMD:L_1206_3216Metric",
        "bounds": (3.2, 1.6),
        "pin_offsets": [("-1.4", 0), ("1.4", 0)],
        "pad_size": (1.6, 1.8),
    },
    "CONN_1x4": {
        "lib": "Connector_PinHeader_2.54mm:PinHeader_1x04_P2.54mm_Vertical",
        "bounds": (2.54, 10.16),
        "pin_offsets": [("0", "0"), ("0", "2.54"), ("0", "5.08"), ("0", "7.62")],
        "pad_size": (1.7, 1.7),
        "is_tht": True,
    },
    "CONN_1x6": {
        "lib": "Connector_PinHeader_2.54mm:PinHeader_1x06_P2.54mm_Vertical",
        "bounds": (2.54, 15.24),
        "pin_offsets": [
            ("0", "0"),
            ("0", "2.54"),
            ("0", "5.08"),
            ("0", "7.62"),
            ("0", "10.16"),
            ("0", "12.7"),
        ],
        "pad_size": (1.7, 1.7),
        "is_tht": True,
    },
    "D_SOD123": {
        "lib": "Diode_SMD:D_SOD-123",
        "bounds": (2.8, 1.8),
        "pin_offsets": [("-1.6", 0), ("1.6", 0)],
        "pad_size": (0.9, 1.2),
    },
}


def generate_uuid() -> str:
    """Generate a UUID for KiCad."""
    return str(uuid.uuid4())


def generate_tstamp(index: int) -> str:
    """Generate a deterministic tstamp based on index."""
    return f"00000000-0000-0000-0000-{index:012d}"


class LargeBoardGenerator:
    """Generator for large PCB fixture."""

    def __init__(self):
        self.components: list[dict] = []
        self.nets: list[str] = [""]  # Net 0 is empty
        self.net_index = 1
        self.comp_index = 1

        # Board dimensions (matches Temper spec roughly)
        self.board_width = 100.0
        self.board_height = 150.0

    def add_net(self, name: str) -> int:
        """Add a net and return its index."""
        self.nets.append(name)
        idx = self.net_index
        self.net_index += 1
        return idx

    def add_component(
        self,
        ref: str,
        value: str,
        footprint_type: str,
        x: float,
        y: float,
        rotation: float = 0,
        pin_nets: list[str] | None = None,
    ):
        """Add a component to the board."""
        fp = FOOTPRINTS[footprint_type]

        self.components.append(
            {
                "ref": ref,
                "value": value,
                "footprint": fp["lib"],
                "x": x,
                "y": y,
                "rotation": rotation,
                "pin_offsets": fp["pin_offsets"],
                "pad_size": fp["pad_size"],
                "pin_nets": pin_nets or [],
                "is_tht": fp.get("is_tht", False),
                "tstamp": generate_tstamp(self.comp_index),
            }
        )
        self.comp_index += 1

    def generate_nets(self):
        """Generate all nets for the board."""
        # Power nets
        self.add_net("GND")
        self.add_net("VCC")
        self.add_net("VCC_3V3")
        self.add_net("VCC_5V")
        self.add_net("VCC_15V")
        self.add_net("HV_DC")

        # Control signals
        self.add_net("MCU_RST")
        self.add_net("MCU_CLK")

        # SPI bus
        self.add_net("SPI_MOSI")
        self.add_net("SPI_MISO")
        self.add_net("SPI_CLK")
        self.add_net("SPI_CS1")
        self.add_net("SPI_CS2")

        # I2C bus
        self.add_net("I2C_SDA")
        self.add_net("I2C_SCL")

        # UART
        self.add_net("UART_TX")
        self.add_net("UART_RX")

        # PWM signals
        for i in range(1, 5):
            self.add_net(f"PWM{i}")

        # Gate driver signals
        for i in range(1, 5):
            self.add_net(f"GATE_H{i}")
            self.add_net(f"GATE_L{i}")

        # Analog signals
        for i in range(1, 9):
            self.add_net(f"AN{i}")

        # Generic signals
        for i in range(1, 11):
            self.add_net(f"SIG{i}")

        # Temperature sensor
        self.add_net("TEMP_OUT")
        self.add_net("TEMP_CS")

        # Current sense
        self.add_net("ISENSE_P")
        self.add_net("ISENSE_N")
        self.add_net("ISENSE_OUT")

    def generate_components(self):
        """Generate all components."""
        # ========== Resistors (50) ==========
        resistor_values = ["100", "1k", "4.7k", "10k", "22k", "47k", "100k"]
        resistor_footprints = ["R_0402", "R_0603", "R_0805"]

        # Decoupling/pullup resistors scattered around
        for i in range(1, 51):
            fp = resistor_footprints[i % 3]
            val = resistor_values[i % len(resistor_values)]
            x = 15 + (i % 8) * 10
            y = 15 + (i // 8) * 8

            # Assign to various nets
            net1 = ["VCC", "VCC_3V3", "GND", f"SIG{(i % 10) + 1}", f"AN{(i % 8) + 1}"][i % 5]
            net2 = ["GND", f"SIG{(i % 10) + 1}", "VCC_3V3", f"AN{(i % 8) + 1}", "VCC"][i % 5]

            self.add_component(f"R{i}", val, fp, x, y, pin_nets=[net1, net2])

        # ========== Capacitors (30) ==========
        cap_values = ["100pF", "1nF", "100nF", "1uF", "10uF", "22uF"]
        cap_footprints = ["C_0402", "C_0603", "C_0805", "C_1206"]

        for i in range(1, 31):
            fp = cap_footprints[i % len(cap_footprints)]
            val = cap_values[i % len(cap_values)]
            x = 15 + (i % 6) * 12
            y = 80 + (i // 6) * 6

            # Most caps are decoupling (VCC to GND)
            net1 = ["VCC", "VCC_3V3", "VCC_5V", "HV_DC"][i % 4]
            net2 = "GND"

            self.add_component(f"C{i}", val, fp, x, y, pin_nets=[net1, net2])

        # ========== ICs (10) ==========
        # MCU (TQFP48)
        mcu_nets = ["GND", "VCC_3V3", "MCU_RST", "MCU_CLK"]
        mcu_nets += ["SPI_MOSI", "SPI_MISO", "SPI_CLK", "SPI_CS1", "SPI_CS2"]
        mcu_nets += ["I2C_SDA", "I2C_SCL"]
        mcu_nets += ["UART_TX", "UART_RX"]
        mcu_nets += [f"PWM{i}" for i in range(1, 5)]
        mcu_nets += [f"AN{i}" for i in range(1, 9)]
        mcu_nets += ["GND", "VCC_3V3"] * 3  # Power pins
        mcu_nets += [f"SIG{i}" for i in range(1, 8)]
        mcu_nets = mcu_nets[:48]  # Ensure we have exactly 48
        self.add_component("U1", "STM32F103", "TQFP48", 50, 75, pin_nets=mcu_nets)

        # Op-amps (4x SOIC8)
        for i in range(2, 6):
            x = 30 + (i - 2) * 15
            y = 110
            nets = [f"AN{i - 1}", f"AN{i}", "GND", "GND", f"SIG{i - 1}", f"SIG{i}", "VCC", "VCC"]
            self.add_component(f"U{i}", "LM358", "SOIC8", x, y, pin_nets=nets)

        # Voltage regulators (SOT23-5)
        for i in range(6, 8):
            x = 75 + (i - 6) * 12
            y = 25
            nets = ["VCC", "GND", "GND", "VCC_3V3", "VCC_3V3"]
            self.add_component(f"U{i}", "AMS1117", "SOT23_5", x, y, pin_nets=nets)

        # Temperature sensor IC
        self.add_component(
            "U8",
            "MAX31865",
            "TQFP32",
            35,
            130,
            pin_nets=[
                "VCC_3V3",
                "GND",
                "SPI_MOSI",
                "SPI_MISO",
                "SPI_CLK",
                "TEMP_CS",
                "TEMP_OUT",
                "GND",
            ]
            * 4,
        )

        # Gate driver ICs (SOT23-5)
        for i in range(9, 11):
            x = 15 + (i - 9) * 25
            y = 45
            nets = ["VCC_15V", f"GATE_H{i - 8}", f"GATE_L{i - 8}", f"PWM{i - 8}", "GND"]
            self.add_component(f"U{i}", "UCC27511", "SOT23_5", x, y, pin_nets=nets)

        # ========== Inductors (5) ==========
        for i in range(1, 6):
            fp = "L_0805" if i < 3 else "L_1206"
            x = 80 + (i - 1) * 8
            y = 55
            net1 = ["VCC", "VCC_3V3", "VCC_5V", "HV_DC", "ISENSE_P"][i - 1]
            net2 = ["VCC_5V", "VCC", "VCC", "VCC_15V", "ISENSE_OUT"][i - 1]
            self.add_component(f"L{i}", "10uH", fp, x, y, pin_nets=[net1, net2])

        # ========== Connectors (5) ==========
        # Programming header
        self.add_component(
            "J1",
            "PROG",
            "CONN_1x6",
            10,
            130,
            pin_nets=["VCC_3V3", "GND", "SPI_MOSI", "SPI_MISO", "SPI_CLK", "MCU_RST"],
        )

        # Debug/UART
        self.add_component(
            "J2", "DEBUG", "CONN_1x4", 10, 110, pin_nets=["VCC_3V3", "GND", "UART_TX", "UART_RX"]
        )

        # I2C
        self.add_component(
            "J3", "I2C", "CONN_1x4", 10, 90, pin_nets=["VCC_3V3", "GND", "I2C_SDA", "I2C_SCL"]
        )

        # Power input
        self.add_component(
            "J4", "PWR_IN", "CONN_1x4", 95, 10, pin_nets=["VCC", "GND", "GND", "VCC"]
        )

        # Analog
        self.add_component(
            "J5",
            "ANALOG",
            "CONN_1x6",
            95,
            130,
            pin_nets=["AN1", "AN2", "AN3", "AN4", "GND", "VCC_3V3"],
        )

        # ========== Diodes (5) ==========
        for i in range(1, 6):
            x = 60 + (i - 1) * 8
            y = 35
            net1 = ["VCC", "VCC_3V3", "VCC_5V", "VCC_15V", "HV_DC"][i - 1]
            self.add_component(f"D{i}", "1N4148", "D_SOD123", x, y, pin_nets=[net1, "GND"])

        # ========== Transistors (5) - using SOT23_3 ==========
        for i in range(1, 6):
            x = 60 + (i - 1) * 8
            y = 20
            nets = [f"SIG{i}", "GND", f"PWM{min(i, 4)}"]
            self.add_component(f"Q{i}", "2N7002", "SOT23_3", x, y, pin_nets=nets)

    def generate_header(self) -> str:
        """Generate KiCad PCB header."""
        return """(kicad_pcb (version 20221018) (generator pcbnew)

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

    def generate_footprint(self, comp: dict) -> str:
        """Generate a single footprint."""
        ref = comp["ref"]
        value = comp["value"]
        fp = comp["footprint"]
        x = comp["x"]
        y = comp["y"]
        rot = comp["rotation"]
        tstamp = comp["tstamp"]
        pin_offsets = comp["pin_offsets"]
        pad_size = comp["pad_size"]
        pin_nets = comp["pin_nets"]
        is_tht = comp.get("is_tht", False)

        rot_str = f" {rot}" if rot != 0 else ""

        lines = [
            f'  (footprint "{fp}" (layer "F.Cu")',
            f"    (tstamp {tstamp})",
            f"    (at {x} {y}{rot_str})",
            f'    (property "Reference" "{ref}")',
            f'    (property "Value" "{value}")',
            f'    (property "Footprint" "{fp}")',
            f'    (path "/{tstamp}")',
        ]

        # Add pads
        for i, offset in enumerate(pin_offsets):
            pin_num = i + 1
            ox, oy = offset if isinstance(offset, tuple) else (offset, 0)

            # Get net for this pin
            net_name = pin_nets[i] if i < len(pin_nets) else ""
            net_idx = self.nets.index(net_name) if net_name in self.nets else 0

            # Build net string if needed
            net_str = f' (net {net_idx} "{net_name}")' if net_idx > 0 else ""

            if is_tht:
                # Through-hole pad
                shape = "rect" if i == 0 else "oval"
                lines.append(
                    f'    (pad "{pin_num}" thru_hole {shape} (at {ox} {oy}) '
                    f'(size {pad_size[0]} {pad_size[1]}) (drill 1.0) (layers "*.Cu" "*.Mask"){net_str})'
                )
            else:
                # SMD pad
                lines.append(
                    f'    (pad "{pin_num}" smd roundrect (at {ox} {oy}) '
                    f'(size {pad_size[0]} {pad_size[1]}) (layers "F.Cu" "F.Paste" "F.Mask") (roundrect_rratio 0.25){net_str})'
                )

        lines.append("  )\n")
        return "\n".join(lines)

    def generate_board_outline(self) -> str:
        """Generate board edge cuts."""
        x_min = 5.0
        y_min = 5.0
        x_max = x_min + self.board_width
        y_max = y_min + self.board_height

        return f'  (gr_rect (start {x_min} {y_min}) (end {x_max} {y_max}) (layer "Edge.Cuts") (width 0.1))\n'

    def generate(self) -> str:
        """Generate the complete KiCad PCB file."""
        self.generate_nets()
        self.generate_components()

        output = self.generate_header()
        output += self.generate_nets_section()

        for comp in self.components:
            output += self.generate_footprint(comp)

        output += self.generate_board_outline()
        output += "\n)"

        return output


def main():
    """Generate the large board fixture."""
    import os

    generator = LargeBoardGenerator()
    pcb_content = generator.generate()

    # Get the output path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "large_board.kicad_pcb")

    with open(output_path, "w") as f:
        f.write(pcb_content)

    # Count components
    comp_count = len(generator.components)
    net_count = len(generator.nets) - 1  # Exclude empty net

    print(f"Generated {output_path}")
    print(f"  - {comp_count} components")
    print(f"  - {net_count} nets")
    print(f"  - Board size: {generator.board_width}x{generator.board_height}mm")


if __name__ == "__main__":
    main()
