"""
Reference Layout Loader for PCB Placement Benchmarking.

This module provides functions to load open-source KiCad PCB designs
and convert them into PlacementState objects for quality metric comparison.

Typical usage:
    # Load a reference design and compute metrics
    ref_state, netlist, board = load_reference_pcb("path/to/design.kicad_pcb")
    report = compute_quality_report(ref_state, netlist, board, context, config)

    # Compare against optimizer output
    opt_report = compute_quality_report(opt_state, netlist, board, context, config)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import jax.numpy as jnp
from jax import Array

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import parse_kicad_pcb, ParseResult


@dataclass
class ReferenceDesign:
    """
    A parsed reference PCB design ready for benchmarking.

    Attributes:
        name: Design name (e.g., "VESC_6.6", "OLinuXino_A64")
        source: Source URL or path
        state: PlacementState with component positions
        netlist: Extracted netlist
        board: Board geometry
        parse_result: Full parse result for additional data
        stats: Design statistics (component count, net count, etc.)
    """

    name: str
    source: str
    state: PlacementState
    netlist: Netlist
    board: Board
    parse_result: ParseResult
    stats: Dict


def load_reference_pcb(
    pcb_path: Path | str,
    name: Optional[str] = None,
    source: Optional[str] = None,
) -> ReferenceDesign:
    """
    Load a KiCad PCB file as a reference design for benchmarking.

    Args:
        pcb_path: Path to the .kicad_pcb file.
        name: Optional design name (defaults to filename).
        source: Optional source URL for attribution.

    Returns:
        ReferenceDesign with PlacementState, Netlist, and Board.

    Raises:
        FileNotFoundError: If the PCB file doesn't exist.
        ValueError: If the PCB cannot be parsed.
    """
    pcb_path = Path(pcb_path)
    if not pcb_path.exists():
        raise FileNotFoundError(f"PCB file not found: {pcb_path}")

    # Parse the KiCad PCB
    result = parse_kicad_pcb(pcb_path)

    if result.netlist.n_components == 0:
        raise ValueError(f"No components found in {pcb_path}")

    if result.board is None:
        raise ValueError(f"No board geometry found in {pcb_path}")

    # Convert to PlacementState
    state = netlist_to_placement_state(result.netlist, result.board)

    # Compute stats
    stats = compute_design_stats(result)

    return ReferenceDesign(
        name=name or pcb_path.stem,
        source=source or str(pcb_path),
        state=state,
        netlist=result.netlist,
        board=result.board,
        parse_result=result,
        stats=stats,
    )


def netlist_to_placement_state(
    netlist: Netlist,
    board: Optional[Board] = None,
) -> PlacementState:
    """
    Convert a parsed Netlist to PlacementState.

    Uses component initial_position and initial_rotation from parsing.
    Components without positions are placed at board center.

    Args:
        netlist: Parsed netlist with component positions.
        board: Optional board for default positioning.

    Returns:
        PlacementState with positions and rotation logits.
    """
    positions = []
    rotation_logits = []

    # Default center position
    center_x = 50.0
    center_y = 50.0
    if board:
        center_x = board.width / 2
        center_y = board.height / 2

    for comp in netlist.components:
        # Get position (origin-relative from parser)
        if comp.initial_position:
            pos = list(comp.initial_position)
        else:
            pos = [center_x, center_y]
        positions.append(pos)

        # Convert rotation index to logits
        # Index 0=0°, 1=90°, 2=180°, 3=270°
        rot_idx = comp.initial_rotation or 0
        rot_idx = rot_idx % 4
        logits = [0.0, 0.0, 0.0, 0.0]
        logits[rot_idx] = 10.0  # High logit for initial rotation
        rotation_logits.append(logits)

    return PlacementState(
        positions=jnp.array(positions, dtype=jnp.float32),
        rotation_logits=jnp.array(rotation_logits, dtype=jnp.float32),
    )


def compute_design_stats(result: ParseResult) -> Dict:
    """
    Compute statistics about a parsed design.

    Args:
        result: ParseResult from parse_kicad_pcb.

    Returns:
        Dict with statistics:
        - n_components: Number of components
        - n_nets: Number of nets
        - n_pins_per_net: Average pins per net
        - board_area_mm2: Board area in mm²
        - component_area_mm2: Total component area
        - density: Component area / board area ratio
        - footprint_types: Set of unique footprint types
    """
    netlist = result.netlist
    board = result.board

    # Component area
    total_comp_area = 0.0
    footprint_types = set()
    for comp in netlist.components:
        w, h = comp.bounds
        total_comp_area += w * h
        # Extract footprint type (e.g., "SOIC-8" from "Package_SO:SOIC-8")
        fp_parts = comp.footprint.split(":")
        footprint_types.add(fp_parts[-1] if fp_parts else comp.footprint)

    # Board area
    board_area = board.width * board.height if board else 0.0

    # Net stats
    n_nets = len(netlist.nets)
    avg_pins = 0.0
    if n_nets > 0:
        total_pins = sum(len(net.pins) for net in netlist.nets)
        avg_pins = total_pins / n_nets

    return {
        "n_components": netlist.n_components,
        "n_nets": n_nets,
        "n_pins_per_net": round(avg_pins, 2),
        "board_width_mm": board.width if board else 0,
        "board_height_mm": board.height if board else 0,
        "board_area_mm2": round(board_area, 1),
        "component_area_mm2": round(total_comp_area, 1),
        "density": round(total_comp_area / board_area, 3) if board_area > 0 else 0,
        "footprint_types": sorted(footprint_types),
        "n_warnings": len(result.warnings),
    }


def filter_components(
    design: ReferenceDesign,
    refs: Optional[Set[str]] = None,
    footprint_pattern: Optional[str] = None,
    min_size_mm2: Optional[float] = None,
) -> ReferenceDesign:
    """
    Create a filtered view of a reference design.

    Useful for creating smaller benchmarks from complex designs.

    Args:
        design: Original ReferenceDesign.
        refs: If provided, only include these component refs.
        footprint_pattern: If provided, only include matching footprints.
        min_size_mm2: If provided, exclude components smaller than this.

    Returns:
        New ReferenceDesign with filtered components.
    """
    filtered_comps = []
    filtered_indices = []

    for i, comp in enumerate(design.netlist.components):
        include = True

        if refs and comp.ref not in refs:
            include = False

        if footprint_pattern and footprint_pattern.lower() not in comp.footprint.lower():
            include = False

        if min_size_mm2:
            area = comp.bounds[0] * comp.bounds[1]
            if area < min_size_mm2:
                include = False

        if include:
            filtered_comps.append(comp)
            filtered_indices.append(i)

    if not filtered_comps:
        raise ValueError("Filter resulted in zero components")

    # Filter nets to only include those with at least 2 remaining components
    remaining_refs = {c.ref for c in filtered_comps}
    filtered_nets = []
    for net in design.netlist.nets:
        filtered_pins = [(ref, pin) for ref, pin in net.pins if ref in remaining_refs]
        if len(filtered_pins) >= 2:
            filtered_nets.append(
                Net(
                    name=net.name,
                    pins=filtered_pins,
                    net_class=net.net_class,
                    weight=net.weight,
                )
            )

    # Create filtered netlist
    filtered_netlist = Netlist(components=filtered_comps, nets=filtered_nets)

    # Filter state
    indices = jnp.array(filtered_indices)
    filtered_state = PlacementState(
        positions=design.state.positions[indices],
        rotation_logits=design.state.rotation_logits[indices],
    )

    # Recompute stats
    filtered_result = ParseResult(
        netlist=filtered_netlist,
        board=design.board,
        warnings=design.parse_result.warnings,
    )
    stats = compute_design_stats(filtered_result)

    return ReferenceDesign(
        name=f"{design.name}_filtered",
        source=design.source,
        state=filtered_state,
        netlist=filtered_netlist,
        board=design.board,
        parse_result=filtered_result,
        stats=stats,
    )


def infer_quality_config(design: ReferenceDesign) -> Dict:
    """
    Infer a reasonable quality config from a reference design.

    This auto-detects:
    - Thermal components (large TO-* packages, power modules)
    - HV components (high-power footprints, certain net names)
    - LV components (small ICs, MCUs)
    - Critical loops (gate drive paths)

    Args:
        design: Parsed reference design.

    Returns:
        Quality config dict suitable for compute_quality_report.
    """
    thermal = set()
    hv = set()
    lv = set()

    for comp in design.netlist.components:
        fp_lower = comp.footprint.lower()
        ref_upper = comp.ref.upper()
        w, h = comp.bounds
        area = w * h

        # Thermal: Large packages (TO-247, D2PAK, modules)
        if any(pkg in fp_lower for pkg in ["to-247", "to-220", "d2pak", "module", "heatsink"]):
            thermal.add(comp.ref)
        elif area > 100:  # Large components (>100mm²)
            thermal.add(comp.ref)

        # HV: Power transistors, diodes, bulk caps
        if ref_upper.startswith(("Q", "D", "TR", "U")) and area > 50:
            hv.add(comp.ref)
        elif "igbt" in fp_lower or "mosfet" in fp_lower:
            hv.add(comp.ref)

        # LV: Small ICs, MCUs, sensors
        if any(pkg in fp_lower for pkg in ["soic", "qfp", "bga", "qfn", "sot"]):
            if area < 100:
                lv.add(comp.ref)

    # Infer loops from gate drive nets
    loops = []
    for net in design.netlist.nets:
        net_upper = net.name.upper()
        if any(kw in net_upper for kw in ["GATE", "DRV", "DRIVE"]):
            if len(net.pins) >= 2:
                loop_refs = [ref for ref, _ in net.pins[:3]]  # First 3 components
                if len(loop_refs) >= 2:
                    loops.append(loop_refs)

    return {
        "thermal_components": thermal,
        "hv_components": hv,
        "lv_components": lv,
        "zone_assignments": {},  # Would need zone data from board
        "loop_components": loops[:3],  # Limit to 3 loops
        "min_hv_lv_clearance": 4.0,  # Conservative default
    }


def list_reference_designs(directory: Path | str) -> List[Dict]:
    """
    Scan a directory for KiCad PCB files that can be used as references.

    Args:
        directory: Directory to scan.

    Returns:
        List of dicts with filename, path, and estimated complexity.
    """
    directory = Path(directory)
    designs = []

    for pcb_path in directory.rglob("*.kicad_pcb"):
        # Skip backup files
        if "-backups" in str(pcb_path) or pcb_path.name.startswith("."):
            continue

        try:
            # Quick scan: just count footprints
            with open(pcb_path, "r") as f:
                content = f.read()

            # Count footprints by looking for (footprint patterns
            fp_count = content.count("(footprint ")

            # Estimate complexity
            if fp_count < 20:
                complexity = "simple"
            elif fp_count < 100:
                complexity = "medium"
            else:
                complexity = "complex"

            designs.append(
                {
                    "name": pcb_path.stem,
                    "path": str(pcb_path),
                    "estimated_components": fp_count,
                    "complexity": complexity,
                }
            )
        except Exception as e:
            # Skip files that can't be read
            continue

    # Sort by component count
    designs.sort(key=lambda d: d["estimated_components"])
    return designs
