"""
Routing strategy generator for temper-placer.

Analyzes placement and constraints to provide explicit routing instructions
for human or automated routing.
"""

from __future__ import annotations

from pathlib import Path

from temper_placer.io.config_loader import load_constraints
from temper_placer.io.kicad_parser import parse_kicad_pcb


def generate_routing_report(pcb_path: Path, constraints_path: Path) -> str:
    """Generate a detailed markdown report with routing instructions."""

    # 1. Load data
    parse_result = parse_kicad_pcb(pcb_path)
    constraints = load_constraints(constraints_path)
    netlist = parse_result.netlist

    report = []
    report.append(f"# Routing Strategy Report for {pcb_path.name}")
    report.append(
        "\nThis report provides explicit instructions for routing the Temper PCB based on the current optimized placement.\n"
    )

    # 2. Critical Net Classes
    report.append("## 1. Net Class Specifications")
    report.append("| Net Class | Trace Width | Min Clearance | Layer Preference |")
    report.append("| :--- | :--- | :--- | :--- |")
    report.append("| **HighVoltage** | 2.0 mm | 10.0 mm | Top (2oz Copper) |")
    report.append("| **Power** | 1.0 mm | 0.5 mm | Any |")
    report.append("| **Signal** | 0.25 mm | 0.25 mm | Bottom |")
    report.append("")

    # 3. High Voltage Section (HV_ZONE)
    report.append("## 2. High Voltage & Power Section (HV_ZONE)")
    report.append(
        "The HV section contains the voltage doubler and the half-bridge. Use thick traces and respect creepage."
    )
    report.append("\n**Key Instructions:**")
    report.append(
        "- **DC_BUS+ / DC_BUS-**: Route with 2.0mm minimum width. Keep these paths as short as possible between C_BUS1, C_BUS2, and the IGBTs (Q1, Q2)."
    )
    report.append(
        "- **SW_NODE**: This is the most electrically noisy net. Keep its area minimal. Connect Q1-Emitter, Q2-Collector, and J_COIL using a wide copper pour if possible."
    )
    report.append(
        "- **Isolation Barrier**: Maintain a clear 10mm gap between any HighVoltage net and the Signal nets in MCU_ZONE. Do not cross the barrier with any copper except for the isolated gate driver signals."
    )
    report.append("")

    # 4. Gate Drive Loops
    report.append("## 3. Critical Gate Drive Loops")
    report.append("Minimizing the area of these loops is critical for EMI and switching stability.")

    for loop in constraints.critical_loops:
        report.append(f"\n### Loop: {loop.name}")
        report.append(f"**Description:** {loop.description}")
        report.append(f"**Target Area:** < {loop.max_area_mm2 or 100} mm²")
        report.append("**Nets to keep together:** " + ", ".join(loop.nets))
        report.append(
            "**Instruction:** Route the GATE and Return (GND_ISO/SW_NODE) traces as a differential pair or stacked on Top/Bottom layers to cancel inductance."
        )

    # 5. Grounding Strategy
    report.append("\n## 4. Grounding & Split Planes")
    report.append("This design uses a split ground strategy (PGND and CGND).")
    report.append(
        "\n- **PGND (Power Ground)**: Keep localized to the HV_ZONE. Use a solid copper plane on the bottom layer if possible."
    )
    report.append(
        "- **CGND (Control Ground)**: Use a solid copper plane in the LV_ZONE and MCU_ZONE."
    )
    report.append(
        "- **Star Point**: Connect PGND and CGND at EXACTLY one point: (50, 40). Use a 0-ohm resistor or a narrow bridge."
    )
    report.append(
        "- **GND_ISO**: This is the floating ground for the high-side gate driver. It must be isolated from all other grounds. Route it locally around U_GATE and Q1."
    )

    # 6. Specific Pin-to-Pin Instructions
    report.append("\n## 5. Explicit Point-to-Point Instructions")
    report.append("Follow these paths strictly:")

    # Find U_GATE and Q1/Q2 positions to give coordinate advice
    try:
        u_gate_idx = netlist.get_component_index("U_GATE")
        q1_idx = netlist.get_component_index("Q1")
        q2_idx = netlist.get_component_index("Q2")

        u_gate_pos = parse_result.netlist.components[u_gate_idx].initial_position
        q1_pos = parse_result.netlist.components[q1_idx].initial_position
        q2_pos = parse_result.netlist.components[q2_idx].initial_position

        if u_gate_pos and q1_pos:
            report.append(
                f"- **High-Side Gate**: Route U_GATE (at {u_gate_pos}) to Q1 (at {q1_pos}). Use a 0.5mm trace. Keep the return path (SW_NODE) directly underneath on the Bottom layer."
            )
        if u_gate_pos and q2_pos:
            report.append(
                f"- **Low-Side Gate**: Route U_GATE (at {u_gate_pos}) to Q2 (at {q2_pos}). Use a 0.5mm trace. Keep the return path (PGND) directly underneath."
            )
    except Exception:
        report.append(
            "- *Component positions could not be extracted for specific advice. Use standard Manhattan routing.*"
        )

    # 7. Finishing Touches
    report.append("\n## 6. Finishing and Optimization")
    report.append(
        "- **Vias**: Minimize vias on HighVoltage and Power paths. Each via adds inductance and resistance."
    )
    report.append(
        "- **Teardrops**: Use teardrops on all pad-to-trace connections to improve mechanical reliability."
    )
    report.append(
        "- **Thermal Relief**: Use thermal relief for all pads connected to large copper planes to facilitate soldering."
    )

    return "\n".join(report)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("pcb", type=Path)
    parser.add_argument("constraints", type=Path)
    parser.add_argument("-o", "--output", type=Path, default=Path("ROUTING_STRATEGY.md"))
    args = parser.parse_args()

    report_md = generate_routing_report(args.pcb, args.constraints)
    args.output.write_text(report_md)
    print(f"Routing strategy report generated: {args.output}")
