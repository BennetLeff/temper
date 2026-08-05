# provenance: commit=5c480a3bcbdddfa42f47b3ad16bb3921fcaf589f dirty=false
#!/usr/bin/env python3
"""Run-C COMPOUND feasibility probe (issue #651 follow-up).

# provenance: commit=5c480a3bcbdddfa42f47b3ad16bb3921fcaf589f dirty=false

Reproduces the zone-inclusive (run-C) formulation on the current board with
the general-convex zone encoding (#674) and answers the compound question the
encoding fix left open: the 14 non-zone exact fixed-copper conflicts that
appear at the naive zone-clear candidate are either jointly solvable by
placement (then run-C feasibility is a search problem and the production
caller with zones should be tried) or some pair of demands is mutually
exclusive (pure geometry: component footprint vs zone demand vs another
component's box -- needing a slot / zone-geometry / floorplan decision).

Deterministic analysis (cores are non-minimal and search-order-dependent, so
the core contents are never the measurement -- direct constraint evaluation
is, exactly as ``gap1_runc_pairs_corrected.py`` / ``gap1_runc_envelope_probe.py``):

  * exact fixed-copper audit at the best-known placement (the current board)
    and at the naive zone-clear candidate (C27 -> (29.62, 222.0), K3 ->
    (16.12, 7.42), the joint zone-reachability first-clearing positions);
  * the 14 non-zone compound conflicts (K3 pad 2/4 vs the GATE_HS zone, K3
    pads vs the ESP32 module's io41/io42/gpio35/gpio36 pads, K3 pad 4 vs two
    segments, K3 pad 1 vs the q_high-g / SW_NODE / gnd pads), each with (a)
    the exact clearance at the best placement, (b) the required clearance,
    (c) whether a placement exists that clears it JOINTLY with every zone
    item (exact-oracle search over the owning free ref's displacement
    envelope, gated by the same edge_margin the solver enforces);
  * the compound question: does a placement exist clearing ALL zone items AND
    ALL 14 compound items at once (cap 60 mm, rotations fixed)? If yes the
    compound is placement-solvable (a search problem); if no, a drop-one
    analysis names which item, removed, unblocks the most cells -- the
    mutually-exclusive demand pair.
  * the production caller (run_clearance_repair_solve, validator-gated,
    fixed_copper hoisted #653) with the zone-inclusive recipe: 3 attempts,
    seeds 0/1/2, 180 s each -- feasible / infeasible / time-limit per attempt
    plus the deterministic conflict set at each result.

NO src/ changes. Read-only w.r.t. ``pcb/temper.kicad_pcb``.

Usage:
    uv run --no-sync python docs/evidence/gap1_runc_compound_probe.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve()
while not (REPO / "pyproject.toml").exists():
    REPO = REPO.parent

_PLACER_DIR = REPO / "packages" / "temper-placer"
os.chdir(_PLACER_DIR)
sys.path.insert(0, str(_PLACER_DIR))

from tests.requirements.safety._real_board_fixture import (  # noqa: E402
    load_real_board_placement,
)

from temper_placer.io.kicad_parser import parse_kicad_pcb  # noqa: E402
from temper_placer.placer.cp_sat.clearance_repair import (  # noqa: E402
    run_clearance_repair_solve,
)
from temper_placer.placer.cp_sat.fixed_copper import (  # noqa: E402
    audit_fixed_copper,
    build_fixed_copper_items,
    build_free_component_pads,
    encoded_overlap,
    exact_clearance_mm,
    pad_world_rect,
)

FREE = {"K3", "C27"}
MARGIN_FC_MM = 0.05
MARGIN_EPS = 1e-6
EDGE_MARGIN_MM = 0.5  # solver edge_margin constraint on every ref
CAP_MM = 60.0         # the run-C displacement cap
STEP_MM = 0.5

# The naive zone-clear candidate (joint zone-reachability first-clearing
# positions at cap 60/120, measured by the envelope probe on the same tree).
CANDIDATE = {
    "C27": {"x_mm": 29.62, "y_mm": 222.0},
    "K3": {"x_mm": 16.12, "y_mm": 7.42},
}

OUT_SUMMARY = REPO / "docs" / "evidence" / "gap1_runc_compound_summary.json"
OUT_CSV = REPO / "docs" / "evidence" / "gap1_runc_compound_conflicts.csv"
OUT_CALLER = REPO / "docs" / "evidence" / "gap1_runc_compound_caller.json"


def git_provenance():
    """(commit, dirty) at write time, so artifacts carry the tree they were
    produced on (docs/METHODOLOGY.md Sec 5)."""
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(REPO)).stdout.strip()
    dirty = bool(subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True,
        cwd=str(REPO)).stdout.strip())
    return {"commit": sha, "dirty": dirty}


# ---------------------------------------------------------------------------
# geometry helpers (same semantics as the solver / probe)
# ---------------------------------------------------------------------------


def build_placement_at(pcb, positions, rotations):
    """Validator-shaped placement dict at *positions* (used only by the
    production caller path; the fixed-copper analysis uses the audit API
    directly)."""
    comps = []
    for c in pcb.netlist.components:
        if c.ref not in positions:
            continue
        pos = positions[c.ref]
        raw = c.attributes.get("_rotation_deg") if c.attributes else None
        rot_idx = rotations.get(c.ref, int(c.initial_rotation or 0) % 4)
        rot_deg = float(raw) if raw is not None else float(rot_idx * 90)
        pads = []
        for pin in c.pins:
            pads.append({
                "number": pin.number or pin.name,
                "net": pin.net,
                "offset": pin.position,
                "width": pin.width,
                "height": pin.height,
                "shape": pin.shape,
                "roundrect_ratio": pin.roundrect_ratio,
                "pad_rotation_deg": pin.pad_rotation_deg,
                "layer": pin.layer,
            })
        comps.append({"ref": c.ref, "position": pos, "rotation_deg": rot_deg,
                      "pads": pads, "nets": []})
    return {"components": comps, "nets": {}}


def pad_reachable_rect(rot_idx, pad, cx0, cy0, cap_mm):
    """Axis-aligned bounding box of every world rect the pad can occupy as the
    component center ranges over the Manhattan displacement envelope. An item
    whose (margin-expanded) rect does not intersect this cannot bind this pad
    anywhere in the envelope -- the pre-filter that keeps the per-cell scan
    tractable.

    Uses the exact ``_rotated`` closed form (same as ``pad_world_rect``) so
    the bound is tight under the component's fixed rotation -- a raw
    ``|lx|+hw`` bound is UNSOUND (a pad at (0,10) with half (1,1) under
    rot 1 reaches |ly|+hh = 11 in x, not 1).
    """
    from temper_placer.placer.cp_sat.fixed_copper import _rotated
    ox, oy, hwx, hwy = _rotated(pad, rot_idx)
    return {
        "x0": cx0 - cap_mm + ox - hwx,
        "y0": cy0 - cap_mm + oy - hwy,
        "x1": cx0 + cap_mm + ox + hwx,
        "y1": cy0 + cap_mm + oy + hwy,
    }


def _rects_overlap(a, b):
    return not (a["x1"] <= b[0] or b[2] <= a["x0"]
                or a["y1"] <= b[1] or b[3] <= a["y0"])


# ---------------------------------------------------------------------------
# deterministic conflict enumeration + joint-clear search
# ---------------------------------------------------------------------------


def enumerate_conflicts(pcb, pads_by_ref, items, positions, rotations):
    """The exact fixed-copper audit as a list of dicts at *positions*."""
    viol = audit_fixed_copper(pads_by_ref, items, positions, rotations)
    return [
        {"ref": v.ref, "pad": v.pad_number, "item_kind": v.item_kind,
         "item_net": v.item_net, "item_label": v.item_label,
         "required_mm": v.required_mm, "actual_mm": round(v.actual_mm, 4)}
        for v in viol
    ]


def zone_items_for(items):
    return [i for i in items if i.kind == "zone"]


def nonzone_items_for(items):
    return [i for i in items if i.kind != "zone"]


def joint_zone_clear(pcb, pads_by_ref, items, ref, center, rot_idx,
                     cap_mm=CAP_MM, step_mm=STEP_MM, board_clamp=False):
    """Scan the displacement envelope of *ref* (rotation fixed) for centers
    where EVERY (pad, zone-item) pair clears its zone by the margin -- the
    FULL run-C zone side (all 96 zone items on the board, not just the ones
    in violation at the best placement), with the audit's exact same-net skip
    (a pad's own net's pours are allowed to touch it) and layer filter.

    Deterministic, direct geometry: the same exact oracle
    (``exact_clearance_mm``) the R24 audit uses, over a uniform grid of the
    Manhattan envelope, gated on the solver's edge_margin (component box
    >= 0.5 mm inside the board).

    ``board_clamp`` restricts the scan to the board bounds (used by the
    board-wide compound scan at step 1.0 to answer the mutual-exclusion
    question without iterating off-board cells).

    Returns the list of clearing centers (as (x, y, disp)) and the total cell
    count, so callers can then evaluate the compound items on the zone-clear
    set only.
    """
    board_w = float(pcb.board.width)
    board_h = float(pcb.board.height)
    comp = next(c for c in pcb.netlist.components if c.ref == ref)
    bwx, bwy = float(comp.bounds[0]), float(comp.bounds[1])
    hw, hh = bwx / 2.0, bwy / 2.0
    cx0, cy0 = center
    pads = pads_by_ref.get(ref, [])
    comp_nets = {p.net for p in pads if p.net}
    zones = [z for z in items
             if z.kind == "zone"
             and (z.net is None or z.net not in comp_nets)]

    # Pre-filter zone items per pad: layer overlap AND reachable-rect overlap
    # with the margin-expanded item rect (both sound necessary conditions for
    # binding; the second is exact under the fixed rotation).
    zones_by_pad = []
    for pad in pads:
        reach = pad_reachable_rect(rot_idx, pad, cx0, cy0, cap_mm)
        zones_by_pad.append(
            [z for z in zones
             if (pad.layers & z.layers) and _rects_overlap(reach, z.rect)]
        )

    x_lo = cx0 - cap_mm
    x_hi = cx0 + cap_mm
    y_lo = cy0 - cap_mm
    y_hi = cy0 + cap_mm
    if board_clamp:
        x_lo = max(x_lo, hw + EDGE_MARGIN_MM)
        x_hi = min(x_hi, board_w - hw - EDGE_MARGIN_MM)
        y_lo = max(y_lo, hh + EDGE_MARGIN_MM)
        y_hi = min(y_hi, board_h - hh - EDGE_MARGIN_MM)

    clearing = []
    n_cells = 0
    x = x_lo
    while x <= x_hi + 1e-9:
        y = y_lo
        while y <= y_hi + 1e-9:
            n_cells += 1
            if abs(x - cx0) + abs(y - cy0) > cap_mm + 1e-9:
                y += step_mm
                continue
            if (x - hw < EDGE_MARGIN_MM or y - hh < EDGE_MARGIN_MM
                    or x + hw > board_w - EDGE_MARGIN_MM
                    or y + hh > board_h - EDGE_MARGIN_MM):
                y += step_mm
                continue
            ok = True
            for pad, pad_zones in zip(pads, zones_by_pad, strict=True):
                rect = pad_world_rect(pad, (x, y), rot_idx)
                for z in pad_zones:
                    # Cheap encoded bbox pre-filter: non-overlap with the
                    # margin-expanded rect implies exact-clear by margin.
                    if encoded_overlap(rect, z):
                        if exact_clearance_mm(rect, z) < z.margin_mm - MARGIN_EPS:
                            ok = False
                            break
                if not ok:
                    break
            if ok:
                clearing.append((round(x, 2), round(y, 2),
                                 round(abs(x - cx0) + abs(y - cy0), 2)))
            y += step_mm
        x += step_mm
    return clearing, n_cells


def item_clear_cells(pcb, pads_by_ref, items, ref, center, rot_idx,
                     zone_clear_set, conflict, cap_mm=CAP_MM, step_mm=STEP_MM):
    """Among the zone-clear centers, count those where the specific conflict
    item ALSO clears (exact oracle). Returns (count, first_clear, best)."""
    pads = pads_by_ref.get(ref, [])
    item = conflict["item"]
    pad_num = conflict["pad"]
    pad = next(p for p in pads if p.number == pad_num)
    n_clear = 0
    first = None
    best = None
    for (x, y, disp) in zone_clear_set:
        rect = pad_world_rect(pad, (x, y), rot_idx)
        if exact_clearance_mm(rect, item) >= item.margin_mm - MARGIN_EPS:
            n_clear += 1
            if first is None:
                first = {"x_mm": x, "y_mm": y, "disp_mm": disp}
            if best is None or disp < best["disp_mm"]:
                best = {"x_mm": x, "y_mm": y, "disp_mm": disp}
    return n_clear, first, best


def _nonzone_by_pad(pads, nonzones, comp_nets, rot_idx, center, cap_mm):
    """Per-pad pre-filtered non-zone items (layer overlap, same-net skip,
    reachable-rect overlap)."""
    by_pad = []
    for pad in pads:
        reach = pad_reachable_rect(rot_idx, pad, center[0], center[1], cap_mm)
        by_pad.append([
            i for i in nonzones
            if (pad.layers & i.layers)
            and (i.net is None or i.net not in comp_nets)
            and _rects_overlap(reach, i.rect)
        ])
    return by_pad


def _cells_clear_all_items(zone_clear, pads, nonzones_by_pad, rot_idx,
                           exclude_idx=None):
    """Among *zone_clear* centers, count those clearing every non-zone item
    (all of them, or all but the one at *exclude_idx* -- the drop-one
    analysis). Returns (count, first, best)."""
    n_clear = 0
    first = None
    best = None
    for (x, y, disp) in zone_clear:
        ok = True
        for pad, pad_items in zip(pads, nonzones_by_pad, strict=True):
            rect = pad_world_rect(pad, (x, y), rot_idx)
            for it in pad_items:
                if exclude_idx is not None and it is exclude_idx:
                    continue
                if encoded_overlap(rect, it):
                    if exact_clearance_mm(rect, it) < it.margin_mm - MARGIN_EPS:
                        ok = False
                        break
            if not ok:
                break
        if ok:
            n_clear += 1
            if first is None:
                first = {"x_mm": x, "y_mm": y, "disp_mm": disp}
            if best is None or disp < best["disp_mm"]:
                best = {"x_mm": x, "y_mm": y, "disp_mm": disp}
    return n_clear, first, best


def compound_clear(pcb, pads_by_ref, items, ref, center, rot_idx,
                   cap_mm=CAP_MM, step_mm=STEP_MM, board_clamp=False,
                   zone_clear=None):
    """Does a placement exist clearing ALL zone items AND ALL non-zone items
    (pads/segments/vias) at once, within the envelope?

    Two-stage scan for tractability:
      1. zone-joint-clear set (all 96 zones, same-net skipped -- see
         ``joint_zone_clear``);
      2. within that set, evaluate the non-zone items (pre-filtered by
         per-pad reachable rect and the same-net skip), keeping centers that
         clear every item.
    """
    nonzones = nonzone_items_for(items)
    pads = pads_by_ref.get(ref, [])
    comp_nets = {p.net for p in pads if p.net}
    if zone_clear is None:
        zone_clear, n_cells = joint_zone_clear(pcb, pads_by_ref, items, ref,
                                               center, rot_idx, cap_mm,
                                               step_mm, board_clamp)
    else:
        n_cells = None
    if not zone_clear:
        return {"any_compound_clear": False,
                "zone_clear_cells": 0,
                "compound_clear_cells": 0,
                "grid_cells": n_cells, "first": None, "best": None}

    nonzones_by_pad = _nonzone_by_pad(pads, nonzones, comp_nets, rot_idx,
                                      center, cap_mm)
    n_compound_clear, first, best = _cells_clear_all_items(
        zone_clear, pads, nonzones_by_pad, rot_idx)
    return {"any_compound_clear": n_compound_clear > 0,
            "zone_clear_cells": len(zone_clear),
            "compound_clear_cells": n_compound_clear,
            "grid_cells": n_cells, "first": first, "best": best}


def drop_one_analysis(pcb, pads_by_ref, items, ref, center, rot_idx,
                      zone_clear_set, conflicts, cap_mm=CAP_MM):
    """If no compound-clear placement exists, report for each conflict item
    how many zone-clear cells clear ALL the OTHER items when THIS ONE is
    dropped. A non-zero count means that single item is a blocking member of
    every feasible compound placement -- the mutually-exclusive demand. A
    zero count everywhere means the block is combinatorial (>=2 items always
    overlap in their exclusion regions)."""
    nonzones = nonzone_items_for(items)
    pads = pads_by_ref.get(ref, [])
    comp_nets = {p.net for p in pads if p.net}
    nonzones_by_pad = _nonzone_by_pad(pads, nonzones, comp_nets, rot_idx,
                                      center, cap_mm)
    rows = []
    for conf in conflicts:
        item = conf["item"]
        n, first, best = _cells_clear_all_items(
            zone_clear_set, pads, nonzones_by_pad, rot_idx, exclude_idx=item)
        rows.append({
            "conflict": conf["label"],
            "pad": conf["pad"],
            "item_kind": item.kind,
            "item_net": item.net,
            "zone_clear_cells_clearing_other_items_with_this_dropped": n,
            "unblocks_when_dropped": n > 0,
            "first_clearing_position": first,
        })
    rows.sort(key=lambda r: -r["zone_clear_cells_clearing_other_items_with_this_dropped"])
    return rows


# ---------------------------------------------------------------------------
# production caller attempts (zone-inclusive recipe)
# ---------------------------------------------------------------------------


def caller_attempt(pcb, full, full_vd, seed, timeout_ms=180_000,
                   cap_mm=CAP_MM, max_rounds=4):
    """One run_clearance_repair_solve with the run-C (zone-inclusive)
    fixed-copper recipe: nothing hard-pinned, rotations fixed, *cap_mm*
    displacement cap, domain-clearance + keepaway SeparatedConstraints,
    fixed-copper FREE={K3,C27} at margin 0.05 with the FULL parse_result
    (zones included)."""
    fc = {"parse_result": pcb, "free_refs": FREE, "margin_mm": MARGIN_FC_MM}
    t0 = time.monotonic()
    report = run_clearance_repair_solve(
        pcb_path=REPO / "pcb" / "temper.kicad_pcb",
        placement=full,
        voltage_domains=full_vd,
        timeout_ms=timeout_ms,
        seed=seed,
        max_rounds=max_rounds,
        max_displacement_mm=cap_mm,
        chain_exempt_pairs=None,
        fixed_copper=fc,
    )
    wall = round(time.monotonic() - t0, 1)
    round0 = report.rounds[0] if report.rounds else None
    return {
        "seed": seed,
        "cap_mm": cap_mm,
        "timeout_ms": timeout_ms,
        "status": report.status,
        "reason": report.reason[:400],
        "wall_s": wall,
        "rounds": len(report.rounds),
        "round0_solve_status": round0.solve_status if round0 else None,
        "round0_solve_time_ms": round0.solve_time_ms if round0 else None,
        "round0_total_constraints": round0.total_constraints if round0 else None,
        "domain_constraints": report.domain_constraints,
        "keepaway_constraints": report.keepaway_constraints,
        "total_displacement_mm": round(report.total_displacement_mm, 2),
        "moved_refs": len(report.moved_refs),
        "fixed_copper_free_refs": sorted(report.fixed_copper_free_refs),
        "fixed_copper_margin_mm": report.fixed_copper_margin_mm,
        "fixed_copper_audit_violations": report.fixed_copper_audit_violations,
        "final_positions": {
            ref: {"position": list(p)} for ref, p in report.final_positions.items()
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-caller", action="store_true",
                    help="skip the production-caller attempts")
    ap.add_argument("--caller-only", action="store_true",
                    help="run ONLY the production-caller attempts (skip the "
                         "deterministic scans; reads existing summary for the "
                         "conflict table)")
    args = ap.parse_args()

    pcb = parse_kicad_pcb(REPO / "pcb" / "temper.kicad_pcb")
    full, _vd, stats = load_real_board_placement()
    full_vd = stats["full_voltage_domains"]
    print(f"board: {pcb.board.width}x{pcb.board.height}mm, "
          f"{len(pcb.netlist.components)} refs, {len(pcb.board.zones)} zones")

    pos = {c.ref: c.initial_position for c in pcb.netlist.components}
    rot = {c.ref: int(c.initial_rotation or 0) for c in pcb.netlist.components}
    print(f"best-known placement: K3={pos['K3']} C27={pos['C27']}")

    if args.caller_only:
        # Deterministic scans already in the summary; just refresh the
        # caller attempts (enlarged-envelope decisive test) and rewrite.
        summary = json.loads(OUT_SUMMARY.read_text()) if OUT_SUMMARY.exists() else {}
        caller_rows = []
        for seed in (0, 1, 2):
            row = caller_attempt(pcb, full, full_vd, seed)
            caller_rows.append(row)
            print(f"  seed {seed}: status={row['status']} "
                  f"rounds={row['rounds']} wall={row['wall_s']}s")
        for cap in (120.0, 240.0):
            row = caller_attempt(pcb, full, full_vd, seed=0, cap_mm=cap)
            row["cap_mm"] = cap
            caller_rows.append(row)
            print(f"  seed 0 cap {cap}: status={row['status']} "
                  f"rounds={row['rounds']} wall={row['wall_s']}s "
                  f"reason={row['reason'][:160]}")
        summary["provenance"] = git_provenance()
        summary["caller_attempts"] = caller_rows
        OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True,
                                          default=str))
        OUT_CALLER.write_text(json.dumps(
            {"provenance": git_provenance(), "attempts": caller_rows},
            indent=2, sort_keys=True, default=str))
        print(f"wrote {OUT_SUMMARY} / {OUT_CALLER}")
        return

    pads = build_free_component_pads(pcb.netlist, FREE)
    items = build_fixed_copper_items(pcb, pcb.netlist, FREE, MARGIN_FC_MM)
    n_items = len(items)
    print(f"fixed-copper items: {n_items} "
          f"({sum(1 for i in items if i.kind=='zone')} zone, "
          f"{sum(1 for i in items if i.kind=='segment')} segment, "
          f"{sum(1 for i in items if i.kind=='via')} via, "
          f"{sum(1 for i in items if i.kind=='pad')} pad)")

    # ---- exact audit at the best-known placement -------------------------
    viol_best = enumerate_conflicts(pcb, pads, items, pos, rot)
    print(f"\nexact fixed-copper violations at BEST placement: {len(viol_best)}")
    for v in viol_best[:40]:
        print(f"  {v['ref']} pad {v['pad']} vs {v['item_kind']} "
              f"({v['item_net']}): {v['actual_mm']}mm < {v['required_mm']}mm")

    # ---- exact audit at the naive zone-clear candidate --------------------
    cand_pos = dict(pos)
    for ref, xy in CANDIDATE.items():
        cand_pos[ref] = (xy["x_mm"], xy["y_mm"])
    viol_cand = enumerate_conflicts(pcb, pads, items, cand_pos, rot)
    print(f"\nexact fixed-copper violations at NAIVE CANDIDATE: {len(viol_cand)}")
    for v in viol_cand:
        print(f"  {v['ref']} pad {v['pad']} vs {v['item_kind']} "
              f"({v['item_net']}): {v['actual_mm']}mm < {v['required_mm']}mm")

    # ---- per-conflict joint-clear analysis (K3 owns all 14) ---------------
    k3_center = pos["K3"]
    k3_rot = rot["K3"]
    print(f"\njoint zone-clear scan over K3's {CAP_MM}mm envelope "
          f"(step {STEP_MM}mm) ...")
    zone_clear, n_cells = joint_zone_clear(pcb, pads, items, "K3", k3_center,
                                           k3_rot)
    print(f"zone-joint-clear cells: {len(zone_clear)} / {n_cells}")

    # Map the 14 candidate violations to their items for the joint-clear test.
    item_index = {}
    for _i, it in enumerate(items):
        item_index.setdefault((it.kind, it.net), []).append(it)

    conflicts = []
    for v in viol_cand:
        cands = item_index.get((v["item_kind"], v["item_net"]), [])
        # Pick the item whose exact clearance at the candidate matches the
        # audit's violation (same pad+item geometry).
        pad = next(p for p in pads["K3"] if p.number == v["pad"])
        chosen = None
        for it in cands:
            rect = pad_world_rect(pad, cand_pos["K3"], k3_rot)
            if abs(exact_clearance_mm(rect, it) - v["actual_mm"]) < 1e-6:
                chosen = it
                break
        if chosen is None and cands:
            chosen = cands[0]
        conflicts.append({
            "label": f"{v['ref']} pad {v['pad']} vs {v['item_kind']} {v['item_net']}",
            "ref": v["ref"], "pad": v["pad"], "item": chosen, "item_kind": v["item_kind"],
            "item_net": v["item_net"], "required_mm": v["required_mm"],
            "actual_mm_at_candidate": v["actual_mm"],
        })

    conflict_rows = []
    for conf in conflicts:
        # (a) exact clearance at the BEST placement
        pad = next(p for p in pads[conf["ref"]] if p.number == conf["pad"])
        rect_best = pad_world_rect(pad, pos[conf["ref"]], rot[conf["ref"]])
        clr_best = exact_clearance_mm(rect_best, conf["item"])
        # (c) joint-clear with the zones
        n, first, best = item_clear_cells(pcb, pads, items, conf["ref"],
                                          pos[conf["ref"]], rot[conf["ref"]],
                                          zone_clear, conf)
        conflict_rows.append({
            "conflict": conf["label"],
            "ref": conf["ref"],
            "pad": conf["pad"],
            "item_kind": conf["item_kind"],
            "item_net": conf["item_net"],
            "clearance_at_best_mm": round(clr_best, 4),
            "required_mm": conf["required_mm"],
            "clearance_at_candidate_mm": conf["actual_mm_at_candidate"],
            "zone_clear_cells_also_clearing_item": n,
            "jointly_clearable_with_zones": n > 0,
            "first_clearing_position": first,
            "min_disp_clearing_position": best,
        })
        print(f"  {conf['label']}: at-best={clr_best:.4f}mm required="
              f"{conf['required_mm']}mm at-candidate={conf['actual_mm_at_candidate']:.4f}mm "
              f"jointly-clearable={n>0} (cells={n})")

    # ---- the compound question -------------------------------------------
    comp = compound_clear(pcb, pads, items, "K3", k3_center, k3_rot)
    print(f"\ncompound (all zones + all 14 items, cap {CAP_MM}mm): "
          f"clearable={comp['any_compound_clear']} "
          f"(zone-clear cells={comp['zone_clear_cells']}, "
          f"compound-clear cells={comp['compound_clear_cells']}, "
          f"first={comp['first']}, min-disp={comp['best']})")

    # Board-wide compound scan: is ANY on-board placement (no displacement
    # cap) zone-clear AND compound-clear? This is the mutual-exclusion test --
    # if the cap-60 compound is blocked but a board-wide one exists, the
    # compound is cap-limited (a search/envelope problem); if even the whole
    # board is blocked, the demand pair is geometrically exclusive.
    cap_wide = 400.0  # > max Manhattan distance from K3 to any board corner
    zc_wide, _n_wide = joint_zone_clear(pcb, pads, items, "K3", k3_center,
                                        k3_rot, cap_mm=cap_wide, step_mm=1.0,
                                        board_clamp=True)
    comp_wide = compound_clear(pcb, pads, items, "K3", k3_center, k3_rot,
                               cap_mm=cap_wide, step_mm=1.0,
                               board_clamp=True, zone_clear=zc_wide)
    print(f"compound board-wide (no cap, step 1.0): "
          f"zone-clear={len(zc_wide)} compound-clear="
          f"{comp_wide['compound_clear_cells']} "
          f"first={comp_wide['first']}")

    # C27 zone side: its only run-C conflicts are zones (DC_BUS_RTN at the
    # best placement); the compound probe's 14 are all K3. Verify C27's
    # all-96-zones joint-clear still exists within the cap (the envelope
    # probe only checked the zones in violation at best).
    c27_center = pos["C27"]
    zc_c27, n_c27 = joint_zone_clear(pcb, pads, items, "C27", c27_center,
                                     rot["C27"])
    print(f"C27 all-96-zones joint-clear: {len(zc_c27)} / {n_c27} cells "
          f"(first={zc_c27[0] if zc_c27 else None})")

    drop = None
    if not comp["any_compound_clear"] and zone_clear:
        drop = drop_one_analysis(pcb, pads, items, "K3", k3_center, k3_rot,
                                 zone_clear, conflicts)
        print("drop-one analysis (dropping THIS item, cells that clear all "
              "the other items):")
        for r in drop:
            print(f"  drop {r['conflict']}: "
                  f"{r['zone_clear_cells_clearing_other_items_with_this_dropped']}"
                  f" unblocks={r['unblocks_when_dropped']}")

    # ---- production caller attempts --------------------------------------
    caller_rows = []
    if not args.skip_caller:
        print("\nproduction caller attempts (zone-inclusive recipe, "
              "seeds 0/1/2, 180s each) ...")
        for seed in (0, 1, 2):
            row = caller_attempt(pcb, full, full_vd, seed)
            caller_rows.append(row)
            print(f"  seed {seed}: status={row['status']} "
                  f"rounds={row['rounds']} "
                  f"round0={row['round0_solve_status']} "
                  f"({row['round0_solve_time_ms']}ms, "
                  f"{row['round0_total_constraints']} constraints) "
                  f"wall={row['wall_s']}s")
            if row["status"] == "infeasible":
                print(f"    reason: {row['reason'][:200]}")

        # Enlarged-envelope decisive test: the exact-oracle compound scan
        # shows the full compound (zones + all 14 items) is only clearable at
        # >= ~119 mm displacement -- beyond the 60 mm run-C cap. If a larger
        # cap flips the caller's solve to feasible, run-C is a cap-limited
        # search problem; if it stays proven-UNSAT, the compound is the
        # binding block even with the region reachable.
        for cap in (120.0, 240.0):
            row = caller_attempt(pcb, full, full_vd, seed=0,
                                 cap_mm=cap)
            row["cap_mm"] = cap
            caller_rows.append(row)
            print(f"  seed 0 cap {cap}: status={row['status']} "
                  f"rounds={row['rounds']} wall={row['wall_s']}s "
                  f"reason={row['reason'][:160]}")

    # ---- write artifacts ---------------------------------------------------
    summary = {
        "provenance": git_provenance(),
        "best_known_placement_is_current_board": True,
        "k3_at_mm": pos["K3"],
        "c27_at_mm": pos["C27"],
        "candidate_positions": CANDIDATE,
        "formulation": {
            "free_refs": sorted(FREE),
            "margin_mm": MARGIN_FC_MM,
            "cap_mm": CAP_MM,
            "grid_step_mm": STEP_MM,
            "edge_margin_mm": EDGE_MARGIN_MM,
            "rotations": "fixed",
            "caller": "run_clearance_repair_solve (validator-gated, "
                      "fixed_copper hoisted #653, zone-inclusive parse_result)",
        },
        "exact_fc_violations_at_best": len(viol_best),
        "exact_fc_violations_at_candidate": len(viol_cand),
        "violations_at_best": viol_best,
        "violations_at_candidate": viol_cand,
        "joint_zone_clear": {
            "ref": "K3", "cap_mm": CAP_MM, "grid_cells": n_cells,
            "zone_clear_cells": len(zone_clear),
            "first_clearing_position": zone_clear[0] if zone_clear else None,
        },
        "joint_zone_clear_c27": {
            "ref": "C27", "cap_mm": CAP_MM, "grid_cells": n_c27,
            "zone_clear_cells": len(zc_c27),
            "first_clearing_position": zc_c27[0] if zc_c27 else None,
        },
        "per_conflict_joint_clear": conflict_rows,
        "compound": comp,
        "compound_board_wide": comp_wide,
        "drop_one_analysis": drop,
        "caller_attempts": caller_rows,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True,
                                      default=str))
    print(f"\nwrote {OUT_SUMMARY}")

    _prov = git_provenance()
    with OUT_CSV.open("w", newline="") as f:
        f.write(f"# provenance: commit={_prov['commit']} dirty={_prov['dirty']}\n")
        w = csv.DictWriter(f, fieldnames=list(conflict_rows[0].keys()) if conflict_rows
                           else ["conflict"])
        w.writeheader()
        w.writerows(conflict_rows)
    print(f"wrote {OUT_CSV}")

    if caller_rows:
        OUT_CALLER.write_text(json.dumps(
            {"provenance": git_provenance(), "attempts": caller_rows},
            indent=2, sort_keys=True, default=str))
        print(f"wrote {OUT_CALLER}")


if __name__ == "__main__":
    main()
