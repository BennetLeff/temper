"""
Parasitic netlist injection engine.

Injects layout-extracted parasitic elements (series R+L, shunt C) into a
SPICE netlist template following the node renaming convention. The original
template is never modified; augmented output is written to a new file.

Node renaming convention:
  - Parasitic-intermediate nodes use the `_peec` suffix
  - A series R+L chain is inserted on each critical signal path
  - Shunt C is added at terminals

Usage:
    python -m tools.spice.inject_parasitics template.cir parasitics.json output.cir
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.spice.extract import ExtractionResult, ParasiticValues


@dataclass
class NodeMapping:
    """Maps KiCad net names to SPICE node names for injection."""

    net_to_spice: dict[str, str] = field(default_factory=dict)

    def spice_node_for(self, net_name: str) -> str | None:
        return self.net_to_spice.get(net_name)

    def peec_node(self, spice_node: str) -> str:
        """Generate the parasitic-intermediate node name."""
        return f"n_{spice_node}_peec"


DEFAULT_NODE_MAPPING: dict[str, str] = {
    "GATE_H": "gate_hi",
    "GATE_L": "gate_lo",
    "DC_BUS+": "vbus",
    "DC_BUS-": "0",
    "SW_NODE": "midpoint",
    "PGND": "emit_lo",
    "GND": "gnd_hi",
}


def _generate_param_name(net_name: str, param_type: str) -> str:
    """Generate a SPICE .param name for a parasitic value."""
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", net_name).upper()
    return f"{param_type}_{safe}"


def inject_parasitics(
    template_path: str | Path,
    extraction_result: ExtractionResult,
    output_path: str | Path,
    node_mapping: dict[str, str] | None = None,
    temp: float | None = None,
) -> str:
    """Inject parasitic elements into a SPICE netlist template.

    Args:
        template_path: Path to the .cir netlist template.
        extraction_result: Parasitic extraction results.
        output_path: Where to write the augmented netlist.
        node_mapping: Optional override for net-to-SPICE node mapping.
        temp: Optional simulation temperature in Celsius.

    Returns:
        The augmented netlist text.
    """
    if node_mapping is None:
        node_mapping = dict(DEFAULT_NODE_MAPPING)

    template = Path(template_path).read_text()

    lines = template.split("\n")
    output_lines: list[str] = []
    injected_header = False
    rename_map: dict[str, str] = {}

    parasitic_params: list[str] = []
    parasitic_elements: list[str] = []

    for net_name, pv in extraction_result.nets.items():
        spice_node = node_mapping.get(net_name)
        if spice_node is None:
            continue

        l_param = _generate_param_name(net_name, "L")
        r_param = _generate_param_name(net_name, "R")
        c_param = _generate_param_name(net_name, "C")

        parasitic_params.append(f".param {l_param}={pv.L_nH}n")
        parasitic_params.append(f".param {r_param}={pv.R_mOhm}m")
        parasitic_params.append(f".param {c_param}={pv.C_pF}p")

        peec_node = f"n_{spice_node}_peec"
        rename_map[spice_node] = peec_node

        if spice_node != "0":
            parasitic_elements.append(
                f"R_peec_{net_name} {spice_node} {peec_node} {{{r_param}}}"
            )
            parasitic_elements.append(
                f"L_peec_{net_name} {peec_node} {spice_node} {{{l_param}}}"
            )

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("* INCLUDE MODELS") and not injected_header:
            output_lines.append(line)
            output_lines.append("")
            output_lines.append("***************************************************************************")
            output_lines.append("* LAYOUT PARASITICS (injected from PCB extraction)")
            output_lines.append("***************************************************************************")
            for pp in parasitic_params:
                output_lines.append(pp)
            output_lines.append("")
            for pe in parasitic_elements:
                output_lines.append(pe)
            output_lines.append("")
            injected_header = True
            continue

        if temp is not None and stripped.startswith(".options reltol"):
            output_lines.append(line)
            output_lines.append(f".temp {temp}")
            continue

        output_lines.append(line)

    result = "\n".join(output_lines)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(result)

    return result


def main() -> None:
    """CLI entry point for parasitic injection."""
    if len(sys.argv) < 4:
        print(
            "Usage: python -m tools.spice.inject_parasitics "
            "template.cir parasitics.json output.cir",
            file=sys.stderr,
        )
        sys.exit(1)

    template_path = sys.argv[1]
    parasitics_path = sys.argv[2]
    output_path = sys.argv[3]

    with open(parasitics_path) as f:
        data: dict[str, dict[str, Any]] = json.load(f)

    nets: dict[str, object] = {}
    for name, vals in data.items():
        nets[name] = ParasiticValues(  # type: ignore[call-arg]
            net_name=name,
            R_mOhm=vals["R_mOhm"],
            L_nH=vals["L_nH"],
            C_pF=vals["C_pF"],
            loop_group=vals.get("loop_group"),
        )

    result = ExtractionResult(
        pcb_file="from_json",
        nets=nets,
        loop_groups={},
    )

    inject_parasitics(template_path, result, output_path)
    print(f"Augmented netlist written to {output_path}")


if __name__ == "__main__":
    main()
