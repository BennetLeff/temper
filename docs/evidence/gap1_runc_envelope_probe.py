# provenance: commit=5d574d4c1d33c42441a84ebd753f65068f514532 dirty=false
#!/usr/bin/env python3
"""Gap-1 run-C envelope probe: does relaxing the displacement cap unblock the
zone-inclusive fixed-copper solve?

# provenance: commit=5d574d4c1d33c42441a84ebd753f65068f514532 dirty=false

Companion to ``docs/evidence/2026-08-03-gap1-runC-envelope-probe.md``.
Re-derives the run-C formulation (issue #523, "gap 1") against the CURRENT
board at ``pcb/temper.kicad_pcb`` (origin/main post-#602 board write: K3 is
the RT314012 swap, C27 at (28.62, 222.0) — the written board IS the
best-known placement) and probes whether ANY zone-inclusive solve terminates
feasible as the displacement envelope is relaxed.

Variant matrix (all with fixed rotations, FREE={K3,C27}, fixed-copper margin
0.05mm, same domain/keepaway SeparatedConstraints as the run-B/C recipe):

  * B_60_s0    -- no-zones fixed copper (repair recipe), cap 60mm, seed 0
                  (feasible + validator-clean is the #602 reproduction).
  * C_60_s0    -- zone-inclusive fixed copper, cap 60mm, seed 0 (baseline
                  infeasible reproduction).
  * C_120_s0   -- zone-inclusive, GLOBAL cap 120mm, seed 0. The brief's
                  probe: ``max_displacement_mm`` is a single global cap in
                  the recipe (applied to every ref in
                  ``minimize_displacement_to``), so a C27-only 120mm cannot
                  be expressed without a src/ change; 120 global is the
                  comparable relaxation.
  * C_120_s1   -- zone-inclusive, global cap 120mm, seed 1 (seed variation).
  * C_c27x_s0  -- zone-inclusive, cap 60mm for every ref EXCEPT C27 which is
                  EXCLUDED from ``minimize_displacement_to`` entirely
                  (unbounded displacement for C27; the strongest C27-only
                  relaxation expressible with the recipe's API).
  * C_240_s0   -- zone-inclusive, global cap 240mm, seed 0 (stronger
                  envelope, only if 120 stays infeasible this bounds the
                  "any envelope at all" question).

Every zone-inclusive variant writes its unsat core (when infeasible) to
``gap1_runc_envelope_matrix.json`` together with the per-variant status /
solve time / core size. ``--analyze-only`` re-derives the deterministic
violation set at the best-known placement (direct constraint evaluation,
the same methodology as ``gap1_runc_pairs_corrected.py`` — cores are
non-minimal and search-order-dependent, so the *core contents* are never
the measurement, only the constraint-evaluated verdicts are):

  * per-pair box-bar vs exact-copper verdicts for the run-C core pairs
    (corrected ``(parts[-4], parts[-3])`` ref parsing);
  * the exact fixed-copper audit (pad vs segment/via/zone/pad items),
    broken out by item kind and net;
  * per violating (ref, pad, zone) the exact clearance at the best
    placement vs the zone's required margin, plus a grid reachability scan
    of the owning component's displacement envelope answering "is this
    zone's demand met anywhere this component can actually go?".

NO src/ changes. Read-only w.r.t. ``pcb/temper.kicad_pcb``.

Usage:
    uv run --no-sync python docs/evidence/gap1_runc_envelope_probe.py [--solve-only] [--analyze-only] [--variant NAME] [--timeout-ms N]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
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
from temper_placer.placer.cp_sat import solve_placement  # noqa: E402
from temper_placer.placer.cp_sat.domain_clearance import (  # noqa: E402
    generate_domain_clearance_constraints,
    generate_unclassified_hv_keepaway_constraints,
)
from temper_placer.placer.cp_sat.model import CpSatModel  # noqa: E402
from temper_placer.requirements.validators.clearance import (  # noqa: E402
    IEC60335_REQUIREMENTS,
    VoltageDomain,
    _CopperModel,
    _domain_boundary_pairs,
    _nets_domain_map,
)

FREE = {"K3", "C27"}
MARGIN_FC_MM = 0.05
MARGIN_EPS = 1e-6
EDGE_MARGIN_MM = 0.5  # solver edge_margin constraint on every ref

OUT_MATRIX = REPO / "docs" / "evidence" / "gap1_runc_envelope_matrix.json"
OUT_ZONES = REPO / "docs" / "evidence" / "gap1_runc_envelope_zones.json"
OUT_ZONES_CSV = REPO / "docs" / "evidence" / "gap1_runc_envelope_zones.csv"
OUT_PAIRS_CSV = REPO / "docs" / "evidence" / "gap1_runc_envelope_pairs.csv"


def git_provenance():
    """(commit, dirty) at write time, so artifacts carry the tree they were
    produced on (docs/METHODOLOGY.md Sec 5) instead of a stale placeholder."""
    import subprocess
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
        cwd=str(REPO)).stdout.strip()
    dirty = bool(subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True,
        cwd=str(REPO)).stdout.strip())
    return {"commit": sha, "dirty": dirty}

# ---------------------------------------------------------------------------
# Variant matrix
# ---------------------------------------------------------------------------

VARIANT_DEFAULTS = {
    "fc": "zones",           # "zones" | "nozones"
    "cap_mm": 60.0,
    "seed": 0,
    "exclude_c27": False,    # drop C27 from minimize_displacement_to (unbounded)
    "timeout_ms": 90_000,
}

VARIANTS: dict[str, dict] = {
    "B_60_s0": {"fc": "nozones", "cap_mm": 60.0, "seed": 0, "timeout_ms": 180_000},
    "C_60_s0": {"fc": "zones", "cap_mm": 60.0, "seed": 0, "timeout_ms": 90_000},
    "C_120_s0": {"fc": "zones", "cap_mm": 120.0, "seed": 0, "timeout_ms": 90_000},
    "C_120_s1": {"fc": "zones", "cap_mm": 120.0, "seed": 1, "timeout_ms": 90_000},
    "C_c27x_s0": {"fc": "zones", "cap_mm": 60.0, "seed": 0, "exclude_c27": True, "timeout_ms": 90_000},
    "C_240_s0": {"fc": "zones", "cap_mm": 240.0, "seed": 0, "timeout_ms": 90_000},
    # Diagnostic: zone-inclusive but WITHOUT the three board-spanning pour
    # nets (DC_BUS_RTN / SW_NODE / +15V_LS). These pours are convex/non-
    # rectilinear so the encoder falls back to their AABB, which spans the
    # board -- if dropping them flips the solve to feasible, they (and by
    # extension their bbox encoding) are the infeasibility driver.
    "C_nobigpours_s0": {"fc": "no_big_pours", "cap_mm": 60.0, "seed": 0, "timeout_ms": 90_000},
}

BIG_POUR_NETS = {"DC_BUS_RTN", "SW_NODE", "+15V_LS"}


def parse_result_without_zones(pcb):
    from types import SimpleNamespace
    return SimpleNamespace(
        traces=pcb.traces,
        vias=pcb.vias,
        board=SimpleNamespace(
            zones=[],
            width=pcb.board.width,
            height=pcb.board.height,
            origin=getattr(pcb.board, "origin", (0.0, 0.0)),
        ),
    )


def parse_result_without_zone_nets(pcb, exclude_nets):
    """ParseResult whose zone list drops every zone on one of *exclude_nets*
    (diagnostic only -- the board file itself is untouched)."""
    from types import SimpleNamespace
    zones = [z for z in pcb.board.zones
             if not any(n in exclude_nets for n in z.net_classes)]
    return SimpleNamespace(
        traces=pcb.traces,
        vias=pcb.vias,
        board=SimpleNamespace(
            zones=zones,
            width=pcb.board.width,
            height=pcb.board.height,
            origin=getattr(pcb.board, "origin", (0.0, 0.0)),
        ),
    )


def run_variant(pcb, extra, *, name, cfg, timeout_ms_override=None):
    """One solve_placement call for a named variant."""
    pos = {c.ref: c.initial_position for c in pcb.netlist.components}
    rot = {c.ref: int(c.initial_rotation or 0) for c in pcb.netlist.components}
    hints = {ref: (x, y, rot[ref]) for ref, (x, y) in pos.items()}
    min_disp = {ref: (x, y) for ref, (x, y) in pos.items()}
    if cfg.get("exclude_c27"):
        min_disp.pop("C27", None)  # C27 unbounded; everyone else capped

    if cfg["fc"] == "zones":
        fc = {"parse_result": pcb, "free_refs": FREE, "margin_mm": MARGIN_FC_MM}
    elif cfg["fc"] == "no_big_pours":
        fc = {"parse_result": parse_result_without_zone_nets(pcb, BIG_POUR_NETS),
              "free_refs": FREE, "margin_mm": MARGIN_FC_MM}
    else:
        fc = {"parse_result": parse_result_without_zones(pcb),
              "free_refs": FREE, "margin_mm": MARGIN_FC_MM}

    timeout_ms = timeout_ms_override or cfg["timeout_ms"]
    t0 = time.monotonic()
    res = solve_placement(
        netlist=pcb.netlist,
        board=pcb.board,
        extra_constraints=extra,
        timeout_ms=timeout_ms,
        seed=cfg["seed"],
        hint_positions=hints,
        minimize_displacement_to=min_disp,
        max_displacement_mm=cfg["cap_mm"],
        fixed_rotations={ref: rot[ref] for ref in pos},
        fixed_copper=fc,
    )
    wall = round(time.monotonic() - t0, 1)
    names = [u["name"] for u in res.unsat_core]
    print(f"[{name}] status={res.status} solve={res.solve_time_ms:.1f}ms "
          f"wall={wall}s core={len(names)}")
    return {
        "status": res.status,
        "solve_time_ms": round(res.solve_time_ms, 1),
        "wall_s": wall,
        "seed": cfg["seed"],
        "cap_mm": cfg["cap_mm"],
        "exclude_c27": cfg.get("exclude_c27", False),
        "fc": cfg["fc"],
        "core_size": len(names),
        "core": names,
    }


# ---------------------------------------------------------------------------
# geometry helpers (identical semantics to the solver / validator)
# ---------------------------------------------------------------------------


def solver_box_geometry(pcb, positions, rotations):
    model = CpSatModel(units_per_mm=100)
    centers: dict[str, tuple[int, int]] = {}
    sizes: dict[str, tuple[int, int]] = {}
    for c in pcb.netlist.components:
        if c.ref not in positions:
            continue
        w = model.mm_to_units(float(c.bounds[0]))
        h = model.mm_to_units(float(c.bounds[1]))
        r = int(rotations.get(c.ref, int(c.initial_rotation or 0)) % 4)
        if r % 2 == 1:
            w, h = h, w
        centers[c.ref] = (model.mm_to_units(positions[c.ref][0]),
                          model.mm_to_units(positions[c.ref][1]))
        sizes[c.ref] = (w, h)
    return centers, sizes


def box_dist_mm(ra, rb, centers, sizes) -> float:
    cx_a, cy_a = centers[ra]
    cx_b, cy_b = centers[rb]
    hw_a, hh_a = sizes[ra][0] // 2, sizes[ra][1] // 2
    hw_b, hh_b = sizes[rb][0] // 2, sizes[rb][1] // 2
    dx = abs(cx_a - cx_b) - (hw_a + hw_b)
    dy = abs(cy_a - cy_b) - (hh_a + hh_b)
    return max(dx, dy) * 0.01


def build_placement_at(pcb, positions, rotations):
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


def edge_slack_mm(pcb, positions, rotations):
    model = CpSatModel(units_per_mm=100)
    board_w = float(pcb.board.width)
    board_h = float(pcb.board.height)
    out = {}
    for c in pcb.netlist.components:
        if c.ref not in positions:
            continue
        x, y = positions[c.ref]
        w = model.mm_to_units(float(c.bounds[0]))
        h = model.mm_to_units(float(c.bounds[1]))
        r = int(rotations.get(c.ref, int(c.initial_rotation or 0)) % 4)
        if r % 2 == 1:
            w, h = h, w
        cx = model.mm_to_units(x)
        cy = model.mm_to_units(y)
        left = cx - w // 2
        right = cx + w // 2
        bot = cy - h // 2
        top = cy + h // 2
        slack = min(left, bot, model.mm_to_units(board_w) - right,
                    model.mm_to_units(board_h) - top) * 0.01
        out[c.ref] = round(slack, 3)
    return out


# ---------------------------------------------------------------------------
# pair verdicts (corrected ref parsing — mirrors gap1_runc_pairs_corrected.py)
# ---------------------------------------------------------------------------

PREFIX_KIND = (
    ("sep_domain_clearance_", "domain"),
    ("sep_keepaway_unclassified_", "keepaway"),
    ("sep_netclass_autogen_", "netclass"),
    ("sep_courtyard_", "courtyard"),
)


def pair_from_name(name: str) -> tuple[str, str] | None:
    for prefix, _kind in PREFIX_KIND:
        if name.startswith(prefix):
            parts = name.split("_")
            if len(parts) < 4:
                return None
            return (parts[-4], parts[-3])
    return None


def pair_verdict_table(pcb, positions, rotations, core_names):
    """Per-pair box-bar vs exact-copper verdicts at *positions* for every
    pair named in the (non-deterministic) run-C core."""
    full, _vd, stats = load_real_board_placement()
    full_vd = stats["full_voltage_domains"]
    centers, sizes = solver_box_geometry(pcb, positions, rotations)
    placement = build_placement_at(pcb, positions, rotations)
    copper = _CopperModel(placement)
    nets_domain = _nets_domain_map(full, full_vd)

    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.placer.cp_sat.netclass_constraints import (
        generate_netclass_separated_constraints,
    )

    nc_rules = load_netclass_rules(_PLACER_DIR / "configs" / "netclass_rules.yaml")
    nc_constraints = generate_netclass_separated_constraints(
        pcb.netlist, pcb.netlist.components, nc_rules.design_rules
    )
    nc_margin: dict[tuple[str, str], float] = {}
    for c in nc_constraints:
        key = tuple(sorted([c.a, c.b]))
        nc_margin[key] = max(nc_margin.get(key, 0.0), c.min_distance_mm)

    wanted: dict[tuple[str, str, str], dict] = {}
    unmatched = 0
    for name in core_names:
        pair = pair_from_name(name)
        if pair is None:
            continue
        kind = next(k for p, k in PREFIX_KIND if name.startswith(p))
        ra, rb = pair
        if ra not in centers or rb not in centers:
            unmatched += 1
            continue
        key = (kind, ra, rb) if ra <= rb else (kind, rb, ra)
        wanted.setdefault(key, {"kind": kind, "ra": key[1], "rb": key[2],
                                "name": name})

    pair_info: dict[tuple[str, str], dict] = {}

    def consider(ra, rb, margin, dom_a=None, dom_b=None):
        key = tuple(sorted([ra, rb]))
        if key not in pair_info:
            pair_info[key] = {"margin": 0.0, "copper": None, "domains": "?"}
        info = pair_info[key]
        info["margin"] = max(info["margin"], margin)
        if dom_a is None:
            cd, _g, _l = copper.copper_distance(
                ra, VoltageDomain.ISOLATED, rb, VoltageDomain.ISOLATED, {})
            tag = "uncl<->HV"
        else:
            cd, _g, _l = copper.copper_distance(ra, dom_a, rb, dom_b, nets_domain)
            tag = f"{dom_a.value}<->{dom_b.value}"
        if info["copper"] is None or cd < info["copper"]:
            info["copper"] = cd
            info["domains"] = tag

    for (dom_a, dom_b, _ins), req in IEC60335_REQUIREMENTS.items():
        margin = max(req["min_clearance_mm"], req["min_creepage_mm"])
        for ca, cb in _domain_boundary_pairs(full, dom_a, dom_b, nets_domain):
            ra, rb = ca.get("ref"), cb.get("ref")
            if not isinstance(ra, str) or not isinstance(rb, str):
                continue
            if (ra in centers and rb in centers
                    and ("domain", ra, rb) in wanted
                    or ("domain", rb, ra) in wanted):
                consider(ra, rb, margin, dom_a, dom_b)

    keepaway_info: dict[tuple[str, str], dict] = {}

    def consider_keepaway(ra, rb, margin):
        key = tuple(sorted([ra, rb]))
        keepaway_info.setdefault(key, {"margin": margin, "copper": None})
        info = keepaway_info[key]
        info["margin"] = max(info["margin"], margin)
        cd, _g, _l = copper.copper_distance(ra, VoltageDomain.ISOLATED,
                                            rb, VoltageDomain.ISOLATED, {})
        if info["copper"] is None or cd < info["copper"]:
            info["copper"] = cd

    for name in core_names:
        if not name.startswith("sep_keepaway_unclassified_"):
            continue
        pair = pair_from_name(name)
        if pair is None:
            continue
        consider_keepaway(pair[0], pair[1], 8.0)

    rows = []
    n_box = n_copper = n_clean = 0
    for (kind, ra, rb), info in sorted(wanted.items()):
        key = tuple(sorted([ra, rb]))
        if kind == "domain":
            pi = pair_info.get(key)
            if pi is None:
                continue
            margin, cd, domains = pi["margin"], pi["copper"], pi["domains"]
        elif kind == "keepaway":
            ki = keepaway_info.get(key)
            if ki is None:
                continue
            margin, cd, domains = ki["margin"], ki["copper"], "uncl<->HV"
        else:
            if kind == "netclass":
                margin = nc_margin.get(key, 0.0)
                if margin <= 0.0:
                    continue
            else:
                margin = 0.4
            cd, _g, _l = copper.copper_distance(ra, VoltageDomain.ISOLATED,
                                                rb, VoltageDomain.ISOLATED,
                                                nets_domain)
            domains = ""
        bd = box_dist_mm(ra, rb, centers, sizes)
        if cd < margin - MARGIN_EPS:
            verdict = "COPPER-VIOLATION"
            n_copper += 1
        elif bd < margin - MARGIN_EPS:
            verdict = "BOX-BAR-BLOCKER"
            n_box += 1
        else:
            verdict = "CLEAN"
            n_clean += 1
        rows.append({
            "name": info["name"], "kind": kind, "refs": f"{ra},{rb}",
            "margin_mm": round(margin, 3),
            "box_dist_mm": round(bd, 3),
            "copper_dist_mm": round(cd, 3),
            "domains": domains,
            "verdict": verdict,
        })
    return rows, {"total": len(wanted), "unmatched_refs": unmatched,
                  "box_bar_blocker": n_box, "copper_violation": n_copper,
                  "clean": n_clean}


# ---------------------------------------------------------------------------
# zone-conflict reachability
# ---------------------------------------------------------------------------


def zone_reachability(pcb, pads_by_ref, items, positions, rotations,
                      cap_mm, step_mm=0.5):
    """For every (free pad, zone item) with clearance below the margin at
    *positions*, scan the owning component's displacement envelope for a
    center that clears THAT zone by the margin (rotation fixed), reporting
    the minimum displacement needed and whether the cap suffices.

    Deterministic, direct geometry: the same exact oracle
    (``exact_clearance_mm``) the R24 audit uses, over a uniform grid of the
    Manhattan envelope. Also gates on the solver's edge_margin (component
    box >= 0.5mm inside the board) so "where C27 can actually go" respects
    the same hard constraints the formulation itself enforces.
    """
    from temper_placer.placer.cp_sat.fixed_copper import (
        exact_clearance_mm,
        pad_world_rect,
    )

    board_w = float(pcb.board.width)
    board_h = float(pcb.board.height)
    bounds = {c.ref: (float(c.bounds[0]), float(c.bounds[1]))
              for c in pcb.netlist.components}

    zone_items = [i for i in items if i.kind == "zone"]
    rows = []
    seen = set()
    for ref, pads in pads_by_ref.items():
        center0 = positions.get(ref)
        if center0 is None:
            continue
        rot_idx = int(rotations.get(ref, 0))
        comp_nets = {p.net for p in pads if p.net}
        for pad in pads:
            for item in zone_items:
                if not (pad.layers & item.layers):
                    continue
                if item.net is not None and item.net in comp_nets:
                    continue
                rect0 = pad_world_rect(pad, center0, rot_idx)
                actual0 = exact_clearance_mm(rect0, item)
                if actual0 >= item.margin_mm - MARGIN_EPS:
                    continue
                key = (ref, pad.number, item.net)
                if key in seen:
                    continue
                seen.add(key)
                # Displacement envelope grid (Manhattan |dx|+|dy| <= cap).
                cx0, cy0 = center0
                bwx, bwy = bounds.get(ref, (0.0, 0.0))
                hw, hh = bwx / 2.0, bwy / 2.0
                best = None          # (disp, clearance) for a clearing center
                n_clear = 0
                n_cells = 0
                # step in 0.5mm; a 60mm cap -> ~57k cells worst case.
                x = cx0 - cap_mm
                while x <= cx0 + cap_mm + 1e-9:
                    y = cy0 - cap_mm
                    while y <= cy0 + cap_mm + 1e-9:
                        n_cells += 1
                        if abs(x - cx0) + abs(y - cy0) > cap_mm + 1e-9:
                            y += step_mm
                            continue
                        # edge_margin: component box inside board by 0.5mm
                        if (x - hw < EDGE_MARGIN_MM or y - hh < EDGE_MARGIN_MM
                                or x + hw > board_w - EDGE_MARGIN_MM
                                or y + hh > board_h - EDGE_MARGIN_MM):
                            y += step_mm
                            continue
                        rect = pad_world_rect(pad, (x, y), rot_idx)
                        clr = exact_clearance_mm(rect, item)
                        disp = abs(x - cx0) + abs(y - cy0)
                        if clr >= item.margin_mm - MARGIN_EPS:
                            n_clear += 1
                            if best is None or disp < best[0]:
                                best = (round(disp, 2), round(clr, 3), (x, y))
                        y += step_mm
                    x += step_mm
                rows.append({
                    "ref": ref, "pad": pad.number, "zone_net": item.net,
                    "zone_label": item.label,
                    "required_mm": item.margin_mm,
                    "clearance_at_best_mm": round(actual0, 4),
                    "best_placement": {"x_mm": round(cx0, 3), "y_mm": round(cy0, 3)},
                    "envelope_cap_mm": cap_mm,
                    "grid_step_mm": step_mm,
                    "grid_cells": n_cells,
                    "grid_clear_cells": n_clear,
                    "min_disp_to_clear_mm": best[0] if best else None,
                    "min_disp_clearance_mm": best[1] if best else None,
                    "clears_within_cap": best is not None,
                })
    return rows


def joint_zone_reachability(pcb, pads_by_ref, items, positions, rotations,
                           cap_mm, step_mm=0.5):
    """For each free ref, is there ANY center position within its
    displacement envelope (respecting the board edge_margin) at which EVERY
    (pad, zone) pair currently in violation clears its zone by the margin?

    This is the joint version of ``zone_reachability``: it answers "can this
    component go anywhere that satisfies all of its zone conflicts at once"
    -- the necessary condition for an envelope-only unblock of the zone
    side. A ref with zero clear cells is blocked by its zone set no matter
    where it goes (within the cap and the board), so those zone items are
    unsatisfiable at ANY reachable placement.
    """
    from temper_placer.placer.cp_sat.fixed_copper import (
        exact_clearance_mm,
        pad_world_rect,
    )

    board_w = float(pcb.board.width)
    board_h = float(pcb.board.height)
    bounds = {c.ref: (float(c.bounds[0]), float(c.bounds[1]))
              for c in pcb.netlist.components}

    zone_items = [i for i in items if i.kind == "zone"]
    # Per ref: the violating (pad, zone) pairs at the best placement.
    conflicts: dict[str, list[tuple]] = {}
    for ref, pads in pads_by_ref.items():
        center0 = positions.get(ref)
        if center0 is None:
            continue
        rot_idx = int(rotations.get(ref, 0))
        comp_nets = {p.net for p in pads if p.net}
        for pad in pads:
            for item in zone_items:
                if not (pad.layers & item.layers):
                    continue
                if item.net is not None and item.net in comp_nets:
                    continue
                rect0 = pad_world_rect(pad, center0, rot_idx)
                if exact_clearance_mm(rect0, item) < item.margin_mm - MARGIN_EPS:
                    conflicts.setdefault(ref, []).append((pad, item))

    rows = []
    for ref, pairs in conflicts.items():
        cx0, cy0 = positions[ref]
        rot_idx = int(rotations.get(ref, 0))
        bwx, bwy = bounds.get(ref, (0.0, 0.0))
        hw, hh = bwx / 2.0, bwy / 2.0
        n_cells = 0
        n_clear_all = 0
        first_clear = None
        x = cx0 - cap_mm
        while x <= cx0 + cap_mm + 1e-9:
            y = cy0 - cap_mm
            while y <= cy0 + cap_mm + 1e-9:
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
                for pad, item in pairs:
                    rect = pad_world_rect(pad, (x, y), rot_idx)
                    if exact_clearance_mm(rect, item) < item.margin_mm - MARGIN_EPS:
                        ok = False
                        break
                if ok:
                    n_clear_all += 1
                    if first_clear is None:
                        first_clear = {"x_mm": round(x, 2), "y_mm": round(y, 2),
                                       "disp_mm": round(abs(x - cx0) + abs(y - cy0), 2)}
                y += step_mm
            x += step_mm
        rows.append({
            "ref": ref,
            "n_conflicting_zone_pairs": len(pairs),
            "conflicting_pads": sorted({p.number for p, _i in pairs}),
            "conflicting_zone_nets": sorted({i.net for _p, i in pairs}),
            "envelope_cap_mm": cap_mm,
            "grid_step_mm": step_mm,
            "grid_cells": n_cells,
            "grid_cells_clearing_all_zones": n_clear_all,
            "any_position_clears_all_zones": n_clear_all > 0,
            "first_clearing_position": first_clear,
            "best_placement": {"x_mm": round(cx0, 3), "y_mm": round(cy0, 3)},
        })
    return rows


def encoded_zone_reachability(pcb, pads_by_ref, items, positions, rotations,
                             cap_mm, step_mm=0.5):
    """For each (free pad, zone item) in exact violation at the best
    placement, count envelope positions where the SOLVER'S ENCODED predicate
    clears the zone, alongside the exact-oracle count.

    This is the encoding-vs-geometry discriminator: the exact oracle answers
    "is the zone's demand met anywhere this component can actually go?"; the
    encoded predicate answers "would the solver even be able to see that
    position?". For bbox-fallback zones whose AABB spans the board, the
    encoded count is ~0 (the constraint is unsatisfiable on-board) while the
    exact count can be large -- proving the infeasibility is the encoding,
    not the zone geometry.
    """
    from temper_placer.placer.cp_sat.fixed_copper import (
        encoded_overlap,
        encoded_overlap_edges,
        exact_clearance_mm,
        pad_world_rect,
    )

    board_w = float(pcb.board.width)
    board_h = float(pcb.board.height)
    bounds = {c.ref: (float(c.bounds[0]), float(c.bounds[1]))
              for c in pcb.netlist.components}

    zone_items = [i for i in items if i.kind == "zone"]
    rows = []
    seen = set()
    for ref, pads in pads_by_ref.items():
        center0 = positions.get(ref)
        if center0 is None:
            continue
        rot_idx = int(rotations.get(ref, 0))
        comp_nets = {p.net for p in pads if p.net}
        bwx, bwy = bounds.get(ref, (0.0, 0.0))
        hw, hh = bwx / 2.0, bwy / 2.0
        cx0, cy0 = center0
        for pad in pads:
            for item in zone_items:
                if not (pad.layers & item.layers):
                    continue
                if item.net is not None and item.net in comp_nets:
                    continue
                rect0 = pad_world_rect(pad, center0, rot_idx)
                if exact_clearance_mm(rect0, item) >= item.margin_mm - MARGIN_EPS:
                    continue
                key = (ref, pad.number, item.net)
                if key in seen:
                    continue
                seen.add(key)
                n_exact = 0
                n_encoded = 0
                n_cells = 0
                x = cx0 - cap_mm
                while x <= cx0 + cap_mm + 1e-9:
                    y = cy0 - cap_mm
                    while y <= cy0 + cap_mm + 1e-9:
                        n_cells += 1
                        if abs(x - cx0) + abs(y - cy0) > cap_mm + 1e-9:
                            y += step_mm
                            continue
                        if (x - hw < EDGE_MARGIN_MM or y - hh < EDGE_MARGIN_MM
                                or x + hw > board_w - EDGE_MARGIN_MM
                                or y + hh > board_h - EDGE_MARGIN_MM):
                            y += step_mm
                            continue
                        rect = pad_world_rect(pad, (x, y), rot_idx)
                        if exact_clearance_mm(rect, item) >= item.margin_mm - MARGIN_EPS:
                            n_exact += 1
                        if item.edges:
                            if not encoded_overlap_edges(rect, item):
                                n_encoded += 1
                        else:
                            if not encoded_overlap(rect, item):
                                n_encoded += 1
                        y += step_mm
                    x += step_mm
                rows.append({
                    "ref": ref, "pad": pad.number, "zone_net": item.net,
                    "encoding": "EXACT" if item.edges else "BBOX-FALLBACK",
                    "envelope_cap_mm": cap_mm,
                    "grid_cells": n_cells,
                    "exact_clear_cells": n_exact,
                    "encoded_clear_cells": n_encoded,
                    "encoded_can_reach_exact_clear": n_encoded > 0,
                })
    return rows


def candidate_compound_audit(pcb, pads_by_ref, items, positions, rotations,
                             candidate):
    """Exact fixed-copper audit + pair verdicts at a candidate placement
    where the free refs are moved to per-ref zone-clear positions (from the
    joint reachability scan's first-clearing positions), everything else
    pinned. Shows whether the compound constraint set (zones + traces +
    vias + pads + pair separations) accepts the naive zone-clear placement
    or what new conflicts it introduces."""
    cand_pos = dict(positions)
    for ref, xy in candidate.items():
        cand_pos[ref] = (xy["x_mm"], xy["y_mm"])
    from temper_placer.placer.cp_sat.fixed_copper import audit_fixed_copper
    viol = audit_fixed_copper(pads_by_ref, items, cand_pos, rotations)
    from collections import Counter
    by_kind = dict(Counter(v.item_kind for v in viol))
    by_net = dict(Counter(f"{v.item_kind}:{v.item_net}" for v in viol))
    return {
        "candidate_positions": candidate,
        "exact_fc_violations": len(viol),
        "by_kind": by_kind,
        "by_net": by_net,
        "violations": [
            {"ref": v.ref, "pad": v.pad_number, "item_kind": v.item_kind,
             "item_net": v.item_net, "actual_mm": round(v.actual_mm, 4),
             "required_mm": v.required_mm}
            for v in viol[:40]
        ],
    }


# ---------------------------------------------------------------------------
# solve + analyze
# ---------------------------------------------------------------------------


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--solve-only", action="store_true")
    ap.add_argument("--analyze-only", action="store_true")
    ap.add_argument("--variant", default=None, help="run only this variant")
    ap.add_argument("--timeout-ms", type=int, default=None)
    args = ap.parse_args()

    pcb = parse_kicad_pcb(REPO / "pcb" / "temper.kicad_pcb")
    full, _vd, stats = load_real_board_placement()
    full_vd = stats["full_voltage_domains"]
    all_refs = {c.ref for c in pcb.netlist.components}
    dc = generate_domain_clearance_constraints(full, full_vd, component_refs=all_refs)
    kw = generate_unclassified_hv_keepaway_constraints(full, full_vd, component_refs=all_refs)
    extra = dc + kw
    print(f"refs={len(all_refs)} domain={len(dc)} keepaway={len(kw)} total={len(extra)}")

    matrix_path = OUT_MATRIX
    matrix = {}
    if matrix_path.exists():
        matrix = json.loads(matrix_path.read_text())
        matrix = matrix.get("variants", {})

    if not args.analyze_only:
        names = [args.variant] if args.variant else list(VARIANTS)
        for name in names:
            cfg = dict(VARIANT_DEFAULTS, **VARIANTS[name])
            if name in matrix and matrix[name].get("status"):
                print(f"[{name}] cached status={matrix[name]['status']}")
                continue
            matrix[name] = run_variant(pcb, extra, name=name, cfg=cfg,
                                       timeout_ms_override=args.timeout_ms)
            OUT_MATRIX.write_text(json.dumps(
                {"provenance": git_provenance(),
                 "variants": matrix}, indent=2, sort_keys=True))
            print(f"wrote {OUT_MATRIX}")

    if args.solve_only:
        return

    # ---- deterministic analysis at the best-known placement --------------
    # Best-known placement: the current board. The #602 write IS the run-B
    # result, so the parser's initial positions ARE the best-known placement
    # (C27 at (28.62, 222.0) normalized; K3 the RT314012 at (58.08, 11.18)-
    # style coordinates on the current board). The B_60_s0 solve above
    # independently confirms that placement is feasible.
    pos = {c.ref: c.initial_position for c in pcb.netlist.components}
    rot = {c.ref: int(c.initial_rotation or 0) for c in pcb.netlist.components}
    print("best-known placement = current board (normalized)")

    from temper_placer.placer.cp_sat.fixed_copper import (
        audit_fixed_copper,
        build_fixed_copper_items,
        build_free_component_pads,
    )

    pads = build_free_component_pads(pcb.netlist, FREE)
    items_z = build_fixed_copper_items(pcb, pcb.netlist, FREE, MARGIN_FC_MM)

    # Exact fixed-copper audit at the current (best-known) placement.
    viol = audit_fixed_copper(pads, items_z, pos, rot)
    by_kind: dict[str, int] = {}
    by_net: dict[str, int] = {}
    for v in viol:
        by_kind[v.item_kind] = by_kind.get(v.item_kind, 0) + 1
        by_net[f"{v.item_kind}:{v.item_net}"] = by_net.get(f"{v.item_kind}:{v.item_net}", 0) + 1
    n_items = len(items_z)
    n_zone = sum(1 for i in items_z if i.kind == "zone")
    n_seg = sum(1 for i in items_z if i.kind == "segment")
    n_via = sum(1 for i in items_z if i.kind == "via")
    n_pad = sum(1 for i in items_z if i.kind == "pad")

    # No-zones audit for the B reproduction (validator-clean check).
    items_nz = build_fixed_copper_items(
        parse_result_without_zones(pcb), pcb.netlist, FREE, MARGIN_FC_MM)
    viol_nz = audit_fixed_copper(pads, items_nz, pos, rot)

    # Zone reachability under the relaxed envelope (120 global as the probe's
    # headline; also report 60 for contrast).
    zone_rows = zone_reachability(pcb, pads, items_z, pos, rot, cap_mm=120.0)
    zone_rows_60 = zone_reachability(pcb, pads, items_z, pos, rot, cap_mm=60.0)
    joint_rows = joint_zone_reachability(pcb, pads, items_z, pos, rot, cap_mm=120.0)
    joint_rows_60 = joint_zone_reachability(pcb, pads, items_z, pos, rot, cap_mm=60.0)
    encoded_rows = encoded_zone_reachability(pcb, pads, items_z, pos, rot, cap_mm=120.0)

    # Compound audit at the per-ref zone-clear candidate positions.
    candidate = {}
    for r in joint_rows:
        if r["first_clearing_position"] is not None:
            candidate[r["ref"]] = r["first_clearing_position"]
    compound = candidate_compound_audit(pcb, pads, items_z, pos, rot, candidate)

    # Pair verdicts from the run-C baseline core (C_60_s0).
    core_c = matrix.get("C_60_s0", {}).get("core", [])
    pairs, pair_counts = pair_verdict_table(pcb, pos, rot, core_c)

    edges = edge_slack_mm(pcb, pos, rot)

    analysis = {
        "provenance": git_provenance(),
        "best_known_placement_is_current_board": True,
        "c27_at_mm": pos.get("C27"),
        "k3_at_mm": pos.get("K3"),
        "nozones_fixed_copper_violations_at_best": len(viol_nz),
        "zone_inclusive_fixed_copper_violations_at_best": len(viol),
        "fc_violations_by_kind": by_kind,
        "fc_violations_by_net": by_net,
        "fc_items": {"total": n_items, "zone": n_zone, "segment": n_seg,
                     "via": n_via, "pad": n_pad},
        "zone_conflict_reachability_cap120": zone_rows,
        "zone_conflict_reachability_cap60": zone_rows_60,
        "joint_zone_reachability_cap120": joint_rows,
        "joint_zone_reachability_cap60": joint_rows_60,
        "encoded_zone_reachability_cap120": encoded_rows,
        "candidate_compound_audit": compound,
        "pair_verdict_counts": pair_counts,
        # Full per-pair rows are in gap1_runc_envelope_pairs.csv (15,113
        # rows); the JSON keeps only the counts to stay lean.
        "edge_slack_mm_at_best": edges,
    }
    OUT_ZONES.write_text(json.dumps(analysis, indent=2, sort_keys=True))
    print(f"wrote {OUT_ZONES}")

    _prov = git_provenance()
    with OUT_ZONES_CSV.open("w", newline="") as f:
        f.write(f"# provenance: commit={_prov['commit']} dirty={_prov['dirty']}\n")
        w = csv.DictWriter(f, fieldnames=list(zone_rows[0].keys()) if zone_rows else ["ref"])
        w.writeheader()
        w.writerows(zone_rows)
    out_joint_csv = REPO / "docs" / "evidence" / "gap1_runc_envelope_joint.csv"
    with out_joint_csv.open("w", newline="") as f:
        f.write(f"# provenance: commit={_prov['commit']} dirty={_prov['dirty']}\n")
        w = csv.DictWriter(f, fieldnames=list(joint_rows[0].keys()) if joint_rows else ["ref"])
        w.writeheader()
        w.writerows(joint_rows)
    with OUT_PAIRS_CSV.open("w", newline="") as f:
        f.write(f"# provenance: commit={_prov['commit']} dirty={_prov['dirty']}\n")
        w = csv.DictWriter(f, fieldnames=list(pairs[0].keys()) if pairs else ["name"])
        w.writeheader()
        w.writerows(pairs)
    print(f"wrote {OUT_ZONES_CSV} / {out_joint_csv} / {OUT_PAIRS_CSV}")


if __name__ == "__main__":
    main()
