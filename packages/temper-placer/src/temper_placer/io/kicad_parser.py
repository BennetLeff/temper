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
from temper_placer.core.design_rules import (
    TEMPER_NET_ASSIGNMENTS,
    DesignRules,
    create_temper_design_rules,
)
from temper_placer.io._kicad_types import (
    ParseResult,
)
from temper_placer.io._parse_board import _extract_stackup
from temper_placer.io._parse_nets import _apply_safety_classifications, _extract_design_rules

_rs = _tdb.parse_engine

if TYPE_CHECKING:
    from collections.abc import Mapping

    from temper_placer.router_v6.stage0_data import ParsedPCB


def parse_kicad_pcb(
    pcb_path: Path,
    normalize: bool = True,
    design_rules: DesignRules | None = None,
    net_class_mapping: Mapping[str, str] | None = None,
) -> ParseResult:
    """Parse a KiCad PCB file (.kicad_pcb) to extract component placement and netlist.

    Args:
        pcb_path: Path to the .kicad_pcb file.
        normalize: If True, subtract board origin from component positions.
        design_rules: DesignRules driving component-level safety
            classification (``comp.net_class``, an HV/LV severity rollup
            over each component's pins -- see
            ``_apply_safety_classifications``). Defaults to this project's
            own SSOT (``create_temper_design_rules()``, built from
            ``TEMPER_NET_CLASSES``/``TEMPER_NET_ASSIGNMENTS`` in
            ``core/design_rules.py``) so every component gets its real
            rollup by default, mirroring ``net_class_mapping``'s own
            SSOT-by-default precedent below -- pass an explicit empty
            ``DesignRules(net_classes={}, net_class_assignments={}, ...)``
            to opt out (e.g. a test asserting the pre-classification
            raw-parse shape).

            Before this default existed, every caller that didn't
            separately opt in (nearly all of them -- ``design_rules`` was
            ``None``-means-skip) got ``comp.net_class == "Signal"`` for
            every component unconditionally, even after net-level
            classification was fixed (#1041/#1042): a net's real class was
            visible on ``Net.net_class``, but never rolled up onto the
            ``Component`` the three Rust safety kernels
            (``creepage.rs``/``hv_lv_separation.rs``/``isolation.rs``)
            actually read. See
            ``tests/io/test_component_net_classification.py``.
        net_class_mapping: ``net_name -> net_class`` mapping applied to each
            parsed ``Net.net_class`` (Rust ``Netlist.apply_net_class_mapping``,
            invoked inside the Rust parse engine itself -- see
            ``parse_engine.rs``'s ``parse_kicad_pcb_impl``). Defaults to this
            project's own ``TEMPER_NET_ASSIGNMENTS`` SSOT
            (``core/design_rules.py``) so every net gets its real class by
            default instead of silently keeping the ``Net`` pyclass's
            ``"Signal"`` default -- pass ``{}`` explicitly to opt out (e.g. a
            test asserting the pre-classification raw-parse shape).

    Returns:
        ParseResult containing netlist, board geometry, and any warnings.
    """
    # Accept both str and Path (the historical signature did; consumers pass
    # either).
    pcb_path = Path(pcb_path)
    content = pcb_path.read_text(encoding="utf-8")
    mapping = TEMPER_NET_ASSIGNMENTS if net_class_mapping is None else net_class_mapping
    result = _rs.parse_kicad_pcb(content, normalize=normalize, net_class_mapping=mapping)

    effective_design_rules = (
        create_temper_design_rules() if design_rules is None else design_rules
    )
    _apply_safety_classifications(result.netlist, effective_design_rules)

    return result


# Collapsed to one-liner: pure-delegation shim -> Rust parse_engine.
# Docstring lives on the Rust pyfunction; the Python wrapper existed only
# to re-document what the Rust side owns.
extract_footprint_positions = _rs.extract_footprint_positions


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
