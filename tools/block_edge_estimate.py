#!/usr/bin/env python3
"""Estimate each block's local channel-skeleton edge count from the
committed board, to turn `block_partition.py`'s per-block net counts into a
SAT-model-size estimate (vars ~ edges_in_block x nets_in_block).

This is a coarse geometric estimate, not a real channel-skeleton
computation (that lives in Rust, `channel_skeleton.py` /
`temper-rust-router-core`, and requires the full obstacle map). The
approximation here: a block's local skeleton edge count scales with the
board AREA its components occupy (skeleton edge density is roughly
uniform per unit of free area for a board this size -- see caveats in the
plan doc). Area is measured as the bounding box of every component
assigned to that block, expanded by a routing margin.

Component -> block assignment (refdes have no hierarchy of their own --
see block_partition.py's docstring) is recovered here by:
  1. Matching each PCB net name's leading token against a known instance
     name (`hb`, `safety`, ...) -- covers most auto-named internal nets.
  2. A hand-built crosswalk for the ~20 nets whose name was overridden to
     a flat UPPER_SNAKE string in main.ato (these are exactly the
     point-to-point boundary nets and shared rails found by
     block_partition.py's atopile-source analysis -- the crosswalk is
     built FROM that analysis's output, not invented separately).
  3. Adjacency propagation: any net/component that still can't be
     classified (bare pin-name nets local to one component, e.g. "bias",
     "fb", "en") inherits its block from whichever already-classified
     component(s) share a net with it, iterated to a fixpoint. If a
     component ends up touching >1 block this way it is counted in all
     of them (generous -- it can only inflate a block's estimated area,
     never hide true membership).

Reads pcb/temper.kicad_pcb and elec/src/main.ato / modules.ato. Writes
nothing; per the task rules pcb/temper.kicad_pcb is never modified.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import block_partition as bp  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
PCB_FILE = REPO_ROOT / "pcb" / "temper.kicad_pcb"

# Hand-built crosswalk: KiCad net name (after main.ato's
# `.override_net_name`) -> atopile block set, read directly off
# block_partition.py's point-to-point / global-rail output for this board
# (2026-08-07 source). Nets not listed here either keep their atopile-style
# auto-generated name (handled by prefix matching) or are power/ground/HV
# rails already excluded from the router's per-net model.
OVERRIDE_NAME_BLOCKS: dict[str, set[str]] = {
    "PWM_HS": {"hb", "mcu"},
    "PWM_LS": {"hb", "mcu"},
    "GATE_HS": {"hb"},
    "GATE_LS": {"hb"},
    "SHUTDOWN": {"hb", "safety"},
    "I_SENSE": {"ct_sense", "safety", "mcu"},
    "V_BUS_SENSE": {"mcu", "safety"},
    "RTD_SCK": {"mcu", "rtd_pan"},
    "RTD_SDI": {"mcu", "rtd_pan"},
    "RTD_SDO": {"mcu", "rtd_pan"},
    "RTD_CS_N": {"mcu", "rtd_pan"},
    "RTD_DRDY": {"mcu", "rtd_pan"},
    "RTD_HW_FAULT": {"rtd_pan", "safety"},
    "OVP_VREF_2V5": {"rtd_pan", "safety"},
    "WDT_KICK": {"mcu", "safety"},
    "WDT_RESET_N": {"mcu", "safety"},
    "RELAY_CTRL": {"mcu", "power_in"},
    "ZCD_ISO": {"power_in", "mcu"},
    "DISCHARGE_CTRL": {"discharge", "mcu"},
}

FOOTPRINT_RE = re.compile(r'^\s*\(footprint\s')
REF_RE = re.compile(r'\(property "Reference" "([^"]+)"')
AT_RE = re.compile(r'^\s*\(at ([-\d.]+) ([-\d.]+)')
PAD_NET_RE = re.compile(r'\(net \d+ "([^"]*)"\)')


def iter_balanced_blocks(text: str, start_pat: re.Pattern) -> list[str]:
    """Yield each balanced-parenthesis block whose opening line matches start_pat."""
    blocks = []
    n = len(text)
    for m in start_pat.finditer(text):
        start = m.start()
        # start_pat's match begins at or before the construct's opening
        # '(' (it begins with '\(footprint'); find that '(' explicitly.
        paren_idx = text.index("(", start)
        depth = 0
        k = paren_idx
        while k < n:
            if text[k] == "(":
                depth += 1
            elif text[k] == ")":
                depth -= 1
                if depth == 0:
                    blocks.append(text[paren_idx : k + 1])
                    break
            k += 1
    return blocks


def parse_footprints(pcb_text: str) -> tuple[dict[str, tuple[float, float]], dict[str, set[str]]]:
    ref_pos: dict[str, tuple[float, float]] = {}
    ref_nets: dict[str, set[str]] = defaultdict(set)
    blocks = iter_balanced_blocks(pcb_text, re.compile(r"\n\s*\(footprint\s"))
    for block in blocks:
        ref_m = REF_RE.search(block)
        if not ref_m:
            continue
        ref = ref_m.group(1)
        at_m = AT_RE.search(block[:400]) or re.search(r"\(at ([-\d.]+) ([-\d.]+)", block)
        if at_m:
            ref_pos[ref] = (float(at_m.group(1)), float(at_m.group(2)))
        for net_m in PAD_NET_RE.finditer(block):
            name = net_m.group(1)
            if name:
                ref_nets[ref].add(name)
    return ref_pos, ref_nets


def classify_net_block(name: str) -> set[str]:
    if name in OVERRIDE_NAME_BLOCKS:
        return set(OVERRIDE_NAME_BLOCKS[name])
    head = re.split(r"[.\-]", name, maxsplit=1)[0]
    if head in bp.TOP_INSTANCES:
        return {head}
    return set()


def propagate_unknown(
    ref_nets: dict[str, set[str]],
    net_to_refs: dict[str, set[str]],
    ref_block: dict[str, set[str]],
    hub_net_max_refs: int = 6,
) -> None:
    """Propagate block membership to components with no directly
    classified net, via adjacency on shared nets -- but NOT through "hub"
    nets that fan out to many components (global gnd/power/HV rails, and
    anything that behaves like one even if a name-pattern heuristic
    missed it). Without this exclusion, any component sharing the global
    GND net with, say, the MCU (a genuine multi-block boundary component)
    would incorrectly inherit the MCU's entire block set -- gnd touches
    nearly every component on the board, so this single omission would
    saturate every block's bbox to ~100% of the board (caught empirically
    while building this script: first pass wrongly reported every block
    at 100% board-area coverage).
    """
    local_net_to_refs = {
        net: refs for net, refs in net_to_refs.items() if len(refs) <= hub_net_max_refs
    }
    changed = True
    rounds = 0
    while changed and rounds < 20:
        changed = False
        rounds += 1
        for ref, nets in ref_nets.items():
            if ref_block.get(ref):
                continue
            inferred: set[str] = set()
            for net in nets:
                for other_ref in local_net_to_refs.get(net, ()):
                    inferred |= ref_block.get(other_ref, set())
            if inferred:
                ref_block[ref] = inferred
                changed = True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--total-edges",
        type=float,
        default=204_490,
        help="Whole-board channel-skeleton edge count to scale from (default: the "
        "2026-08-07 measurement cited in this task's brief).",
    )
    ap.add_argument("--margin-mm", type=float, default=15.0, help="Bbox expansion margin per side")
    args = ap.parse_args()

    pcb_text = PCB_FILE.read_text()
    ref_pos, ref_nets = parse_footprints(pcb_text)

    net_to_refs: dict[str, set[str]] = defaultdict(set)
    for ref, nets in ref_nets.items():
        for net in nets:
            net_to_refs[net].add(ref)

    ref_block: dict[str, set[str]] = {}
    for ref, nets in ref_nets.items():
        blocks: set[str] = set()
        for net in nets:
            blocks |= classify_net_block(net)
        if blocks:
            ref_block[ref] = blocks

    propagate_unknown(ref_nets, net_to_refs, ref_block)

    unresolved = [r for r in ref_nets if r not in ref_block]

    # Whole-board bbox (from the Edge.Cuts rectangle: 20,20 to 172,254 on
    # the committed board -- 152mm x 234mm, 279.0mm diagonal, matching the
    # task brief's cited figure).
    board_w, board_h = 152.0, 234.0
    board_area = board_w * board_h

    per_block_bbox = {}
    for block in bp.TOP_INSTANCES:
        pts = [ref_pos[r] for r, bl in ref_block.items() if block in bl and r in ref_pos]
        if not pts:
            per_block_bbox[block] = None
            continue
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        x0 = max(board_w * 0 + 20, min(xs) - args.margin_mm)
        x1 = min(20 + board_w, max(xs) + args.margin_mm)
        y0 = max(20, min(ys) - args.margin_mm)
        y1 = min(20 + board_h, max(ys) + args.margin_mm)
        area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        per_block_bbox[block] = {
            "n_components": len(pts),
            "bbox_mm": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
            "area_mm2": round(area, 1),
            "area_fraction_of_board": round(area / board_area, 4),
        }

    # Combine with block_partition.py's net counts.
    modules_text = bp.MODULES_ATO.read_text()
    main_text = bp.MAIN_ATO.read_text()
    bodies = bp.parse_module_bodies(modules_text)
    graph = bp.instantiation_graph(bodies)
    block_reports = bp.compute_internal_nets(bodies, graph)
    cross_nets = bp.compute_top_level_nets(main_text)
    p2p = [c for c in cross_nets if len(c.blocks) >= 2 and not c.has_shared_rail]

    boundary_touch_count: dict[str, int] = defaultdict(int)
    for c in p2p:
        for b in c.blocks:
            boundary_touch_count[b] += 1

    report = {}
    for block in bp.TOP_INSTANCES:
        internal = block_reports[block].internal_nets_routable
        boundary = boundary_touch_count[block]
        # "own" nets = internal only (routed entirely within the block's
        # local model); "own + boundary" = the nets whose channel vars
        # this block's local SAT model must carry if boundary nets are
        # assigned to (i.e. routed by) this block -- see the ordering
        # discussion in the plan doc.
        nets_own = internal
        nets_with_boundary = internal + boundary
        bbox = per_block_bbox[block]
        if bbox is None:
            edge_est = None
            vars_own = vars_boundary = None
        else:
            frac = bbox["area_fraction_of_board"]
            edge_est = round(args.total_edges * frac)
            vars_own = edge_est * nets_own
            vars_boundary = edge_est * nets_with_boundary
        report[block] = {
            "n_components": bbox["n_components"] if bbox else 0,
            "bbox_area_mm2": bbox["area_mm2"] if bbox else 0,
            "area_fraction_of_board": bbox["area_fraction_of_board"] if bbox else 0,
            "estimated_local_edges": edge_est,
            "nets_own": nets_own,
            "nets_own_plus_boundary": nets_with_boundary,
            "estimated_vars_own": vars_own,
            "estimated_vars_own_plus_boundary": vars_boundary,
        }

    if args.json:
        print(json.dumps({"unresolved_refs": sorted(unresolved), "blocks": report}, indent=2))
        return 0

    print(f"Whole-board bbox: {board_w} x {board_h} mm = {board_area:.0f} mm^2 (diagonal {(board_w**2+board_h**2)**0.5:.1f} mm)")
    print(f"Whole-board skeleton edges (input, from --total-edges): {args.total_edges:.0f}")
    print(f"Unresolved (unclassified) refdes: {len(unresolved)} / {len(ref_nets)}  {unresolved[:15]}{'...' if len(unresolved) > 15 else ''}")
    print()
    hdr = f"{'block':<12}{'comps':>7}{'area%':>8}{'est.edges':>11}{'nets(own)':>11}{'nets(+bnd)':>12}{'vars(own)':>13}{'vars(+bnd)':>14}"
    print(hdr)
    for block in bp.TOP_INSTANCES:
        r = report[block]
        print(
            f"{block:<12}{r['n_components']:>7}{r['area_fraction_of_board']*100:>7.1f}%"
            f"{r['estimated_local_edges'] or 0:>11}{r['nets_own']:>11}{r['nets_own_plus_boundary']:>12}"
            f"{r['estimated_vars_own'] or 0:>13,}{r['estimated_vars_own_plus_boundary'] or 0:>14,}"
        )
    total_own = sum((r["estimated_vars_own"] or 0) for r in report.values())
    total_bnd = sum((r["estimated_vars_own_plus_boundary"] or 0) for r in report.values())
    print()
    print(f"Sum across all blocks, own-nets-only model:      {total_own:,} vars")
    print(f"Sum across all blocks, own+boundary-nets model:   {total_bnd:,} vars")
    monolith = args.total_edges * 110
    print(f"Monolithic model (whole board x 110 nets):        {monolith:,.0f} vars")
    largest = max(report.items(), key=lambda kv: (kv[1]["estimated_vars_own_plus_boundary"] or 0))
    print()
    print(
        f"Largest block by worst-case (own+boundary) model size: {largest[0]} "
        f"~= {largest[1]['estimated_vars_own_plus_boundary']:,} vars "
        f"({largest[1]['estimated_vars_own_plus_boundary'] / monolith * 100:.2f}% of monolith)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
