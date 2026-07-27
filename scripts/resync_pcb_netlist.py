#!/usr/bin/env python3
"""Resync ``pcb/temper.kicad_pcb``'s nets/designators/footprints against the
current atopile netlist (``elec/build/default.net``), WITHOUT moving any
existing footprint.

Why this exists (2026-07-27 resync): the committed board predates today's
SELV-float electrical work (net rename ``+340V_BUS`` -> ``+170V_BUS``, new
``gnd``/``ZCD_ISO`` nets, new modules THM-02/UVL-02/H11L1 opto/fuse holder,
split OVP divider resistors). ``scripts/gen_pcb_skeleton.py`` already knows
how to build a from-scratch board from the netlist (flow-layout placement,
footprint resolution via ``pcb/fp-lib-table``, the module-instance
``Sheetpath`` identity that survives designator renumbering -- see
``docs/solutions/logic-errors/fixed-positions-ref-fragility-across-
renumbering.md``). This script reuses that identity mechanism and that
footprint-resolution code directly (imported, not reimplemented), but instead
of laying out fresh positions for every component, it is KiCad's own
"update PCB from schematic" pattern: match existing footprints to the new
netlist by their stable ``Sheetpath`` identity, keep the OLD board's
position/orientation/layer/locked state for every match, only reassign pad
net numbers/names, drop footprints whose sheetpath no longer exists, and
append genuinely new components (never before in the board) into a clearly
separated staging row below the board outline rather than inventing a
"real" placement for them.

Usage:
    python scripts/resync_pcb_netlist.py [--netlist PATH] [--board PATH]
                                          [--fp-lib-table PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from gen_pcb_skeleton import (  # noqa: E402  (path shim above must run first)
    Netlist,
    _uuid_from_seed,
    parse_netlist,
    resolve_footprint,
)

from kiutils.board import Board  # noqa: E402
from kiutils.footprint import Footprint  # noqa: E402
from kiutils.items.common import Net as KiNet  # noqa: E402
from kiutils.items.common import Position  # noqa: E402

STAGING_GAP_MM = 20.0  # clearance below the existing outline before staging new parts
STAGING_ROW_PITCH_MM = 8.0
STAGING_COL_PITCH_MM = 12.0
STAGING_COLS = 10


def _reset_pad_nets(fp: Footprint) -> None:
    for pad in fp.pads:
        pad.net = None


def _assign_pad_nets(fp: Footprint, comp, netlist: Netlist, net_table: dict[str, KiNet]) -> None:
    """Identical matching strategy to gen_pcb_skeleton.generate_board(): exact
    pad-number match against a netlist pin first, then positional fallback
    for footprints whose pad numbers don't line up with netlist pin numbers
    (e.g. relay 'A1'/'A2'/'13'/'14')."""
    connectable_pads = [p for p in fp.pads if p.type in ("smd", "thru_hole")]
    for pad in fp.pads:
        net_name: str | None = None
        for net in netlist.nets.values():
            for ref, pin in net.nodes:
                if ref == comp.ref and pin == pad.number:
                    net_name = net.name
                    break
            if net_name is not None:
                break

        if net_name is None and pad in connectable_pads:
            pos_idx = connectable_pads.index(pad)
            has_exact_match = any(
                pin == pad.number
                for net in netlist.nets.values()
                for ref, pin in net.nodes
                if ref == comp.ref
            )
            if not has_exact_match:
                pin_str = str(pos_idx + 1)
                for net in netlist.nets.values():
                    for ref, pin in net.nodes:
                        if ref == comp.ref and pin == pin_str:
                            net_name = net.name
                            break
                    if net_name is not None:
                        break

        pad.net = net_table[net_name] if net_name and net_name in net_table else None


def resync(
    netlist_path: Path,
    board_path: Path,
    fp_lib_table_path: Path,
    dry_run: bool,
) -> dict:
    netlist = parse_netlist(netlist_path)
    old_board = Board.from_file(str(board_path))

    old_by_sheetpath: dict[str, Footprint] = {}
    old_by_libid: dict[str, Footprint] = {}
    for fp in old_board.footprints:
        sp = (fp.properties or {}).get("Sheetpath")
        if sp:
            old_by_sheetpath[sp] = fp
        old_by_libid.setdefault(fp.libId, fp)

    new_components = sorted(netlist.components.values(), key=lambda c: c.ref)

    kept: list[tuple[str, str, str]] = []  # sheetpath, ref, note
    footprint_swapped: list[tuple[str, str, str, str]] = []  # sheetpath, ref, old_fpid, new_fpid
    added: list[tuple[str, str]] = []  # sheetpath, ref
    designator_changes: list[tuple[str, str, str]] = []  # sheetpath, old_ref, new_ref

    matched_sheetpaths: set[str] = set()
    result_footprints: list[tuple] = []  # (comp, footprint)

    # Staging area: a clear row below the existing board outline, so new
    # components are visibly separate from anything already placed/routed.
    max_y = max((fp.position.Y for fp in old_board.footprints), default=0.0)
    stage_y0 = max_y + STAGING_GAP_MM
    stage_idx = 0

    for comp in new_components:
        old_fp = old_by_sheetpath.get(comp.sheetpath)
        if old_fp is not None:
            matched_sheetpaths.add(comp.sheetpath)
            old_ref = (old_fp.properties or {}).get("Reference")
            if old_ref != comp.ref:
                designator_changes.append((comp.sheetpath, old_ref, comp.ref))

            if old_fp.libId == comp.footprint:
                fp = copy.deepcopy(old_fp)
                kept.append((comp.sheetpath, comp.ref, "position preserved, same footprint"))
            else:
                # Same circuit slot, different physical footprint (e.g. a
                # part substitution). Resolve the new footprint's geometry
                # but transplant the OLD position/orientation/layer/locked
                # state onto it -- this is a footprint swap, not a move.
                try:
                    fp_path = resolve_footprint(comp.footprint, fp_lib_table_path)
                    fp = Footprint.from_file(str(fp_path))
                except ValueError:
                    template = old_by_libid.get(comp.footprint)
                    if template is None:
                        raise
                    fp = copy.deepcopy(template)
                fp.position = Position(
                    old_fp.position.X, old_fp.position.Y, old_fp.position.angle
                )
                fp.layer = old_fp.layer
                fp.locked = old_fp.locked
                footprint_swapped.append(
                    (comp.sheetpath, comp.ref, old_fp.libId, comp.footprint)
                )

            fp.libId = comp.footprint
            fp.tstamp = _uuid_from_seed(f"fp:{comp.tstamp}")
            fp.tedit = _uuid_from_seed(f"tedit:{comp.tstamp}")[:8]
            fp.properties = {
                "Reference": comp.ref,
                "Value": comp.value or "?",
                "Footprint": comp.footprint,
                "Sheetpath": comp.sheetpath,
            }
            _reset_pad_nets(fp)
            result_footprints.append((comp, fp))
        else:
            # Genuinely new component -- never existed in the committed
            # board under any designator. No position to preserve; staged
            # in a clearly separated row below the outline rather than
            # invented into the routed layout.
            try:
                fp_path = resolve_footprint(comp.footprint, fp_lib_table_path)
                fp = Footprint.from_file(str(fp_path))
            except ValueError:
                template = old_by_libid.get(comp.footprint)
                if template is None:
                    raise
                fp = copy.deepcopy(template)

            col = stage_idx % STAGING_COLS
            row = stage_idx // STAGING_COLS
            fp.position = Position(
                20.0 + col * STAGING_COL_PITCH_MM, stage_y0 + row * STAGING_ROW_PITCH_MM
            )
            fp.layer = "F.Cu"
            fp.locked = False
            stage_idx += 1

            fp.libId = comp.footprint
            fp.tstamp = _uuid_from_seed(f"fp:{comp.tstamp}")
            fp.tedit = _uuid_from_seed(f"tedit:{comp.tstamp}")[:8]
            fp.properties = {
                "Reference": comp.ref,
                "Value": comp.value or "?",
                "Footprint": comp.footprint,
                "Sheetpath": comp.sheetpath,
            }
            _reset_pad_nets(fp)
            added.append((comp.sheetpath, comp.ref))
            result_footprints.append((comp, fp))

    removed = [
        (sp, (fp.properties or {}).get("Reference"))
        for sp, fp in old_by_sheetpath.items()
        if sp not in matched_sheetpaths
    ]

    # Net table: deterministic (sorted by name), matching generate_board().
    sorted_nets = sorted(netlist.nets.values(), key=lambda n: n.name)
    net_table: dict[str, KiNet] = {}
    for i, net in enumerate(sorted_nets):
        net_table[net.name] = KiNet(number=i + 1, name=net.name)

    for comp, fp in result_footprints:
        _assign_pad_nets(fp, comp, netlist, net_table)

    # Positions captured BEFORE mutating old_board.footprints, for the
    # zero-moved proof.
    old_positions = {
        (fp.properties or {}).get("Sheetpath"): (
            fp.position.X,
            fp.position.Y,
            fp.position.angle,
            fp.layer,
        )
        for fp in old_board.footprints
        if (fp.properties or {}).get("Sheetpath")
    }
    new_positions = {
        comp.sheetpath: (fp.position.X, fp.position.Y, fp.position.angle, fp.layer)
        for comp, fp in result_footprints
    }
    moved = [
        sp
        for sp in matched_sheetpaths
        if old_positions.get(sp) != new_positions.get(sp)
    ]

    report = {
        "netlist_components": len(new_components),
        "old_board_footprints": len(old_board.footprints),
        "new_board_footprints": len(result_footprints),
        "kept_count": len(kept),
        "footprint_swapped_count": len(footprint_swapped),
        "added_count": len(added),
        "removed_count": len(removed),
        "designator_changes": designator_changes,
        "footprint_swapped": footprint_swapped,
        "added": added,
        "removed": removed,
        "moved_count": len(moved),
        "moved": moved,
        "net_count": len(net_table),
    }

    if not dry_run:
        old_board.footprints = [fp for _, fp in result_footprints]
        old_board.nets = list(net_table.values())
        old_board.to_file(str(board_path))

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--netlist", type=Path, default=REPO_ROOT / "elec/build/default.net")
    parser.add_argument("--board", type=Path, default=REPO_ROOT / "pcb/temper.kicad_pcb")
    parser.add_argument("--fp-lib-table", type=Path, default=REPO_ROOT / "pcb/fp-lib-table")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.netlist.is_file():
        print(f"ERROR: netlist not found: {args.netlist}", file=sys.stderr)
        sys.exit(1)
    if not args.board.is_file():
        print(f"ERROR: board not found: {args.board}", file=sys.stderr)
        sys.exit(1)

    report = resync(args.netlist, args.board, args.fp_lib_table, args.dry_run)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
