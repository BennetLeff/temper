#!/usr/bin/env python3
"""Feasibility evidence for the mains<->SELV isolation-barrier plan (2026-08-01).

Answers OQ1 (achievable corridor width), OQ2 (isolator-BOM dependency) and
OQ3 (corridor axis/position/HV-side) of
docs/plans/2026-08-01-001-feat-mains-selv-isolation-barrier-plan.md with
numbers computed from the real board, using the SAME geometry model as the
gate itself (scripts/check_isolation_keepout.py):

  - pads are classified by EXACT net-name match against
    elec/domain_manifest.yaml's HV/SELV net lists (never substring);
  - each pad is modelled as a disk of its exact, shape-aware bounding radius
    (temper_placer.core.pad_geometry.pad_bounding_radius -- the same
    conservative, never-under-approximating model the gate's intrusion check
    uses);
  - a straight corridor is a full-height/full-width strip that must (a) not
    intersect ANY pad disk, (b) put every HV-net pad disk on one side and
    every SELV-net pad disk on the other (the gate's far-side + intrusion
    semantics; the disk condition is strictly stronger than the gate's
    center-based far-side test, so it is the binding one).

Isolator straddle feasibility uses the placer's own per-component evaluation
(temper_placer.placer.cp_sat.isolation_barrier.evaluate_isolator_feasibility
over the real board's local-frame pad geometry), so the per-isolator numbers
here are the same numbers the CP-SAT hard-barrier constraint encodes.

Run from the repo root:
    uv run --no-sync python docs/evidence/2026-08-01-isolation-barrier-feasibility.py
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import yaml
from kiutils.board import Board

REPO_ROOT = Path(__file__).resolve().parents[2]
BOARD_PATH = REPO_ROOT / "pcb" / "temper.kicad_pcb"
MANIFEST_PATH = REPO_ROOT / "elec" / "domain_manifest.yaml"

sys.path.insert(0, str(REPO_ROOT / "packages" / "temper-placer" / "src"))

from temper_placer.core.pad_geometry import pad_bounding_radius  # noqa: E402
from temper_placer.geometry.kicad_transform import rotate_local_to_world_deg  # noqa: E402

WIDTHS_MM = (8.0, 10.0, 12.6)
BOARD_INSET = 0.5  # corridor edges must be strictly inside the outline (>inset from each edge)

# ---------------------------------------------------------------------------
# 1. Load manifest + board (gate-equivalent pad model)
# ---------------------------------------------------------------------------


@dataclass
class Pad:
    ref: str
    number: str
    x: float
    y: float
    radius: float
    net: str


def load_manifest(path: Path) -> tuple[frozenset[str], frozenset[str]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    domains = data["domains"]
    return frozenset(domains["HV"]["nets"]), frozenset(domains["SELV"]["nets"])


def load_pads(path: Path) -> tuple[list[Pad], tuple[float, float, float, float]]:
    """Extract pads in world coordinates with the gate's exact model.

    Returns (pads, board_outline_bbox) where bbox = (x_min, y_min, x_max, y_max).
    """
    board = Board.from_file(str(path))
    pads: list[Pad] = []
    for fp in board.footprints:
        props = fp.properties or {}
        ref = props.get("Reference") or "<noref>"
        fx, fy = fp.position.X, fp.position.Y
        fangle = fp.position.angle or 0.0
        flipped = str(fp.layer or "F.Cu").startswith("B.")
        for pad in fp.pads:
            net = pad.net.name if pad.net is not None else ""
            lx, ly = pad.position.X, pad.position.Y
            if flipped:
                lx = -lx
            dx, dy = rotate_local_to_world_deg(lx, ly, fangle)
            size_x = getattr(pad.size, "X", 0.0) or 0.0
            size_y = getattr(pad.size, "Y", 0.0) or 0.0
            shape = getattr(pad, "shape", None) or "rect"
            rratio = getattr(pad, "roundrectRatio", None)
            if rratio is None:
                rratio = 0.25
            radius = pad_bounding_radius(size_x, size_y, shape, rratio)
            pads.append(Pad(ref=ref, number=pad.number, x=fx + dx, y=fy + dy, radius=radius, net=net))

    outline = None
    for item in board.graphicItems:
        if getattr(item, "layer", None) == "Edge.Cuts" and type(item).__name__ == "GrPoly":
            coords = getattr(item, "coordinates", None)
            if coords:
                xs = [pt.X for pt in coords]
                ys = [pt.Y for pt in coords]
                outline = (min(xs), min(ys), max(xs), max(ys))
                break
    if outline is None:
        raise SystemExit("no Edge.Cuts GrPoly found")
    return pads, outline


# ---------------------------------------------------------------------------
# 2. Corridor analysis
# ---------------------------------------------------------------------------


def _disk_overlaps_rect(px, py, pr, x0, y0, x1, y1) -> bool:
    """Exact axis-aligned-rect vs disk intersection (2D)."""
    cx = max(x0, min(px, x1))
    cy = max(y0, min(py, y1))
    return (px - cx) ** 2 + (py - cy) ** 2 <= pr * pr + 1e-9


def corridor_axis_gap(pads, hv_nets, selv_nets, axis: int, exclude_refs: frozenset[str] | None):
    """Raw edge-to-edge gap between the HV pad region and the SELV pad region
    on one axis, over pads whose CENTER is inside the board bbox (the gate's
    far-side check only reasons about pads whose centers land in a partition
    region; staged pads outside the outline are reported separately).

    axis: 0 = X (vertical corridor), 1 = Y (horizontal corridor).
    Returns dict with 'HV_lo' and 'HV_hi' convention gaps (mm).
    """
    coord = lambda p: p.x if axis == 0 else p.y  # noqa: E731
    lo = min(coord(p) - p.radius for p in pads)
    hi = max(coord(p) + p.radius for p in pads)

    def in_board(p: Pad) -> bool:
        return (bx0 <= p.x <= bx1) and (by0 <= p.y <= by1)

    hv = [p for p in pads if p.net in hv_nets and in_board(p)]
    sv = [p for p in pads if p.net in selv_nets and in_board(p)]
    if exclude_refs:
        hv = [p for p in hv if p.ref not in exclude_refs]
        sv = [p for p in sv if p.ref not in exclude_refs]
    if not hv or not sv:
        return None

    # Which pads set the region extents (drives the OQ2 finding):
    coord = lambda p: p.x if axis == 0 else p.y  # noqa: E731
    max_hv_pad = max(hv, key=lambda p: coord(p) + p.radius)
    min_sv_pad = min(sv, key=lambda p: coord(p) - p.radius)
    max_sv_pad = max(sv, key=lambda p: coord(p) + p.radius)
    min_hv_pad = min(hv, key=lambda p: coord(p) - p.radius)
    print(f"    extent pads: HV hi-edge {max_hv_pad.ref}.{max_hv_pad.number} ({coord(max_hv_pad) + max_hv_pad.radius:.2f}) | "
          f"SELV lo-edge {min_sv_pad.ref}.{min_sv_pad.number} ({coord(min_sv_pad) - min_sv_pad.radius:.2f}) | "
          f"SELV hi-edge {max_sv_pad.ref}.{max_sv_pad.number} | HV lo-edge {min_hv_pad.ref}.{min_hv_pad.number}")

    # HV on the lo side, SELV on the hi side:
    max_hv_hi_edge = max(coord(p) + p.radius for p in hv)   # HV region's hi edge
    min_sv_lo_edge = min(coord(p) - p.radius for p in sv)   # SELV region's lo edge
    gap_hv_lo = min_sv_lo_edge - max_hv_hi_edge

    # SELV on the lo side, HV on the hi side:
    max_sv_hi_edge = max(coord(p) + p.radius for p in sv)
    min_hv_lo_edge = min(coord(p) - p.radius for p in hv)
    gap_hv_hi = min_hv_lo_edge - max_sv_hi_edge

    return {"HV_lo": gap_hv_lo, "HV_hi": gap_hv_hi}


def corridor_exists(pads, hv_nets, selv_nets, axis, W, board_rect, exclude_refs=None,
                    convention="HV_lo"):
    """Does a fully-clear full-span corridor of width W exist, and at which
    positions?  Returns (exists, valid_c_interval_or_None).

    convention 'HV_lo' = HV domain on the small-coordinate side (HV left for
    a vertical corridor / HV top for a horizontal one); 'HV_hi' = the reverse.
    """
    x0, y0, x1, y1 = board_rect
    span = (x1 - x0) if axis == 0 else (y1 - y0)
    # Corridor placement range along its normal axis, strictly inside the board:
    c_lo_allowed, c_hi_allowed = BOARD_INSET, span - W - BOARD_INSET
    if c_hi_allowed <= c_lo_allowed:
        return False, None

    def coord(p):
        return p.x if axis == 0 else p.y

    def normal(p):
        return p.y if axis == 0 else p.x

    def in_board(p: Pad) -> bool:
        return (x0 <= p.x <= x1) and (y0 <= p.y <= y1)

    # Domain side requirements (disk-based, gate-binding condition):
    if convention == "HV_lo":
        side_hv = [p for p in pads if p.net in hv_nets and in_board(p) and (exclude_refs is None or p.ref not in exclude_refs)]
        side_sv = [p for p in pads if p.net in selv_nets and in_board(p) and (exclude_refs is None or p.ref not in exclude_refs)]
    else:
        side_hv = [p for p in pads if p.net in selv_nets and in_board(p) and (exclude_refs is None or p.ref not in exclude_refs)]
        side_sv = [p for p in pads if p.net in hv_nets and in_board(p) and (exclude_refs is None or p.ref not in exclude_refs)]

    lo_edge_req = max((coord(p) + p.radius for p in side_sv), default=-math.inf)
    hi_edge_req = min((coord(p) - p.radius for p in side_hv), default=math.inf)

    # c (the corridor's lo edge) must satisfy:
    #   c >= lo_edge_req          (all "lo side" pads fully left of c)
    #   c + W <= hi_edge_req      (all "hi side" pads fully right of c+W)
    c_min = max(c_lo_allowed, lo_edge_req)
    c_max = min(c_hi_allowed, hi_edge_req - W)
    if c_max < c_min:
        return False, None

    # All remaining pads (unclassified nets, plus any excluded/island pads)
    # must simply not intersect the corridor rect. Each such pad forbids
    # c in (coord - radius - W, coord + radius) PROVIDED its disk overlaps
    # the corridor's Y (or X) span.
    forbidden: list[tuple[float, float]] = []
    for p in pads:
        is_lo_side = p in side_sv
        is_hi_side = p in side_hv
        if is_lo_side or is_hi_side:
            continue
        # pad disk intersects the full-span strip?
        if not _disk_overlaps_rect(coord(p), normal(p), p.radius,
                                   c_min, y0 if axis == 0 else x0,
                                   c_max + W, y1 if axis == 0 else x1):
            continue
        f_lo = coord(p) - p.radius - W
        f_hi = coord(p) + p.radius
        forbidden.append((f_lo, f_hi))

    # subtract forbidden intervals from [c_min, c_max]
    valid: list[tuple[float, float]] = [(c_min, c_max)]
    for f_lo, f_hi in sorted(forbidden):
        new_valid = []
        for v_lo, v_hi in valid:
            if f_hi <= v_lo or f_lo >= v_hi:
                new_valid.append((v_lo, v_hi))
            else:
                if f_lo > v_lo:
                    new_valid.append((v_lo, min(f_lo, v_hi)))
                if f_hi < v_hi:
                    new_valid.append((max(f_hi, v_lo), v_hi))
        valid = new_valid
        if not valid:
            return False, None
    return True, valid


def component_drift(pads, hv_nets, selv_nets, axis, W, c, board_rect, isolators,
                    convention="HV_lo", exclude_refs=None):
    """Per-component drift (mm along the corridor normal axis) required to
    make corridor [c, c+W] valid for the domain-only bulk.

    Domain-only components are shifted as rigid bodies to their required side.
    Isolators are handled by their own straddle feasibility (see
    isolator_straddle_report) -- a pure translation cannot change an
    isolator's own HV/SELV cluster gap, so an isolator whose gap < W is not
    fixable by drift at all (it needs rotation or a BOM/footprint change).
    Returns (drift_by_ref, movers, total, max_drift).
    """
    x0, y0, x1, y1 = board_rect

    def coord(p):
        return p.x if axis == 0 else p.y

    def normal(p):
        return p.y if axis == 0 else p.x

    # group pads by component ref
    by_ref: dict[str, list[Pad]] = {}
    for p in pads:
        by_ref.setdefault(p.ref, []).append(p)

    drift_by_ref: dict[str, float] = {}
    for ref, comp_pads in by_ref.items():
        if ref in isolators:
            continue  # handled separately (straddle feasibility)
        # Pads whose CENTER is outside the board outline are invisible to the
        # gate's far-side check (they sit in neither partition region) and
        # cannot intrude an in-board corridor (their disks don't reach it) --
        # e.g. C27, staged outside the outline. Skip them for drift too.
        comp_pads = [p for p in comp_pads if x0 <= p.x <= x1 and y0 <= p.y <= y1]
        if not comp_pads:
            continue
        hv_pads = [p for p in comp_pads if p.net in hv_nets]
        sv_pads = [p for p in comp_pads if p.net in selv_nets]
        is_hv_only = bool(hv_pads) and not sv_pads
        is_sv_only = bool(sv_pads) and not hv_pads
        is_mixed = bool(hv_pads) and bool(sv_pads)
        # mixed-but-not-isolator shouldn't happen on this board; treat as isolator-free
        if convention == "HV_lo":
            hv_side_required, sv_side_required = True, True
        else:
            hv_side_required, sv_side_required = True, True
        del hv_side_required, sv_side_required

        if is_hv_only or is_sv_only or is_mixed:
            # Domain pads must land on their side of the corridor.
            if convention == "HV_lo":
                hv_lo = True
            else:
                hv_lo = False
            if hv_lo:
                need_lo = hv_pads  # these must be fully left of c
                need_hi = sv_pads  # fully right of c+W
            else:
                need_lo = sv_pads
                need_hi = hv_pads
            d_lo = max((coord(p) + p.radius - c for p in need_lo), default=-math.inf)
            d_hi = max(((c + W) - (coord(p) - p.radius) for p in need_hi), default=-math.inf)
            drift = max(0.0, d_lo, d_hi)
        else:
            # Unclassified: pads may sit on either side but must clear the
            # corridor rect.  Shift the body the minimum of (left-clearing,
            # right-clearing) shifts.
            d_left = 0.0
            d_right = 0.0
            for p in comp_pads:
                # does this pad's disk intersect the corridor rect?
                if not _disk_overlaps_rect(coord(p), normal(p), p.radius, c, y0 if axis == 0 else x0, c + W, y1 if axis == 0 else x1):
                    continue
                d_left = max(d_left, coord(p) + p.radius - c)         # shift body left
                d_right = max(d_right, (c + W) - (coord(p) - p.radius))  # shift body right
            drift = min(d_left, d_right)
        if drift > 0.01:
            drift_by_ref[ref] = drift

    total = sum(drift_by_ref.values())
    movers = len(drift_by_ref)
    max_drift = max(drift_by_ref.values(), default=0.0)
    return drift_by_ref, movers, total, max_drift


def sweep_best_corridor(pads, hv_nets, selv_nets, axis, W, board_rect, isolators,
                        convention="HV_lo", step=0.25):
    """Find the corridor position (c) minimizing total domain-only drift."""
    x0, y0, x1, y1 = board_rect
    span = (x1 - x0) if axis == 0 else (y1 - y0)
    best = None
    c = BOARD_INSET
    while c + W <= span - BOARD_INSET:
        drift_by_ref, movers, total, max_drift = component_drift(
            pads, hv_nets, selv_nets, axis, W, c, board_rect, isolators, convention)
        if best is None or total < best[0]:
            best = (total, c, drift_by_ref, movers, max_drift)
        c += step
    return best


def isolator_straddle_report(netlist, hv_nets, selv_nets):
    """Per-isolator HV/SELV pad-cluster gaps via the placer's own machinery."""
    from temper_placer.placer.cp_sat.isolation_barrier import (
        compute_pad_groups,
        evaluate_isolator_feasibility,
    )
    rows = []
    for comp in netlist.components:
        groups = compute_pad_groups(comp, hv_nets, selv_nets)
        if not groups.hv_pads or not groups.selv_pads:
            continue
        for axis in (0, 1):
            f = evaluate_isolator_feasibility(groups, corridor_width_mm=8.0, barrier_axis=axis)
            rows.append({
                "ref": comp.ref,
                "axis": "X" if axis == 0 else "Y",
                "gap_x": f.gap_x_mm,
                "gap_y": f.gap_y_mm,
                "achievable": f.achievable_gap_mm,
                "rot": f.chosen_rotation,
                "hv_is_lo": f.hv_is_lo,
            })
    return rows


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    hv_nets, selv_nets = load_manifest(MANIFEST_PATH)
    pads, board_rect = load_pads(BOARD_PATH)
    bx0, by0, bx1, by1 = board_rect

    print(f"Board outline bbox: x [{bx0}, {bx1}] y [{by0}, {by1}]  ({bx1-bx0:.1f} x {by1-by0:.1f} mm)")
    print(f"Pads total: {len(pads)}")

    # ---- partition ----
    comp_pads: dict[str, set[str]] = {}
    for p in pads:
        comp_pads.setdefault(p.ref, set()).add(p.net)
    hv_only, sv_only, isolators, unclassified = [], [], [], []
    for ref, nets in sorted(comp_pads.items()):
        t_hv = bool(nets & hv_nets)
        t_sv = bool(nets & selv_nets)
        if t_hv and t_sv:
            isolators.append(ref)
        elif t_hv:
            hv_only.append(ref)
        elif t_sv:
            sv_only.append(ref)
        else:
            unclassified.append(ref)

    print(f"Components: HV-only={len(hv_only)} SELV-only={len(sv_only)} isolators={len(isolators)} unclassified={len(unclassified)}")
    print(f"Isolators: {sorted(isolators)}")
    print(f"Unclassified: {sorted(unclassified)}")

    hv_pads = [p for p in pads if p.net in hv_nets]
    sv_pads = [p for p in pads if p.net in selv_nets]
    in_board = [p for p in pads if bx0 <= p.x <= bx1 and by0 <= p.y <= by1]
    staged = [p for p in pads if not (bx0 <= p.x <= bx1 and by0 <= p.y <= by1)]
    print(f"HV pads: {len(hv_pads)}  SELV pads: {len(sv_pads)}  pads outside outline (staged): {len(staged)}")
    if staged:
        refs = sorted({p.ref for p in staged})
        print(f"  staged refs: {refs}")
        for p in staged[:10]:
            print(f"    staged pad {p.ref}.{p.number} net={p.net!r} at ({p.x:.2f}, {p.y:.2f}) r={p.radius:.3f}")

    # ---- repro: 10mm columns ----
    print("\n--- 10mm full-height column check (vertical, x=20..172) ---")
    mixed = 0
    for col in range(0, 15):
        x0c, x1c = 20 + 10 * col, 20 + 10 * (col + 1)
        c_hv = {p.ref for p in hv_pads if p.x >= x0c and p.x <= x1c and p.ref not in isolators}
        c_sv = {p.ref for p in sv_pads if p.x >= x0c and p.x <= x1c and p.ref not in isolators}
        tag = "BOTH" if (c_hv and c_sv) else ("HV" if c_hv else ("SELV" if c_sv else "empty"))
        if c_hv and c_sv:
            mixed += 1
        print(f"  col {x0c:.0f}-{x1c:.0f}: {tag}  (HV {len(c_hv)}, SELV {len(c_sv)})")
    print(f"  columns with both domains: {mixed}/15")

    # ---- repro: nearest cross-domain cross-component pad pair ----
    print("\n--- nearest cross-domain cross-component pad pair (edge-to-edge, in-board) ---")
    hv_ib = [p for p in hv_pads if p in in_board]
    sv_ib = [p for p in sv_pads if p in in_board]
    best_dist = math.inf
    best_pair = None
    pairs_lt8 = 0
    comp_pairs_lt8 = set()
    for p1 in hv_ib:
        for p2 in sv_ib:
            if p1.ref == p2.ref:
                continue
            d = math.hypot(p1.x - p2.x, p1.y - p2.y) - p1.radius - p2.radius
            if d < 8.0:
                pairs_lt8 += 1
                comp_pairs_lt8.add(tuple(sorted((p1.ref, p2.ref))))
            if d < best_dist:
                best_dist = d
                best_pair = (p1, p2)
    print(f"nearest HV-SELV cross-component pad pair: {best_dist:.3f} mm ({best_pair[0].ref}.{best_pair[0].number} net={best_pair[0].net!r} <-> {best_pair[1].ref}.{best_pair[1].number} net={best_pair[1].net!r})")
    print(f"pad pairs within 8.0mm: {pairs_lt8} across {len(comp_pairs_lt8)} distinct component pairs")
    print("component pairs:")
    for pair in sorted(comp_pairs_lt8):
        print(f"  {pair[0]} <-> {pair[1]}")

    # ---- corridor feasibility ----
    isolators_set = frozenset(isolators)
    print("\n--- corridor feasibility (as-is, all pads) ---")
    for axis, axis_name in ((0, "X (vertical corridor, splits left/right)"), (1, "Y (horizontal corridor, splits top/bottom)")):
        gaps = corridor_axis_gap(pads, hv_nets, selv_nets, axis, None)
        print(f"\nOrientation {axis_name}")
        for conv, label in (("HV_lo", "HV on lo side"), ("HV_hi", "HV on hi side")):
            gap = gaps[conv]
            print(f"  {label}: raw region gap = {gap:+.3f} mm")
            for W in WIDTHS_MM:
                exists, valid = corridor_exists(pads, hv_nets, selv_nets, axis, W, board_rect, None, conv)
                if exists:
                    vlo = min(v[0] for v in valid)
                    vhi = max(v[1] for v in valid)
                    print(f"    W={W}: CORRIDOR EXISTS  c in [{vlo:.2f}, {vhi:.2f}]")
                else:
                    print(f"    W={W}: no corridor")
        # best drift position per width (HV_lo convention)
        for W in WIDTHS_MM:
            total, c, drift_by_ref, movers, max_drift = sweep_best_corridor(
                pads, hv_nets, selv_nets, axis, W, board_rect, isolators_set, "HV_lo")
            print(f"  [HV_lo, W={W}] best c={c:.2f}  total domain drift={total:.1f} mm, movers={movers}, max single={max_drift:.2f} mm")

    # ---- isolator straddle report ----
    print("\n--- isolator HV<->SELV pad-cluster gaps (placer's evaluate_isolator_feasibility) ---")
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    parsed = parse_kicad_pcb(BOARD_PATH)
    netlist = parsed.netlist
    rows = isolator_straddle_report(netlist, hv_nets, selv_nets)
    by_ref: dict[str, dict] = {}
    for r in rows:
        by_ref.setdefault(r["ref"], {})[r["axis"]] = r
    for ref in sorted(by_ref):
        rx, ry = by_ref[ref]["X"], by_ref[ref]["Y"]
        ach = max(rx["achievable"], ry["achievable"])
        feas = {W: (ach >= W) for W in WIDTHS_MM}
        print(f"  {ref}: gap_x={rx['gap_x']:+.3f} gap_y={ry['gap_y']:+.3f} "
              f"achievable(X)={rx['achievable']:.3f} achievable(Y)={ry['achievable']:.3f} "
              f"max={ach:.3f}  feasible@ {', '.join(f'{W}:{feas[W]}' for W in WIDTHS_MM)}")

    # ---- OQ2: isolators re-homed (excluded from domain extents) ----
    print("\n--- OQ2: corridor feasibility with isolator pads excluded from domain extents ---")
    for axis, axis_name in ((0, "X (vertical)"), (1, "Y (horizontal)")):
        gaps = corridor_axis_gap(pads, hv_nets, selv_nets, axis, isolators_set)
        print(f"\nOrientation {axis_name}")
        for conv, label in (("HV_lo", "HV on lo side"), ("HV_hi", "HV on hi side")):
            gap = gaps[conv]
            print(f"  {label}: raw region gap (isolators re-homed) = {gap:+.3f} mm")
            for W in WIDTHS_MM:
                exists, valid = corridor_exists(pads, hv_nets, selv_nets, axis, W, board_rect, isolators_set, conv)
                if exists:
                    vlo = min(v[0] for v in valid)
                    vhi = max(v[1] for v in valid)
                    print(f"    W={W}: CORRIDOR EXISTS  c in [{vlo:.2f}, {vhi:.2f}]")
                else:
                    print(f"    W={W}: no corridor")

    # ---- drift detail at best position for W=8.0 (HV_lo) per orientation ----
    print("\n--- drift detail (HV_lo, W=8.0, best c) ---")
    for axis, axis_name in ((0, "X"), (1, "Y")):
        total, c, drift_by_ref, movers, max_drift = sweep_best_corridor(
            pads, hv_nets, selv_nets, axis, 8.0, board_rect, isolators_set, "HV_lo")
        print(f"\n{axis_name}: best c={c:.2f}, total={total:.1f}mm, movers={movers}, max={max_drift:.2f}mm")
        for ref, d in sorted(drift_by_ref.items(), key=lambda kv: -kv[1])[:25]:
            domain = ("HV-only" if ref in hv_only else "SELV-only" if ref in sv_only else "unclass")
            print(f"  {ref:6s} ({domain:9s}) drift {d:7.2f} mm")
        if len(drift_by_ref) > 25:
            print(f"  ... and {len(drift_by_ref) - 25} more")

    # ---- edge / enclosure constraints ----
    print("\n--- board edge constraints (OQ4 input) ---")
    for p in sorted(hv_pads + sv_pads, key=lambda q: min(q.x - bx0, bx1 - q.x, q.y - by0, by1 - q.y))[:5]:
        m = min(p.x - bx0, bx1 - p.x, p.y - by0, by1 - p.y)
        print(f"  {p.ref}.{p.number} net={p.net!r} at ({p.x:.2f},{p.y:.2f}) r={p.radius:.2f}  closest-to-edge {m:.2f} mm")
    print(f"  board size {bx1-bx0:.0f}x{by1-by0:.0f}mm; corridor spans full {by1-by0:.0f}mm (X) / {bx1-bx0:.0f}mm (Y)")
