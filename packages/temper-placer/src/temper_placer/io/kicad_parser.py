"""
KiCad PCB parser — re-export hub over the Rust parse engine.

Migrated to Rust (Wave 4 Phase 3 candidate 3, plan
``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``): the
parse engine lives in ``temper_design_bundle_python.parse_engine`` and this
module is its delegation shim. kiutils no longer imports in this module
(parent R4).

Public orchestrators (parse_kicad_pcb, parse_kicad_pcb_v6,
extract_footprint_positions) remain here; ``parse_kicad_schematic`` was
RETIRED (plan R8: a `pass` stub returning an empty netlist, consumer
``tests/io/test_integration.py`` only; its kiutils ``Schematic`` import had
to leave with this candidate).

Bit-identical parity against the verbatim kiutils oracle is asserted by
``tests/io/test_parse_engine_rust_differential.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb

from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules
from temper_placer.io._kicad_types import (
    PadData,
    ParseResult,
    TraceData,
    ViaData,
)
from temper_placer.io._parse_board import _extract_stackup
from temper_placer.io._parse_nets import _apply_safety_classifications, _extract_design_rules

_rs = _tdb.parse_engine

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
    # Accept both str and Path (the historical signature did; consumers pass
    # either).
    pcb_path = Path(pcb_path)
    content = pcb_path.read_text(encoding="utf-8")
    result = _rs.parse_kicad_pcb(content, normalize=normalize)

    if design_rules is not None:
        _apply_safety_classifications(result.netlist, design_rules)

    return result


def extract_footprint_positions(content: str) -> dict[str, dict]:
    """Extract component positions from raw KiCad PCB content without kiutils.

    Args:
        content: Raw KiCad PCB file content as string.

    Returns:
        Dict mapping component reference to position info:
        {"U1": {"x": 50.5, "y": 75.25, "rotation": 90.0}, ...}
    """
    return _rs.extract_footprint_positions(content)


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

    pcb_path = Path(pcb_path)
    try:
        pcb_content = pcb_path.read_text(encoding="utf-8")
    except Exception as e:
        warnings.append(f"Failed to read PCB file content: {e}")
        pcb_content = ""

    legacy_result = parse_kicad_pcb(pcb_path, normalize=False)
    warnings.extend(legacy_result.warnings)

    design_rules = _extract_design_rules(None, warnings, pcb_content)

    stackup = _extract_stackup(
        None, warnings, use_declared_layer_roles=use_declared_layer_roles, pcb_content=pcb_content
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
        vias=legacy_result.vias,
        warnings=warnings,
    )
