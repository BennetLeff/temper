"""
Constraint generator for external PCB test fixtures.

Generates realistic placement constraint YAML files from parsed PCB boards,
enabling automated testing without hand-crafting constraints for each board.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# Import conditionally to avoid import errors if temper_placer not installed
try:
    from temper_placer.io.kicad_parser import ParseResult
except ImportError:
    ParseResult = None  # type: ignore


def generate_constraints(
    parse_result: ParseResult,
    margin_mm: float = 2.0,
    power_net_weight: float = 0.5,
    signal_net_weight: float = 1.5,
) -> dict[str, Any]:
    """
    Generate placement constraints from a parsed PCB.

    Args:
        parse_result: Result from parse_kicad_pcb()
        margin_mm: Board edge margin in mm
        power_net_weight: Weight for power nets (lower = prefer shorter traces)
        signal_net_weight: Weight for signal nets

    Returns:
        Constraint dictionary suitable for YAML serialization
    """
    if parse_result.board is None:
        raise ValueError("ParseResult has no board geometry")

    board = parse_result.board
    netlist = parse_result.netlist

    # Basic board constraints
    constraints: dict[str, Any] = {
        "board": {
            "width_mm": round(board.width, 2),
            "height_mm": round(board.height, 2),
            "margin_mm": margin_mm,
        }
    }

    # Create a single default zone covering the entire board
    constraints["zones"] = [
        {
            "name": "main",
            "bounds": [0, 0, round(board.width, 2), round(board.height, 2)],
            "net_classes": ["Signal", "Power"],
        }
    ]

    # Generate component groups based on reference prefixes
    groups = _generate_component_groups(netlist)
    if groups:
        constraints["groups"] = groups

    # Generate net weights based on net names
    net_weights = _generate_net_weights(netlist, power_net_weight, signal_net_weight)
    if net_weights:
        constraints["net_weights"] = net_weights

    return constraints


def _generate_component_groups(netlist) -> list[dict[str, Any]]:
    """
    Generate component groups based on reference designator prefixes.

    Groups components like R1, R2, R3 into "resistors" group, etc.
    """
    # Categorize components by prefix
    prefix_map: dict[str, list[str]] = {}

    for comp in netlist.components:
        ref = comp.ref
        # Extract prefix (letters) from reference
        prefix = ""
        for c in ref:
            if c.isalpha():
                prefix += c
            else:
                break

        if prefix:
            if prefix not in prefix_map:
                prefix_map[prefix] = []
            prefix_map[prefix].append(ref)

    # Create groups for common prefixes
    groups = []
    prefix_names = {
        "R": "resistors",
        "C": "capacitors",
        "L": "inductors",
        "D": "diodes",
        "Q": "transistors",
        "U": "ics",
        "J": "connectors",
        "SW": "switches",
        "F": "fuses",
        "Y": "crystals",
        "FB": "ferrite_beads",
    }

    for prefix, refs in prefix_map.items():
        if len(refs) < 2:
            continue  # Don't create groups for single components

        group_name = prefix_names.get(prefix, f"{prefix.lower()}_components")

        # Calculate reasonable max spread based on component count
        # More components = allow more spread
        max_spread = min(50.0, 10.0 + len(refs) * 2.0)

        groups.append(
            {
                "name": group_name,
                "components": refs,
                "zone": "main",
                "max_spread_mm": round(max_spread, 1),
            }
        )

    return groups


def _generate_net_weights(
    netlist,
    power_weight: float,
    signal_weight: float,
) -> dict[str, float]:
    """
    Generate net weights based on net names.

    Power nets (GND, VCC, etc.) get lower weight to prefer shorter traces.
    Signal nets get higher weight.
    """
    net_weights = {}

    # Common power net patterns
    power_patterns = [
        "GND",
        "VCC",
        "VDD",
        "VSS",
        "VIN",
        "VOUT",
        "+3V3",
        "+5V",
        "+12V",
        "+1V",
        "+2V5",
        "3V3",
        "5V",
        "12V",
        "1V1",
        "1V8",
        "2V5",
        "AGND",
        "DGND",
        "PGND",
        "AVCC",
        "DVCC",
    ]

    for net in netlist.nets:
        net_name = net.name if hasattr(net, "name") else str(net)
        if not net_name or net_name == "":
            continue

        # Check if it's a power net
        net_upper = net_name.upper()
        is_power = any(
            pattern in net_upper or net_upper.startswith(pattern.rstrip("0123456789"))
            for pattern in power_patterns
        )

        if is_power:
            net_weights[net_name] = power_weight
        else:
            net_weights[net_name] = signal_weight

    return net_weights


def save_constraints(
    constraints: dict[str, Any],
    output_path: Path,
) -> None:
    """
    Save constraints dictionary to YAML file.

    Args:
        constraints: Constraint dictionary
        output_path: Path to save YAML file
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        yaml.dump(
            constraints,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
        )


def generate_constraints_for_project(
    project_name: str,
    output_dir: Path | None = None,
) -> Path | None:
    """
    Generate and save constraints for a downloaded external PCB project.

    Args:
        project_name: Name of the project (from manifest.yaml)
        output_dir: Directory to save constraints (default: same as PCB cache)

    Returns:
        Path to generated constraints file, or None if failed
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    from .download_pcbs import get_cached_pcb_path, get_project_config

    # Check project exists and is KiCad 6+
    config = get_project_config(project_name)
    if config is None:
        print(f"Unknown project: {project_name}")
        return None

    kicad_version = config.get("kicad_version", 6)
    if kicad_version == 5:
        print(f"Skipping {project_name}: KiCad 5 format not supported")
        return None

    # Get PCB path
    pcb_path = get_cached_pcb_path(project_name)
    if pcb_path is None or not pcb_path.exists():
        print(f"PCB not downloaded: {project_name}")
        return None

    # Parse PCB
    try:
        result = parse_kicad_pcb(pcb_path)
    except Exception as e:
        print(f"Failed to parse {project_name}: {e}")
        return None

    if result.netlist.n_components == 0:
        print(f"No components found in {project_name} (may be KiCad 5 format)")
        return None

    # Generate constraints
    constraints = generate_constraints(result)

    # Save to file
    if output_dir is None:
        output_dir = pcb_path.parent

    output_path = output_dir / f"{project_name}_constraints.yaml"
    save_constraints(constraints, output_path)

    print(f"Generated constraints for {project_name}: {output_path}")
    return output_path


if __name__ == "__main__":

    # Generate constraints for all downloaded projects
    from .download_pcbs import load_manifest

    manifest = load_manifest()
    projects = manifest.get("projects", {})

    generated = 0
    skipped = 0

    for name, config in projects.items():
        if config.get("kicad_version", 6) == 5:
            print(f"[SKIP] {name}: KiCad 5 format")
            skipped += 1
            continue

        result = generate_constraints_for_project(name)
        if result:
            generated += 1
        else:
            skipped += 1

    print(f"\nGenerated: {generated}, Skipped: {skipped}")
