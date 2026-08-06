# provenance: commit=760252f02d76facc1812d9dab1de4f15f27282b3 dirty=false
#!/usr/bin/env python3
"""Gap-1 run-C unsat-core pair table — CORRECTED ref parsing.

# provenance: PLACEHOLDER

The salvaged run-C measurement (``gap1_runc_measure.py``, dead dispatch) parsed
constraint names with ``parts[-4], parts[-2]`` which for the encoder's name
pattern ``sep_<kind>_<a>_<b>_<a>_<b>`` yields the SELF-pair ``(a, a)`` for every
constraint. That invalidated the entire per-constraint box/copper verdict table
in ``gap1_runc_core_table.csv`` (3711 "BOX-BAR-BLOCKER" + 11853
"COPPER-VIOLATION" at a *feasible* B placement are all intra-footprint
self-distances, not inter-component measurements).

This script re-derives the per-pair box-bar vs exact-copper verdicts at the
run-B (best-known feasible) placement using the CORRECT pair
``(parts[-4], parts[-3])`` and the same exact-copper methodology as the wall
spike's ``gap2_wall_pairs.py`` (which regenerated pairs from the domain matrix
and never parsed names):

  * box bar  — solver Chebyshev bbox gap on the even-rounded grid, exactly
    what ``handlers/separated.py::encode_separated`` enforces.
  * copper bar — the REQ-SAFE-01 validator's own ``_CopperModel.copper_distance``
    on exact rotation-aware pad geometry, per applicable domain boundary.
  * margin — domain: max(clearance, creepage) over applicable IEC60335 rows;
    keepaway: 8.0; netclass: 6.0; courtyard: 0.4.

Writes ``docs/evidence/gap1_runc_pairs_corrected.csv`` (per unique pair in the
run-C core) and ``docs/evidence/gap1_runc_pairs_corrected_summary.json``.

NO src/ changes. Read-only w.r.t. ``pcb/temper.kicad_pcb``.

Usage:
    uv run --no-sync python docs/evidence/gap1_runc_pairs_corrected.py
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
from temper_placer.placer.cp_sat.model import CpSatModel  # noqa: E402
from temper_placer.requirements.validators.clearance import (  # noqa: E402
    IEC60335_REQUIREMENTS,
    VoltageDomain,
    _CopperModel,
    _domain_boundary_pairs,
    _nets_domain_map,
)

MARGIN_EPS = 1e-6

PREFIX_KIND = (
    ("sep_domain_clearance_", "domain"),
    ("sep_keepaway_unclassified_", "keepaway"),
    ("sep_netclass_autogen_", "netclass"),
    ("sep_courtyard_", "courtyard"),
)


def pair_from_name(name: str) -> tuple[str, str] | None:
    """Extract (ra, rb) from ``sep_<kind>_<a>_<b>_<a>_<b>``-shaped names.

    The encoder builds ``label = f"sep_{constraint.id}_{ra}_{rb}"`` where
    ``constraint.id`` already ends in ``_{ra}_{rb}``, so the name ends with
    the ref pair TWICE: last-4 tokens are [ra, rb, ra, rb]. The correct pair
    is (tokens[-4], tokens[-3]). (The salvaged script used tokens[-4],
    tokens[-2] == (ra, ra) — a self-pair bug.)
    """
    for prefix, _kind in PREFIX_KIND:
        if name.startswith(prefix):
            parts = name.split("_")
            if len(parts) < 4:
                return None
            return (parts[-4], parts[-3])
    return None


def solver_box_geometry(pcb, positions, rotations):
    """({ref: (cx, cy)}, {ref: (w, h)}) at *positions* on the model grid."""
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


def main():
    pcb = parse_kicad_pcb(REPO / "pcb" / "temper.kicad_pcb")
    full, _vd, stats = load_real_board_placement()
    full_vd = stats["full_voltage_domains"]

    # True per-pair netclass margins from the same generator solve_placement
    # uses (Signal<->Power is 0.25mm, not 6.0 — the 6.0 figure only applies
    # to HV-crossing class pairs in configs/netclass_rules.yaml).
    from temper_placer.io.netclass_loader import load_netclass_rules
    from temper_placer.placer.cp_sat.netclass_constraints import (
        generate_netclass_separated_constraints,
    )

    _nc_path = (_PLACER_DIR / "configs" / "netclass_rules.yaml")
    nc_rules = load_netclass_rules(_nc_path)
    nc_constraints = generate_netclass_separated_constraints(
        pcb.netlist, pcb.netlist.components, nc_rules.design_rules
    )
    nc_margin: dict[tuple[str, str], float] = {}
    for c in nc_constraints:
        key = tuple(sorted([c.a, c.b]))
        nc_margin[key] = max(nc_margin.get(key, 0.0), c.min_distance_mm)

    cores_path = REPO / "docs" / "evidence" / "gap1_runc_solve_cores.json"
    summary_path = REPO / "docs" / "evidence" / "gap1_runc_summary.json"
    cores = json.loads(cores_path.read_text())
    summary = json.loads(summary_path.read_text())

    names_c = cores["C_repair_with_zones"]["core"]
    best = summary.get("best_known_placement") or {}
    best_rot = {c.ref: int(c.initial_rotation or 0)
                for c in pcb.netlist.components}
    # The B solve fixes rotations, so solver rotations == initial rotations.

    centers, sizes = solver_box_geometry(pcb, best, best_rot)
    placement = build_placement_at(pcb, best, best_rot)
    copper = _CopperModel(placement)
    nets_domain = _nets_domain_map(full, full_vd)

    wanted: dict[tuple[str, str, str], dict] = {}
    unmatched = 0
    for name in names_c:
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

    rows = []
    n_box = n_copper = n_clean = 0
    # Domain pair info: iterate the matrix rows exactly like
    # gap2_wall_pairs.py::consider() (membership-testing ref strings against
    # _domain_boundary_pairs' component dicts never matches).
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
            cd, _g, _l = copper.copper_distance(ra, dom_a, rb, dom_b,
                                                nets_domain)
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

    # Keepaway pairs: 8.0 bar, ISOLATED/HV with empty net map (wall-spike
    # methodology).
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

    for name in names_c:
        if not name.startswith("sep_keepaway_unclassified_"):
            continue
        pair = pair_from_name(name)
        if pair is None:
            continue
        consider_keepaway(pair[0], pair[1], 8.0)

    for (kind, ra, rb), info in sorted(wanted.items()):
        key = tuple(sorted([ra, rb]))
        if kind == "domain":
            pi = pair_info.get(key)
            if pi is None:
                # Pair named in core but not on any matrix boundary walked
                # above (shouldn't happen; defensive).
                continue
            margin = pi["margin"]
            cd = pi["copper"]
            domains = pi["domains"]
        elif kind == "keepaway":
            ki = keepaway_info.get(key)
            if ki is None:
                continue
            margin = ki["margin"]
            cd = ki["copper"]
            domains = "uncl<->HV"
        else:
            if kind == "netclass":
                margin = nc_margin.get(key, 0.0)
                if margin <= 0.0:
                    continue  # pair not actually constrained by netclass rules
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

    out_csv = REPO / "docs" / "evidence" / "gap1_runc_pairs_corrected.csv"
    with out_csv.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    out_summary = {
        "total_pair_constraints_in_core": len(wanted),
        "unmatched_refs": unmatched,
        "box_bar_blocker": n_box,
        "copper_violation": n_copper,
        "clean": n_clean,
        "b_placement": {"K3": best.get("K3"), "C27": best.get("C27")},
        "note": ("corrected pair parsing (parts[-4], parts[-3]); salvaged "
                 "table used self-pairs and is invalid"),
    }
    out_json = REPO / "docs" / "evidence" / "gap1_runc_pairs_corrected_summary.json"
    out_json.write_text(json.dumps(out_summary, indent=2, sort_keys=True))
    print(json.dumps(out_summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
