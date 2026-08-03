# provenance: commit=d1bcfe1235a9026409e1b07914eb96b3abc41b52 dirty=false
#!/usr/bin/env python3
"""Gap-1 run-C unsat-core measurement: zone-inclusive fixed-copper solve.

# provenance: PLACEHOLDER

Companion to ``docs/evidence/2026-08-01-gap1-runC-unsat-core.md``.

Reproduces the production repair recipe with fixed-copper INCLUDING zone
items ("run C", the gap-1 zone-inclusive fixed-copper solve) on
``pcb/temper.kicad_pcb`` at the committed board state, extracts the unsat
core, and produces a per-constraint explanation table:

  * run C  -- nothing pinned, hard Manhattan displacement cap 60mm, rotations
    fixed at current, domain-clearance + keepaway + courtyard + netclass
    SeparatedConstraints, fixed-copper vs traces/vias/zones/other pads for
    FREE={K3,C27} at margin 0.05mm (parse_result carries board zones).
  * run B  -- identical but fixed-copper parse_result carries NO zones (the
    zone-blind repair recipe from the run-B evidence doc). Used as the
    "best-known feasible placement" for the per-constraint slack table.

For every constraint the run-C core names:

  * edge_margin_<ref>  -- measured edge slack (mm) at the run-B placement
    (min over the four box edges of clearance to the board edge; negative
    means the box pokes past the edge).
  * sep_domain_clearance_* / sep_keepaway_unclassified_* /
    sep_netclass_autogen_* / sep_courtyard_* -- pair constraints: solver
    box-bar distance, required margin, exact-copper pad-to-pad distance at
    the run-B placement (the REQ-SAFE-01 measurement), verdict per pair
    (BOX-BAR-BLOCKER / COPPER-VIOLATION / CLEAN).
  * no_overlap_2d / fixed_copper_<ref> -- aggregate flags; for
    fixed_copper_<ref> the exact fixed-copper oracle audit at the run-B
    placement, broken out by item kind (segment/via/zone/pad) and by net.

Writes ``docs/evidence/gap1_runc_solve_cores.json``,
``docs/evidence/gap1_runc_core_table.csv`` and
``docs/evidence/gap1_runc_summary.json``.

NO src/ changes. Read-only w.r.t. ``pcb/temper.kicad_pcb``.

Usage:
    uv run --no-sync python docs/evidence/gap1_runc_measure.py
"""

from __future__ import annotations

import csv
import json
import os
import sys
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
SEED = 0
MAX_DISP_MM = 60.0
MARGIN_EPS = 1e-6


# ---------------------------------------------------------------------------
# geometry helpers (identical semantics to the solver / validator)
# ---------------------------------------------------------------------------


def solver_box_geometry(pcb):
    """({ref: (cx_units, cy_units)}, {ref: (w_units, h_units)}) at current
    board positions on the model's even-rounded integer grid, rotation-aware.
    """
    model = CpSatModel(units_per_mm=100)
    centers: dict[str, tuple[int, int]] = {}
    sizes: dict[str, tuple[int, int]] = {}
    for c in pcb.netlist.components:
        if c.initial_position is None:
            continue
        w = model.mm_to_units(float(c.bounds[0]))
        h = model.mm_to_units(float(c.bounds[1]))
        r = int(c.initial_rotation or 0)
        if r % 2 == 1:
            w, h = h, w
        centers[c.ref] = (model.mm_to_units(c.initial_position[0]),
                          model.mm_to_units(c.initial_position[1]))
        sizes[c.ref] = (w, h)
    return centers, sizes


def box_dist_mm(ra, rb, centers, sizes) -> float:
    """Chebyshev box gap in mm (exactly what SeparatedConstraint encodes)."""
    cx_a, cy_a = centers[ra]
    cx_b, cy_b = centers[rb]
    hw_a, hh_a = sizes[ra][0] // 2, sizes[ra][1] // 2
    hw_b, hh_b = sizes[rb][0] // 2, sizes[rb][1] // 2
    dx = abs(cx_a - cx_b) - (hw_a + hw_b)
    dy = abs(cy_a - cy_b) - (hh_a + hh_b)
    return max(dx, dy) * 0.01


def build_placement_at(pcb, positions, rotations):
    """Validator-shape placement dict over every parsed ref at *positions*."""
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


def pair_table(pcb, positions, rotations, core_names):
    """Box-bar vs copper-bar at *positions* for every pair constraint named
    in the core. Mirrors gap2_wall_pairs.py's exact-copper measurement."""
    centers, sizes = solver_box_geometry(pcb)
    # Box geometry must reflect the *solved* positions, not the current ones.
    for ref, (x, y) in positions.items():
        centers[ref] = (CpSatModel(units_per_mm=100).mm_to_units(x),
                        CpSatModel(units_per_mm=100).mm_to_units(y))
    placement = build_placement_at(pcb, positions, rotations)
    full, _vd, stats = load_real_board_placement()
    full_vd = stats["full_voltage_domains"]
    model = _CopperModel(placement)
    nets_domain = _nets_domain_map(full, full_vd)

    wanted = set()
    for name in core_names:
        for prefix, kind in (
            ("sep_domain_clearance_", "domain"),
            ("sep_keepaway_unclassified_", "keepaway"),
            ("sep_netclass_autogen_", "netclass"),
            ("sep_courtyard_", "courtyard"),
        ):
            if name.startswith(prefix):
                # Constraint names end with the ref pair twice:
                # sep_domain_clearance_<a>_<b>_<a>_<b> for domain/keepaway/
                # courtyard, and sep_netclass_autogen_<NetA>_<NetB>_<a>_<b>_<a>_<b>
                # for netclass. The refs are always the LAST 4 underscore
                # tokens (refs never contain underscores).
                parts = name.split("_")
                if len(parts) >= 4:
                    ra, rb = parts[-4], parts[-2]
                    wanted.add((kind, ra, rb))
                break

    rows = []
    for (kind, ra, rb) in sorted(wanted):
        margin = 0.0
        domain_tag = "uncl<->HV"
        dom_pair = None
        if kind == "domain":
            best = (None, 0.0, "?")
            for (dom_a, dom_b, _ins), req in IEC60335_REQUIREMENTS.items():
                if (ra, rb) in _domain_boundary_pairs(full, dom_a, dom_b, nets_domain) or \
                   (rb, ra) in _domain_boundary_pairs(full, dom_a, dom_b, nets_domain):
                    m = max(req["min_clearance_mm"], req["min_creepage_mm"])
                    if m > best[1]:
                        best = (m, m, f"{dom_a.value}<->{dom_b.value}")
                        dom_pair = (dom_a, dom_b)
            margin = best[1]
            domain_tag = best[2]
            if dom_pair is not None:
                da, db = dom_pair
                cd, _g, _l = model.copper_distance(ra, da, rb, db, nets_domain)
            else:
                cd = float("inf")
            if margin == 0.0:
                # pair not found through the matrix walk; fall back to the
                # generator's own pair list for the margin.
                from temper_placer.placer.cp_sat.domain_clearance import (
                    generate_domain_clearance_constraints,
                )
                dc = generate_domain_clearance_constraints(full, nets_domain)
                for c in dc:
                    if {c.a, c.b} == {ra, rb}:
                        margin = c.min_distance_mm
                        break
                if margin == 0.0:
                    margin = 8.0
                    domain_tag = "matrix-walk-miss"
                cd, _g, _l = model.copper_distance(ra, VoltageDomain.ISOLATED,
                                                   rb, VoltageDomain.ISOLATED,
                                                   nets_domain)
        elif kind == "keepaway":
            margin = 8.0
            cd, _g, _l = model.copper_distance(ra, VoltageDomain.ISOLATED,
                                               rb, VoltageDomain.ISOLATED, {})
        else:
            margin = 0.4 if kind == "courtyard" else 6.0
            cd, _g, _l = model.copper_distance(ra, VoltageDomain.ISOLATED,
                                               rb, VoltageDomain.ISOLATED,
                                               nets_domain)
        bd = box_dist_mm(ra, rb, centers, sizes)
        if cd < margin - MARGIN_EPS:
            verdict = "COPPER-VIOLATION"
        elif bd < margin - MARGIN_EPS:
            verdict = "BOX-BAR-BLOCKER"
        else:
            verdict = "CLEAN"
        rows.append({"kind": kind, "ra": ra, "rb": rb,
                     "margin_mm": round(margin, 3),
                     "box_dist_mm": round(bd, 3),
                     "copper_dist_mm": round(cd, 3),
                     "domains": domain_tag, "verdict": verdict})
    return rows


def edge_slack_mm(pcb, positions, rotations):
    """Min clearance (mm) from each component's box to the board edge at
    *positions*. Negative = box pokes outside the edge margin."""
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


def classify_core(core_names):
    kinds = {
        "edge_margin": [], "no_overlap_2d": [], "fixed_copper": [],
        "sep_domain_clearance": [], "sep_keepaway": [],
        "sep_netclass_autogen": [], "sep_courtyard": [],
        "other": [],
    }
    for n in core_names:
        if n.startswith("edge_margin_"):
            kinds["edge_margin"].append(n)
        elif n == "no_overlap_2d":
            kinds["no_overlap_2d"].append(n)
        elif n.startswith("fixed_copper_"):
            kinds["fixed_copper"].append(n)
        elif n.startswith("sep_domain_clearance_"):
            kinds["sep_domain_clearance"].append(n)
        elif n.startswith("sep_keepaway_unclassified_"):
            kinds["sep_keepaway"].append(n)
        elif n.startswith("sep_netclass_autogen_"):
            kinds["sep_netclass_autogen"].append(n)
        elif n.startswith("sep_courtyard_"):
            kinds["sep_courtyard"].append(n)
        else:
            kinds["other"].append(n)
    return kinds


def fixed_copper_audit(pcb, positions, rotations):
    """Exact fixed-copper oracle at *positions* for FREE={K3,C27}."""
    from temper_placer.placer.cp_sat.fixed_copper import (
        audit_fixed_copper,
        build_fixed_copper_items,
        build_free_component_pads,
    )
    pads = build_free_component_pads(pcb.netlist, FREE)
    items = build_fixed_copper_items(pcb, pcb.netlist, FREE, MARGIN_FC_MM)
    viol = audit_fixed_copper(pads, items, positions, rotations)
    return viol, items


def run_variant(pcb, extra, *, label, fc, timeout_ms=180_000):
    pos = {c.ref: c.initial_position for c in pcb.netlist.components}
    rot = {c.ref: int(c.initial_rotation or 0) for c in pcb.netlist.components}
    hints = {ref: (x, y, rot[ref]) for ref, (x, y) in pos.items()}
    min_disp = {ref: (x, y) for ref, (x, y) in pos.items()}
    res = solve_placement(
        netlist=pcb.netlist,
        board=pcb.board,
        extra_constraints=extra,
        timeout_ms=timeout_ms,
        seed=SEED,
        hint_positions=hints,
        minimize_displacement_to=min_disp,
        max_displacement_mm=MAX_DISP_MM,
        fixed_rotations={ref: rot[ref] for ref in pos},
        fixed_copper=fc,
    )
    names = [u["name"] for u in res.unsat_core]
    print(f"[{label}] status={res.status} time={res.solve_time_ms:.1f}ms "
          f"core={len(names)}")
    return res, names


def main():
    pcb = parse_kicad_pcb(REPO / "pcb" / "temper.kicad_pcb")
    full, _vd, stats = load_real_board_placement()
    full_vd = stats["full_voltage_domains"]
    all_refs = {c.ref for c in pcb.netlist.components}
    dc = generate_domain_clearance_constraints(full, full_vd, component_refs=all_refs)
    kw = generate_unclassified_hv_keepaway_constraints(full, full_vd, component_refs=all_refs)
    extra = dc + kw
    print(f"refs={len(all_refs)} domain={len(dc)} keepaway={len(kw)} total={len(extra)}")

    fc_zones = {"parse_result": pcb, "free_refs": FREE, "margin_mm": MARGIN_FC_MM}
    fc_nozones = {"parse_result": parse_result_without_zones(pcb),
                  "free_refs": FREE, "margin_mm": MARGIN_FC_MM}

    res_b, names_b = run_variant(pcb, extra, label="B repair no-zones", fc=fc_nozones,
                                 timeout_ms=180_000)
    res_c, names_c = run_variant(pcb, extra, label="C repair with-zones", fc=fc_zones,
                                 timeout_ms=90_000)

    # The run-C core from the PRIOR spike (gap2_wall_solve_cores.json variant C)
    # for cross-check, if present in the repo.
    prior = None
    prior_path = REPO / "docs" / "evidence" / "gap2_wall_solve_cores.json"
    if prior_path.exists():
        prior = json.loads(prior_path.read_text()).get("C_repair_with_zones", {}).get("core")

    best = {}
    rot = {c.ref: int(c.initial_rotation or 0) for c in pcb.netlist.components}
    if res_b.status in ("feasible", "optimal"):
        best = res_b.positions
        best_rot = {**rot, **res_b.rotations}
    else:
        best_rot = rot

    kinds_c = classify_core(names_c)
    summary = {
        "run_C": {"status": res_c.status,
                  "solve_time_ms": round(res_c.solve_time_ms, 1),
                  "core_size": len(names_c),
                  "core_by_kind": {k: len(v) for k, v in kinds_c.items()},
                  "core_names": names_c},
        "run_B": {"status": res_b.status,
                  "solve_time_ms": round(res_b.solve_time_ms, 1),
                  "core_size": len(names_b)},
        "prior_spike_variantC_core_size": len(prior) if prior else None,
        "core_identical_to_prior_spike": sorted(names_c) == sorted(prior) if prior else None,
        "best_known_placement": best,
    }

    out_cores = REPO / "docs" / "evidence" / "gap1_runc_solve_cores.json"
    out_cores.write_text(json.dumps(
        {"B_repair_no_zones": {"status": res_b.status, "core": names_b},
         "C_repair_with_zones": {"status": res_c.status, "core": names_c}},
        indent=2, sort_keys=True))
    print(f"wrote {out_cores}")

    if best:
        edges = edge_slack_mm(pcb, best, best_rot)
        pairs = pair_table(pcb, best, best_rot, names_c)
        viol, items = fixed_copper_audit(pcb, best, best_rot)
        by_kind: dict[str, int] = {}
        by_net: dict[str, int] = {}
        for v in viol:
            by_kind[v.item_kind] = by_kind.get(v.item_kind, 0) + 1
            by_net[f"{v.item_kind}:{v.item_net}"] = by_net.get(f"{v.item_kind}:{v.item_net}", 0) + 1
        fc_rows = [{"ref": v.ref, "pad": v.pad_number, "item_kind": v.item_kind,
                    "item_net": v.item_net, "required_mm": round(v.required_mm, 3),
                    "actual_mm": round(v.actual_mm, 3), "reason": v.reason}
                   for v in viol]
        n_items = len(items)
        n_zone_items = sum(1 for i in items if i.kind == "zone")
        n_seg_items = sum(1 for i in items if i.kind == "segment")
        n_via_items = sum(1 for i in items if i.kind == "via")
        n_pad_items = sum(1 for i in items if i.kind == "pad")

        rows = []
        for name in sorted(names_c):
            if name.startswith("edge_margin_"):
                ref = name[len("edge_margin_"):]
                rows.append({"name": name, "kind": "edge-margin",
                             "refs": ref,
                             "box_dist_mm": "", "margin_mm": "",
                             "copper_dist_mm": "",
                             "slack_mm_at_best": edges.get(ref),
                             "verdict": "NEGATIVE-SLACK" if edges.get(ref, 0) < 0 else "OK-AT-BEST"})
            elif name == "no_overlap_2d":
                rows.append({"name": name, "kind": "no-overlap-2d",
                             "refs": "", "box_dist_mm": "", "margin_mm": "",
                             "copper_dist_mm": "", "slack_mm_at_best": "",
                             "verdict": "AGGREGATE"})
            elif name.startswith("fixed_copper_"):
                ref = name[len("fixed_copper_"):]
                nv = sum(1 for v in fc_rows if v["ref"] == ref)
                rows.append({"name": name, "kind": "fixed-copper",
                             "refs": ref, "box_dist_mm": "", "margin_mm": MARGIN_FC_MM,
                             "copper_dist_mm": "",
                             "slack_mm_at_best": f"{nv} exact violations at best",
                             "verdict": "COPPER-OVERLAP-AT-BEST" if nv else "CLEAN-AT-BEST"})
            else:
                # Pair constraint: match by (kind, ra, rb) using the same
                # last-4-tokens rule the pair table uses.
                parts = name.split("_")
                target = None
                if len(parts) >= 4:
                    target = (name.rsplit("_", 4)[0], parts[-4], parts[-2])
                matched = None
                if target is not None:
                    pfx, ra, rb = target
                    for pr in pairs:
                        if (pr["ra"], pr["rb"]) == (ra, rb) and \
                           name.startswith(f"sep_{pr['kind']}"):
                            matched = pr
                            break
                if matched is not None:
                    rows.append({"name": name, "kind": matched["kind"],
                                 "refs": f"{matched['ra']},{matched['rb']}",
                                 "box_dist_mm": matched["box_dist_mm"],
                                 "margin_mm": matched["margin_mm"],
                                 "copper_dist_mm": matched["copper_dist_mm"],
                                 "slack_mm_at_best": "",
                                 "verdict": matched["verdict"]})
                else:
                    rows.append({"name": name, "kind": "pair-unknown",
                                 "refs": "", "box_dist_mm": "",
                                 "margin_mm": "", "copper_dist_mm": "",
                                 "slack_mm_at_best": "", "verdict": "?"})

        out_csv = REPO / "docs" / "evidence" / "gap1_runc_core_table.csv"
        with out_csv.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

        summary["best_known"] = {
            "fixed_copper_items": n_items,
            "zone_items": n_zone_items,
            "segment_items": n_seg_items,
            "via_items": n_via_items,
            "pad_items": n_pad_items,
            "exact_fc_violations_total": len(fc_rows),
            "exact_fc_violations_by_kind": by_kind,
            "exact_fc_violations_by_net": by_net,
            "exact_fc_violations": fc_rows[:400],
            "edge_slack_mm": edges,
            "pair_verdict_counts": {
                v: sum(1 for r in pairs if r["verdict"] == v)
                for v in ("BOX-BAR-BLOCKER", "COPPER-VIOLATION", "CLEAN")
            },
            "pairs": pairs,
        }
        print("best-known fixed-copper exact violations:",
              json.dumps({"total": len(fc_rows), "by_kind": by_kind}))
        print("pair verdicts at best:", summary["best_known"]["pair_verdict_counts"])

    out_json = REPO / "docs" / "evidence" / "gap1_runc_summary.json"
    out_json.write_text(json.dumps(summary, indent=2, sort_keys=True))
    print(f"wrote {out_json}")


if __name__ == "__main__":
    main()
