"""
KiCad PCB and schematic parser using kiutils — re-export hub.

Implementation extracted to ``io._parse_*`` and ``io._kicad_types``.
Public orchestrators (parse_kicad_pcb, parse_kicad_schematic, parse_kicad_pcb_v6)
remain here; all helpers and dataclasses are imported from the internal modules.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from kiutils.board import Board as KiBoard
from kiutils.schematic import Schematic

from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules
from temper_placer.core.netlist import Component, Net, Netlist
from temper_placer.io._kicad_types import ParseResult
from temper_placer.io._parse_board import _extract_board_geometry, _extract_stackup
from temper_placer.io._parse_modules import (
    _extract_components_from_pcb,
    _extract_pads_from_pcb,
)
from temper_placer.io._parse_nets import (
    _apply_safety_classifications,
    _extract_design_rules,
    _extract_nets_from_pcb,
)
from temper_placer.io._parse_tracks import _extract_traces_from_pcb, _extract_vias_from_pcb

if TYPE_CHECKING:
    from temper_placer.router_v6.stage0_data import ParsedPCB


def parse_kicad_pcb(
    pcb_path: Path,
    normalize: bool = True,
    design_rules: DesignRules | None = None,
) -> ParseResult:
    """Parse a KiCad PCB file (.kicad_pcb) to extract component placement and netlist.

    Args:
        pcb_path: Path to the .kicad_pcb file.
        normalize: If True, subtract board origin from component positions.
        design_rules: Optional DesignRules for net safety classification.

    Returns:
        ParseResult containing netlist, board geometry, and any warnings.
    """
    warnings: list[str] = []

    ki_board = KiBoard.from_file(str(pcb_path))

    if not ki_board.footprints:
        warnings.append("No footprints found in PCB.")
        board = _extract_board_geometry(ki_board, warnings)
        return ParseResult(
            netlist=Netlist(components=[], nets=[]),
            board=board,
            warnings=warnings,
            traces=[],
            vias=[],
            pads=[],
        )

    board = _extract_board_geometry(ki_board, warnings)

    origin_to_use = board.origin if normalize else (0.0, 0.0)
    components = _extract_components_from_pcb(ki_board, warnings, board_origin=origin_to_use)

    nets = _extract_nets_from_pcb(ki_board, components, warnings)

    net_map = {}
    if hasattr(ki_board, "nets"):
        for n in ki_board.nets:
            if hasattr(n, "number") and hasattr(n, "name"):
                net_map[str(n.number)] = n.name
            elif hasattr(n, "code") and hasattr(n, "name"):
                net_map[str(n.code)] = n.name

    traces = _extract_traces_from_pcb(ki_board, warnings, net_map)
    vias = _extract_vias_from_pcb(ki_board, warnings, net_map)
    pads = _extract_pads_from_pcb(ki_board, warnings)

    netlist = Netlist(components=components, nets=nets)

    if design_rules is not None:
        _apply_safety_classifications(netlist, design_rules)

    return ParseResult(
        netlist=netlist, board=board, warnings=warnings, traces=traces, vias=vias, pads=pads
    )


def parse_kicad_schematic(sch_path: Path, recursive: bool = True) -> ParseResult:
    """Parse KiCad schematic files to extract component and netlist data.

    Args:
        sch_path: Path to the root .kicad_sch file.
        recursive: If True, also parse hierarchical sheets.

    Returns:
        ParseResult with extracted netlist.
    """
    warnings: list[str] = []
    components: list[Component] = []
    nets_dict: dict[str, list[tuple[str, str]]] = {}

    sch = Schematic.from_file(str(sch_path))
    _parse_schematic_sheet(sch, components, nets_dict, warnings, recursive)

    nets = [Net(name=name, pins=pins) for name, pins in nets_dict.items()]

    return ParseResult(
        netlist=Netlist(components=components, nets=nets), board=None, warnings=warnings
    )


def _parse_schematic_sheet(
    _sheet: Schematic,
    components: list[Component],
    nets_dict: dict[str, list[tuple[str, str]]],
    warnings: list[str],
    recursive: bool,
) -> None:
    """Recursive helper for parsing hierarchical schematics."""
    pass


def extract_footprint_positions(content: str) -> dict[str, dict]:
    """Extract component positions from raw KiCad PCB content without kiutils.

    Args:
        content: Raw KiCad PCB file content as string.

    Returns:
        Dict mapping component reference to position info:
        {"U1": {"x": 50.5, "y": 75.25, "rotation": 90.0}, ...}
    """
    positions = {}

    footprint_starts = []
    for match in re.finditer(r'\(footprint\s+"[^"]+"\s+\(layer', content):
        footprint_starts.append(match.start())

    for i, start in enumerate(footprint_starts):
        end = footprint_starts[i + 1] if i + 1 < len(footprint_starts) else len(content)
        block = content[start:end]

        at_match = re.search(r"\(at\s+([\d.-]+)\s+([\d.-]+)(?:\s+([\d.-]+))?\)", block)
        if not at_match:
            continue

        x = float(at_match.group(1))
        y = float(at_match.group(2))
        rotation = float(at_match.group(3)) if at_match.group(3) else 0.0

        ref_match = re.search(r'\(property\s+"Reference"\s+"([^"]+)"', block)
        if not ref_match:
            continue

        ref = ref_match.group(1)

        positions[ref] = {
            "x": x,
            "y": y,
            "rotation": rotation,
        }

    return positions


def parse_kicad_pcb_v6(pcb_path: Path, *, use_declared_layer_roles: bool = False) -> ParsedPCB:
    """Parse KiCad PCB for Router V6 Stage 0.1: Load KiCad PCB File.

    Extracts complete ParsedPCB structure including:
    - Components, nets, zones (from existing parser)
    - Design rules: net classes, clearances, via sizes
    - Stackup: layer count, types, thicknesses, plane assignments

    Args:
        pcb_path: Path to .kicad_pcb file.
        use_declared_layer_roles: Forwarded to ``_extract_stackup`` (R8,
            default ``False`` -- today's zone-content-driven classification,
            unchanged). See that function's docstring: this must not be set
            to ``True`` in production before pours become derived output
            (this plan's U3), or it reproduces the recorded 12x completion
            regression in ``docs/evidence/2026-07-28-stackup-partial-revert.md``.

    Returns:
        ParsedPCB with all required data for Router V6.
    """
    from temper_placer.router_v6.stage0_data import ParsedPCB

    warnings: list[str] = []

    ki_board = KiBoard.from_file(str(pcb_path))

    try:
        pcb_content = pcb_path.read_text(encoding="utf-8")
    except Exception as e:
        warnings.append(f"Failed to read PCB file content: {e}")
        pcb_content = ""

    legacy_result = parse_kicad_pcb(pcb_path, normalize=False)
    warnings.extend(legacy_result.warnings)

    design_rules = _extract_design_rules(ki_board, warnings, pcb_content)

    stackup = _extract_stackup(
        ki_board, warnings, use_declared_layer_roles=use_declared_layer_roles
    )

    return ParsedPCB(
        components=legacy_result.netlist.components,
        nets=legacy_result.netlist.nets,
        zones=legacy_result.board.zones if legacy_result.board else [],
        board=legacy_result.board or Board.temper_default(),
        design_rules=design_rules,
        stackup=stackup,
        source_path=pcb_path,
        tracks=legacy_result.traces,
        warnings=warnings,
    )
