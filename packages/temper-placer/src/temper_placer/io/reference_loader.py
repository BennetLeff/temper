"""
Reference Layout Loader for PCB Placement Benchmarking.

Delegation shim — under Wave 4 Phase 3, candidate 5, the two pure kernels
(``compute_design_stats``, ``infer_quality_config``) migrated to Rust
(``temper-design-bundle``, ``reference_loader.rs``). The orchestration that
is entangled with the KiCad parse engine (candidate 3) and numpy
``PlacementState`` (Phase 4/5) stays Python: ``load_reference_pcb``,
``filter_components``, ``netlist_to_placement_state`` and
``list_reference_designs`` keep calling the Rust kernels for the pure parts
(see the R3 boundary decision in ``packages/temper-design-bundle/VERIFICATION.md``).

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
from typing import cast

import numpy as np
import temper_design_bundle_python as _tdb

from temper_placer.core.board import Board
from temper_placer.core.netlist import Net, Netlist
from temper_placer.core.state import PlacementState
from temper_placer.io.kicad_parser import ParseResult, parse_kicad_pcb


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
    stats: dict


# Rust kernels (temper_design_bundle_python / reference_loader.rs).
compute_design_stats = _tdb.compute_design_stats
infer_quality_config = _tdb.infer_quality_config


def load_reference_pcb(
    pcb_path: Path | str,
    name: str | None = None,
    source: str | None = None,
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
    board: Board | None = None,
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
        pos = list(comp.initial_position) if comp.initial_position else [center_x, center_y]
        positions.append(pos)

        # Convert rotation index to logits
        # Index 0=0°, 1=90°, 2=180°, 3=270°
        rot_idx = comp.initial_rotation or 0
        rot_idx = rot_idx % 4
        logits = [0.0, 0.0, 0.0, 0.0]
        logits[rot_idx] = 10.0  # High logit for initial rotation
        rotation_logits.append(logits)

    return PlacementState(
        positions=np.array(positions, dtype=np.float32),
        rotation_logits=np.array(rotation_logits, dtype=np.float32),
    )


def filter_components(
    design: ReferenceDesign,
    refs: set[str] | None = None,
    footprint_pattern: str | None = None,
    min_size_mm2: float | None = None,
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
    indices = np.array(filtered_indices)
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


def list_reference_designs(directory: Path | str) -> list[dict]:
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
            with open(pcb_path) as f:
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
        except Exception:
            # Skip files that can't be read
            continue

    # Sort by component count
    designs.sort(key=lambda d: cast(int, d["estimated_components"]))
    return designs
